"""Read-only Pinterest import. No browser scraping, credentials on disk or remote writes."""
import json
import re
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from zipfile import ZipFile
from .storage import utc_now

MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 10000
SCHEMA = (
    """CREATE TABLE IF NOT EXISTS pinterest_remote_boards (
    remote_id TEXT PRIMARY KEY, board_id INTEGER REFERENCES boards(id) ON DELETE SET NULL,
    account TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS pinterest_remote_pins (
    remote_id TEXT PRIMARY KEY, pin_id INTEGER UNIQUE REFERENCES pins(id) ON DELETE SET NULL,
    remote_board_id TEXT NOT NULL, account TEXT NOT NULL, remote_url TEXT NOT NULL,
    remote_created_at TEXT NOT NULL, media_type TEXT NOT NULL, media_url TEXT NOT NULL,
    source TEXT NOT NULL, imported_at TEXT NOT NULL)""",
)

def migrate(conn):
    for sql in SCHEMA: conn.execute(sql)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None

def api_get(token, endpoint, query=None):
    if endpoint not in ('user_account','boards','pins'):
        raise ValueError('Unsupported read endpoint')
    if not token or any(c.isspace() for c in token):
        raise ValueError('Введіть чинний access token.')
    url='https://api.pinterest.com/v5/'+endpoint
    if query: url+='?'+urlencode(query)
    req=Request(url,headers={'Authorization':'Bearer '+token,'Accept':'application/json'},method='GET')
    try:
        with build_opener(NoRedirect()).open(req,timeout=15) as response:
            data=response.read(MAX_BYTES+1)
    except HTTPError as exc:
        raise ValueError(f'Pinterest API: HTTP {exc.code}. Перевірте дозволи або ліміти.') from None
    except (URLError,TimeoutError,OSError):
        raise ValueError('Pinterest API недоступний. Перевірте з’єднання.') from None
    if len(data)>MAX_BYTES: raise ValueError('Відповідь API завелика.')
    try: result=json.loads(data)
    except (ValueError,UnicodeError): raise ValueError('Некоректна JSON-відповідь API.') from None
    if not isinstance(result,dict): raise ValueError('Невідома структура відповіді API.')
    return result

def pages(token, endpoint, get=api_get):
    items=[]; seen=set(); query={'page_size':100}; deadline=time.monotonic()+60
    if endpoint=='pins': query['pin_filter']='exclude_repins'
    for _ in range(100):
        if time.monotonic()>deadline: raise ValueError('Ліміт часу запиту API. Спробуйте ще раз.')
        result=get(token,endpoint,query)
        batch=result.get('items')
        if not isinstance(batch,list) or not all(isinstance(x,dict) for x in batch):
            raise ValueError('Некоректний список API.')
        items.extend(batch)
        if len(items)>MAX_ROWS: raise ValueError('Перевищено ліміт імпорту.')
        bookmark=result.get('bookmark')
        if not bookmark: return items
        if not isinstance(bookmark,str) or bookmark in seen:
            raise ValueError('Некоректна пагінація API.')
        seen.add(bookmark); query['bookmark']=bookmark
    raise ValueError('Перевищено ліміт сторінок API.')

def _id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[0-9]{1,30}',value):
        raise ValueError('Pinterest ID має бути цифровим рядком без втрати точності.')
    return value

def _text(value):
    return value.strip() if isinstance(value,str) else ''

def _account(value):
    value=_text(value).lstrip('@')
    if not re.fullmatch(r'[A-Za-z0-9_\-]{1,100}',value):
        raise ValueError('Вкажіть точне ім’я профілю Pinterest (username).')
    return value.casefold()

def _media(media):
    if not isinstance(media,dict): return '', ''
    kind=_text(media.get('media_type'))
    images=media.get('images')
    urls=[]
    if isinstance(images,dict):
        for image in images.values():
            if isinstance(image,dict):
                url=_text(image.get('url'))
                try:
                    p=urlsplit(url)
                    if p.scheme=='https' and p.hostname=='i.pinimg.com' and not p.username and not p.password:
                        urls.append((image.get('width',0) if isinstance(image.get('width'),int) else 0,url))
                except ValueError: pass
    return kind,max(urls,default=(0,''))[1]

def fetch_snapshot(token,expected,get=api_get):
    expected=_account(expected)
    account=_account(get(token,'user_account').get('username'))
    if account!=expected: raise ValueError('Токен належить іншому акаунту. Імпорт заблоковано.')
    boards=pages(token,'boards',get)
    pins=pages(token,'pins',get)
    # Only own public boards and non-repinned, non-ad-only pins.
    own=[b for b in boards if isinstance(b.get('owner'),dict)
         and _text(b['owner'].get('username')).casefold()==account
         and b.get('privacy')=='PUBLIC']
    board_ids={_id(b.get('id')) for b in own}
    selected=[]
    for p in pins:
        if p.get('board_id') not in board_ids or p.get('parent_pin_id') or p.get('is_owner') is False or p.get('is_removable') is True:
            continue
        kind,url=_media(p.get('media'))
        selected.append({'id':_id(p.get('id')),'board_id':p['board_id'],'title':_text(p.get('title')),
            'description':_text(p.get('description')),'link':_text(p.get('link')),
            'created_at':_text(p.get('created_at')),'media_type':kind,'media_url':url})
    return {'account':account,'boards':[{'id':b['id'],'name':_text(b.get('name')),
            'description':_text(b.get('description'))} for b in own],
            'pins':selected,'source':'API_READ'}

def read_manifest(path):
    """Inspect only named, normalized import manifest; never extract a ZIP."""
    path=Path(path)
    if path.suffix.lower()=='.zip':
        with ZipFile(path) as z:
            matches=[x for x in z.infolist() if x.filename=='ithutir_pinterest_import.json']
            if len(matches)!=1:
                raise ValueError('Невідомий формат архіву Pinterest. Потрібен зразок офіційного архіву для адаптації; автоматичного імпорту не виконано.')
            if matches[0].file_size>MAX_BYTES: raise ValueError('Маніфест завеликий.')
            data=z.read(matches[0])
    elif path.suffix.lower()=='.json':
        with path.open('rb') as stream: data=stream.read(MAX_BYTES+1)
    else: raise ValueError('Виберіть JSON або ZIP.')
    if len(data)>MAX_BYTES: raise ValueError('Файл завеликий.')
    result=json.loads(data)
    if not isinstance(result,dict) or result.get('format')!='ITHutir Pinterest Import v1':
        raise ValueError('Непідтримуваний формат. Імпорт не виконано.')
    result['source']='USER_ARCHIVE'
    return result

def prepare(storage,snapshot,expected):
    account=_account(expected)
    if _account(snapshot.get('account'))!=account: raise ValueError('Невідповідність акаунта.')
    source=snapshot.get('source')
    if source not in ('API_READ','USER_ARCHIVE'): raise ValueError('Невідоме джерело.')
    boards=snapshot.get('boards'); pins=snapshot.get('pins')
    if not isinstance(boards,list) or not isinstance(pins,list) or len(boards)+len(pins)>MAX_ROWS:
        raise ValueError('Некоректний або завеликий список.')
    if not all(isinstance(x,dict) for x in boards+pins): raise ValueError('Некоректні записи.')
    by_board={}; seen=set()
    for b in boards:
        rid=_id(b.get('id')); name=_text(b.get('name'))
        if rid in by_board or not name: raise ValueError('Дублікат ID дошки або відсутня назва.')
        by_board[rid]=dict(id=rid,name=name,description=_text(b.get('description')))
    existing=storage.all('pins')
    titles={_text(x['title']).casefold() for x in existing}
    known={r[0] for r in storage.conn.execute('SELECT remote_id FROM pinterest_remote_pins')}
    ledger=set()
    for (url,) in storage.conn.execute("SELECT evidence_ref FROM rss_publication_ledger WHERE evidence_ref IS NOT NULL"):
        match=re.search(r'/pin/([0-9]+)/?',url)
        if match: ledger.add(match.group(1))
    new=[]; skipped=0; conflicts=[]
    for pin in pins:
        rid=_id(pin.get('id'))
        if rid in seen: raise ValueError('Повторний Pinterest Pin ID у джерелі.')
        seen.add(rid)
        if rid in known or rid in ledger: skipped+=1; continue
        bid=_id(pin.get('board_id'))
        if bid not in by_board: raise ValueError('Невідома дошка піна.')
        title=_text(pin.get('title')) or 'Pinterest Pin '+rid
        # Existing local records may have no remote ID: never silently merge them.
        if title.casefold() in titles:
            conflicts.append(title); continue
        titles.add(title.casefold())
        new.append(dict(id=rid,board_id=bid,title=title,description=_text(pin.get('description')),
            link=_text(pin.get('link')),created_at=_text(pin.get('created_at')),
            media_type=_text(pin.get('media_type')),media_url=_text(pin.get('media_url'))))
    return dict(account=account,source=source,boards=list(by_board.values()),pins=new,skipped=skipped,conflicts=conflicts)

def apply(storage,snapshot,expected):
    """Append only. PUBLISHED means API-observed or expressly user-attested, not local creation."""
    plan=prepare(storage,snapshot,expected)
    conn=storage.conn
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        mapping={}
        for board in plan['boards']:
            row=conn.execute('SELECT board_id,account FROM pinterest_remote_boards WHERE remote_id=?',(board['id'],)).fetchone()
            if row:
                if row[1]!=plan['account'] or row[0] is None:
                    raise ValueError('Конфлікт прив’язки дошки; потрібна ручна перевірка.')
                mapping[board['id']]=row[0]; continue
            matches=[b for b in storage.all('boards') if b['name'].strip().casefold()==board['name'].casefold()]
            if len(matches)>1: raise ValueError('Неоднозначна локальна дошка: '+board['name'])
            if matches:
                local=matches[0]['id']
                if conn.execute('SELECT 1 FROM pinterest_remote_boards WHERE board_id=?',(local,)).fetchone():
                    raise ValueError('Локальна дошка вже пов’язана з іншим Pinterest ID.')
            else:
                local=conn.execute('INSERT INTO boards(name,description,created_at) VALUES(?,?,?)',
                    (board['name'],board['description'],utc_now())).lastrowid
            conn.execute('INSERT INTO pinterest_remote_boards VALUES(?,?,?)',(board['id'],local,plan['account']))
            mapping[board['id']]=local
        for pin in plan['pins']:
            local=conn.execute("INSERT INTO pins(title,description,destination_url,board_id,status,created_at) VALUES(?,?,?,?,'PUBLISHED',?)",
                (pin['title'],pin['description'],pin['link'],mapping[pin['board_id']],utc_now())).lastrowid
            conn.execute('INSERT INTO pinterest_remote_pins VALUES(?,?,?,?,?,?,?,?,?,?)',
                (pin['id'],local,pin['board_id'],plan['account'],'https://www.pinterest.com/pin/'+pin['id']+'/',
                 pin['created_at'],pin['media_type'],pin['media_url'],plan['source'],utc_now()))
    return plan
