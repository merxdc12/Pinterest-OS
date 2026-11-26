"""Unified local publishing plan. Legacy pin schedules stay authoritative."""
from datetime import datetime
from pathlib import Path
import re
import hashlib
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from .storage import utc_now
from .utm import marketing_url, OWNED_HOSTS, new_tracking_id, read_tracking_id
from .carousel_logic import validate_slides, png_dimensions
from .content_factory import ContentFactory

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS carousel_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    carousel_id INTEGER NOT NULL REFERENCES carousels(id) ON DELETE CASCADE,
    scheduled_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PLANNED','READY','PUBLISHED','CANCELLED')),
    created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS plan_details (
    id INTEGER PRIMARY KEY,
    pin_schedule_id INTEGER UNIQUE REFERENCES pin_schedule(id) ON DELETE CASCADE,
    carousel_schedule_id INTEGER UNIQUE REFERENCES carousel_schedule(id) ON DELETE CASCADE,
    board_id INTEGER REFERENCES boards(id) ON DELETE SET NULL,
    original_url TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
    tracking_id INTEGER REFERENCES pin_tracking(id),
    external_review INTEGER NOT NULL DEFAULT 0,
    affiliate INTEGER NOT NULL DEFAULT 0, disclosure TEXT NOT NULL DEFAULT '',
    CHECK((pin_schedule_id IS NULL) != (carousel_schedule_id IS NULL)))""",
    "CREATE INDEX IF NOT EXISTS idx_carousel_schedule_date ON carousel_schedule(scheduled_at)",
)

def backup_before_migration(conn,path):
    """Create an independent verified backup before upgrading an existing workspace."""
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='plan_details'").fetchone():
        return None
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone():
        return None
    from .workspace import backup_database
    from uuid import uuid4
    # A project manifest covers its directory; keep this snapshot outside it.
    if (path.parent/'manifest.json').is_file():
        dest=path.parent.parent/(path.parent.name+'.pre-content-plan.sqlite3')
    else:
        dest=path.with_name(path.name+'.pre-content-plan.sqlite3')
    if dest.exists():
        dest=dest.with_name(dest.stem+'-'+uuid4().hex[:8]+dest.suffix)
    return backup_database(conn,dest)

def migrate(conn):
    for sql in SCHEMA:
        conn.execute(sql)

def _dicts(storage, sql, args=()):
    cursor = storage.conn.execute(sql, args)
    keys = [column[0] for column in cursor.description]
    return [dict(zip(keys, row)) for row in cursor.fetchall()]

def _valid_url(url):
    try:
        p = urlsplit(url)
        return (p.scheme in ('http', 'https') and bool(p.hostname)
                and p.username is None and p.password is None
                and not re.search(r'[\x00-\x20\x7f\\]', url))
    except ValueError:
        return False

def owned(url):
    try:
        p = urlsplit(url)
        return p.scheme == 'https' and p.hostname in OWNED_HOSTS and p.port in (None,443)
    except ValueError:
        return False

def entries(storage, start, end, board_id=None):
    """Positive IDs are existing pin schedules; negative IDs are carousel schedules."""
    pins = _dicts(storage, """
        SELECT s.id,s.pin_id,NULL AS carousel_id,'PIN' AS kind,s.scheduled_at,s.status,
        p.title,CASE WHEN d.id IS NULL THEN p.board_id ELSE d.board_id END AS board_id,
        CASE WHEN d.id IS NULL THEN p.destination_url ELSE d.original_url END AS original_url,
        p.description,d.id AS details_id,d.tracking_id,d.external_review,d.affiliate,d.disclosure,
        p.status AS pin_status,t.marketing_url,t.campaign
        FROM pin_schedule s JOIN pins p ON p.id=s.pin_id
        LEFT JOIN plan_details d ON d.pin_schedule_id=s.id
        LEFT JOIN pin_tracking t ON t.id=d.tracking_id
        WHERE s.scheduled_at BETWEEN ? AND ?""", (start,end+'T23:59'))
    carousels = _dicts(storage, """
        SELECT -s.id AS id,NULL AS pin_id,s.carousel_id,'CAROUSEL' AS kind,s.scheduled_at,s.status,
        c.title,d.board_id,d.original_url,d.description,d.id AS details_id,d.tracking_id,
        d.external_review,d.affiliate,d.disclosure,NULL AS pin_status,t.marketing_url,t.campaign
        FROM carousel_schedule s JOIN carousels c ON c.id=s.carousel_id
        JOIN plan_details d ON d.carousel_schedule_id=s.id
        LEFT JOIN pin_tracking t ON t.id=d.tracking_id
        WHERE s.scheduled_at BETWEEN ? AND ?""", (start,end+'T23:59'))
    boards = {b['id']:b['name'] for b in storage.all('boards')}
    rows = pins + carousels
    for row in rows:
        row['board_name'] = boards.get(row['board_id'])
        row['destination_url'] = row['marketing_url'] or row['original_url']
        try:
            row['tracking_code'] = read_tracking_id(row["marketing_url"] or "", "pint") if row["tracking_id"] else ""
        except (ValueError, TypeError):
            row['tracking_code'] = ""
    return sorted((r for r in rows if board_id is None or r['board_id']==board_id),
                  key=lambda r:(r['scheduled_at'],r['id']))

def get_entry(storage, entry_id):
    return next((r for r in entries(storage,'0001-01-01','9999-12-31') if r['id']==entry_id),None)

def conflicts(storage, when, board_id, exclude=None):
    return [r for r in entries(storage,when[:10],when[:10],board_id)
            if r['board_id']==board_id and r['scheduled_at']==when and r['id']!=exclude
            and r['status']!='CANCELLED']

def queue(storage, now=None):
    now=now or datetime.now()
    return [r for r in entries(storage,'0001-01-01',now.date().isoformat())
            if r['scheduled_at']<=now.strftime('%Y-%m-%dT%H:%M')
            and r['status'] in ('PLANNED','READY') and r['pin_status']!='PUBLISHED']

def creative_signature(storage,row):
    """Exact ordered asset hashes, not perceptual similarity."""
    if row['kind']=='PIN':
        design=storage.get_pin_design(row['pin_id'])
        paths=[(design or {}).get('png_path')]
    else:
        paths=[s.get('png_path') for s in storage.carousel_slides(row['carousel_id'])]
    if not paths or not all(paths): return None
    try:
        hashes=[]
        for value in paths:
            path=Path(value)
            digest=hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):
                    digest.update(chunk)
            hashes.append(digest.hexdigest())
        return tuple(hashes)
    except (OSError,ValueError):
        return None

def canonical_destination(url):
    try:
        parts=urlsplit(url)
        query=sorted((k,v) for k,v in parse_qsl(parts.query,keep_blank_values=True)
                     if not k.lower().startswith('utm_'))
        return urlunsplit((parts.scheme.lower(),parts.netloc.lower(),parts.path,
                           urlencode(query),''))
    except ValueError:
        return url

def duplicate_candidates(storage,row):
    signature=creative_signature(storage,row)
    if signature is None: return []
    result=[]
    for other in entries(storage,'0001-01-01','9999-12-31',row['board_id']):
        if (other['id']==row['id'] or other['status']=='CANCELLED'
                or other['kind']!=row['kind']
                or canonical_destination(other['original_url'])!=canonical_destination(row['original_url'])):
            continue
        if creative_signature(storage,other)==signature: result.append(other)
    return result

def issues(storage, row):
    from .publishing_logic import publishing_issues
    problems=[]
    if row['kind']=='PIN':
        pin=storage.get('pins',row['pin_id'])
        if not pin: return ['Pin no longer exists']
        design=storage.get_pin_design(row['pin_id'])
        pin=dict(pin,board_id=row['board_id'],destination_url=row['destination_url'])
        problems.extend(publishing_issues(pin,design))
        problems.extend(ContentFactory(storage).publication_issues(row['pin_id']))
        if row['details_id'] is not None and design and design.get('png_path'):
            try:
                path=Path(design['png_path'])
                if png_dimensions(path)!=(1000,1500):
                    problems.append('Pin PNG must be 1000 × 1500')
            except (OSError,ValueError):
                problems.append('Invalid or missing PNG')
    else:
        if not row['title'].strip(): problems.append('Carousel title')
        if not row['description'].strip(): problems.append('Carousel description')
        problems.extend(validate_slides(storage.carousel_slides(row['carousel_id'])))
    if row['details_id'] is not None:
        if len(row['title'])>100: problems.append('Title exceeds 100 characters')
        if len(row['description'])>500: problems.append('Description exceeds 500 characters')
        if duplicate_candidates(storage,row):
            problems.append('Exact duplicate creative and destination on this board')
        if row['board_id'] is None: problems.append('Assigned board')
        if not _valid_url(row['original_url']): problems.append('Valid destination URL')
        if owned(row['original_url']):
            if not row['tracking_id'] or not row['tracking_code']:
                problems.append('ITHutir UTM required or invalid')
            else:
                try:
                    expected = marketing_url(row['original_url'], 'pint', row['campaign'], row['tracking_code'])
                    if expected != row['marketing_url']:
                        problems.append('UTM URL does not match registered destination or campaign')
                except (ValueError, TypeError):
                    problems.append('Invalid UTM registry data')
        elif not row['external_review']:
            problems.append('External destination / partner rules not reviewed')
        if row['affiliate'] and (not row['disclosure'].strip()
            or row['disclosure'].strip().casefold() not in row['description'].casefold()):
            problems.append('Affiliate disclosure must appear in description')
    return list(dict.fromkeys(problems))

def save(storage, kind, content_id, when, board_id, url, description='', campaign='pinterest',
         add_utm=True, external_review=False, affiliate=False, disclosure='', status='PLANNED',
         entry_id=None):
    if kind not in ('PIN','CAROUSEL') or status not in ('PLANNED','READY','CANCELLED'):
        raise ValueError('Invalid content type or planning status')
    datetime.strptime(when,'%Y-%m-%dT%H:%M')
    if board_id is None or not storage.get('boards',board_id):
        raise ValueError('Select a board')
    url=url.strip()
    if not _valid_url(url):
        raise ValueError('Enter a valid HTTP(S) destination URL')
    if owned(url) and add_utm:
        marketing_url(url,'pint',campaign,'pint_000001')
    elif add_utm:
        raise ValueError('UTM can only be generated for owned HTTPS ITHutir URLs; review external links manually')
    old=get_entry(storage,entry_id) if entry_id is not None else None
    if old is None and status=='CANCELLED':
        raise ValueError('A new plan cannot be cancelled before creation')
    if entry_id is not None and (not old or old['kind']!=kind or old['status'] in ('PUBLISHED','CANCELLED')):
        raise ValueError('Completed/cancelled entries cannot be changed')
    if old and (old['pin_id'] if kind=='PIN' else old['carousel_id'])!=content_id:
        raise ValueError('Cannot change content of an existing plan; create a new entry')
    if kind=='PIN':
        pin=storage.get('pins',content_id)
        if not pin or pin['status']=='PUBLISHED': raise ValueError('Select an unpublished pin')
        description=pin['description']
        # Approved factory content must retain its reviewed board and canonical URL.
        slots=ContentFactory(storage).rows('SELECT id FROM campaign_slots WHERE pin_id=?',(content_id,))
        if slots and (board_id!=pin['board_id'] or url!=pin['destination_url']):
            raise ValueError('Content Factory: change board/URL in the Factory and reapprove first')
        if slots and not old:
            raise ValueError('Content Factory: export the approved slot to Calendar first')
        if storage.conn.execute("SELECT 1 FROM pin_schedule WHERE pin_id=? AND status IN ('PLANNED','READY') AND id!=?",(content_id,entry_id or -1)).fetchone():
            raise ValueError('This pin already has a pending plan; edit that entry')
    else:
        if not any(c['id']==content_id for c in storage.list_carousels()):
            raise ValueError('Select a carousel')
        if any(r['kind']=='CAROUSEL' and r['carousel_id']==content_id and r['board_id']==board_id
               and r['status'] in ('PLANNED','READY','PUBLISHED') and r['id']!=entry_id
               for r in entries(storage,'0001-01-01','9999-12-31')):
            raise ValueError('This carousel is already planned/published for this board')
    conn=storage.conn
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        if old:
            sid=abs(entry_id)
            table='pin_schedule' if kind=='PIN' else 'carousel_schedule'
            conn.execute(f'UPDATE {table} SET scheduled_at=?,status=? WHERE id=?',(when,status,sid))
        else:
            table,key=('pin_schedule','pin_id') if kind=='PIN' else ('carousel_schedule','carousel_id')
            sid=conn.execute(f'INSERT INTO {table}({key},scheduled_at,status,created_at) VALUES(?,?,?,?)',
                             (content_id,when,status,utc_now())).lastrowid
        track=None
        if add_utm:
            if old and old['tracking_id'] and old['original_url']==url and old['campaign']==campaign:
                track=old['tracking_id']
            else:
                # Shared registry sequence, reserved for a publication rather than a library pin.
                track=conn.execute("INSERT INTO pin_tracking(pin_id,original_url,marketing_url,campaign,term,created_at) VALUES(NULL,?,'',?,'',?)",
                                   (url,campaign,utc_now())).lastrowid
                generated=marketing_url(url,'pint',campaign,new_tracking_id('pint'))
                conn.execute('UPDATE pin_tracking SET marketing_url=? WHERE id=?',(generated,track))
        field='pin_schedule_id' if kind=='PIN' else 'carousel_schedule_id'
        conn.execute(f"""INSERT INTO plan_details({field},board_id,original_url,description,tracking_id,external_review,affiliate,disclosure)
                        VALUES(?,?,?,?,?,?,?,?) ON CONFLICT({field}) DO UPDATE SET
                        board_id=excluded.board_id,original_url=excluded.original_url,description=excluded.description,
                        tracking_id=excluded.tracking_id,external_review=excluded.external_review,
                        affiliate=excluded.affiliate,disclosure=excluded.disclosure""",
                     (sid,board_id,url,description,track,int(external_review),int(affiliate),disclosure.strip()))
        signed=sid if kind=='PIN' else -sid
        if status=='READY':
            problems=issues(storage,get_entry(storage,signed))
            if problems: raise ValueError('Not ready: '+ '; '.join(problems))
    return signed

def move(storage, entry_id, when):
    datetime.strptime(when,'%Y-%m-%dT%H:%M')
    row=get_entry(storage,entry_id)
    if not row or row['status'] not in ('PLANNED','READY') or row['pin_status']=='PUBLISHED':
        raise ValueError('Only pending unpublished entries can be moved')
    table='pin_schedule' if entry_id>0 else 'carousel_schedule'
    with storage.conn:
        storage.conn.execute(f'UPDATE {table} SET scheduled_at=? WHERE id=?',(when,abs(entry_id)))

def factory_slot_for_entry(storage, entry_id):
    if entry_id <= 0:
        return None
    row=storage.conn.execute("SELECT id FROM campaign_slots WHERE schedule_id=?", (entry_id,)).fetchone()
    return row[0] if row else None


def remove(storage, entry_id):
    """Cancel an unpublished plan and keep its history and library assets."""
    row=get_entry(storage,entry_id)
    if not row or row['status'] not in ('PLANNED','READY') or row['pin_status']=='PUBLISHED':
        raise ValueError('Скасувати можна лише неопублікований активний план.')
    slot_id=factory_slot_for_entry(storage,entry_id)
    if slot_id is not None:
        # Use the existing factory withdrawal workflow, including its evidence checks.
        ContentFactory(storage).reopen_review(slot_id)
        return
    table='pin_schedule' if entry_id>0 else 'carousel_schedule'
    with storage.conn:
        result=storage.conn.execute(f"UPDATE {table} SET status='CANCELLED' WHERE id=? AND status IN ('PLANNED','READY')",(abs(entry_id),))
        if result.rowcount!=1:
            raise ValueError('Статус плану змінився. Оновіть список.')


def delete_entry(storage, entry_id):
    """Delete a local schedule only; tracking allocations and published history survive."""
    row=get_entry(storage,entry_id)
    if not row:
        raise ValueError('Запис уже не існує.')
    if row['status']=='PUBLISHED':
        raise ValueError('Історію підтверджених публікацій видаляти не можна.')
    if row['status'] not in ('PLANNED','READY','CANCELLED'):
        raise ValueError('Неприпустимий статус плану.')
    if factory_slot_for_entry(storage,entry_id) is not None:
        raise ValueError('Спочатку скасуйте цей план, щоб повернути слот Фабрики контенту на погодження.')
    table='pin_schedule' if entry_id>0 else 'carousel_schedule'
    with storage.conn:
        result=storage.conn.execute(f"DELETE FROM {table} WHERE id=? AND status IN ('PLANNED','READY','CANCELLED')",(abs(entry_id),))
        if result.rowcount!=1:
            raise ValueError('Статус плану змінився. Оновіть список.')

def confirm(storage, entry_id):
    row=get_entry(storage,entry_id)
    if not row or row['status'] not in ('PLANNED','READY'):
        raise ValueError('Only pending entries can be confirmed')
    problems=issues(storage,row)
    if problems: raise ValueError('; '.join(problems))
    if row['kind']=='PIN':
        storage.confirm_manual_publication(entry_id)
    else:
        with storage.conn:
            storage.conn.execute("UPDATE carousel_schedule SET status='PUBLISHED' WHERE id=? AND status IN ('PLANNED','READY')",(-entry_id,))
