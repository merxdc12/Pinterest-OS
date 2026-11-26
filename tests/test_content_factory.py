"""Phase 1 contracts: migration safety, evidence, review and existing-engine handoff."""
import json
import shutil
import sqlite3
from unittest.mock import patch

import pytest
from PyQt6.QtGui import QImage

from pinterest_os import content_migrations
from pinterest_os.content_factory import ContentFactory
from pinterest_os.content_feed import FEED_URL, parse_feed
from pinterest_os.storage import SCHEMA, Storage
from pinterest_os.workspace import backup_database, verify_database


@pytest.fixture
def factory(tmp_path):
    db = Storage(tmp_path / 'workspace.sqlite3')
    try:
        yield ContentFactory(db)
    finally:
        db.close()


def prepared(factory, tmp_path, *, count=1, source_type='MANUAL_ARTICLE'):
    board = factory.storage.create('boards', name='Engineering', url='https://www.pinterest.com/example/engineering/')
    source = factory.add_source(source_type, 'https://ithutir.com/article', 'Source')
    cid = factory.create_campaign('Monthly batch', '2026-11')
    for index, slot in enumerate(factory.slots(cid)[:count]):
        factory.edit_slot(slot['id'], source_id=source, board_id=board, content_type=slot['content_type'], scheduled_at=slot['scheduled_at'])
        pid = factory.ensure_design_pin(slot['id'])
        image = QImage(1000, 1500, QImage.Format.Format_RGB32)
        image.fill(0xff123400 + index)
        path = tmp_path / f'creative-{pid}.png'
        assert image.save(str(path))
        factory.storage.save_pin_design(pid, '{"version":1}', str(path))
        factory.save_copy(slot['id'], f'Engineering idea {index}', 'An original engineering idea.', 'A green design.',
                          image_review_hash=factory.image_hash(slot['id']))
    return cid, factory.slots(cid)[0]['id']


def legacy(path):
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO pins(title,created_at) VALUES('Keep me','2026-01-01')")
    conn.execute('CREATE TABLE custom_data(value BLOB)')
    conn.execute("INSERT INTO custom_data VALUES(x'010203')")
    conn.commit()
    return conn


def test_additive_migration_backup_restart_restore(tmp_path):
    path = tmp_path / 'legacy.sqlite3'
    original = legacy(path)
    before = original.iterdump()
    before = '\n'.join(before)
    original.close()
    db = Storage(path)
    backup = db.migration_backup
    assert backup.is_file()
    assert verify_database(backup) == (True, 'ok')
    assert db.get('pins', 1)['title'] == 'Keep me'
    assert db.conn.execute('SELECT value FROM custom_data').fetchone()[0] == b'\x01\x02\x03'
    assert db.conn.execute('PRAGMA foreign_key_check').fetchall() == []
    after = '\n'.join(db.conn.iterdump())
    db.close()
    db = Storage(path)
    assert db.migration_backup is None
    assert '\n'.join(db.conn.iterdump()) == after
    db.close()
    restored_path = tmp_path / 'restored.sqlite3'
    shutil.copy2(backup, restored_path)
    with sqlite3.connect(restored_path) as restored:
        assert '\n'.join(restored.iterdump()) == before
    restored = Storage(restored_path)
    assert restored.get('pins', 1)['title'] == 'Keep me'
    restored.close()


def test_migration_failure_rolls_back_entire_startup(tmp_path):
    path = tmp_path / 'legacy.sqlite3'
    conn = legacy(path)
    before = '\n'.join(conn.iterdump())
    conn.close()
    with patch.object(content_migrations, 'SCHEMA', content_migrations.SCHEMA + ';INVALID SQL;'):
        with pytest.raises(sqlite3.Error):
            Storage(path)
    with sqlite3.connect(path) as conn:
        assert '\n'.join(conn.iterdump()) == before
    db = Storage(path)
    assert db.get('pins', 1)['title'] == 'Keep me'
    assert len(list(tmp_path.glob('*.pre-content-factory*.sqlite3'))) == 2
    db.close()


def test_older_schema_columns_are_preserved_and_upgraded(tmp_path):
    path = tmp_path / 'old.sqlite3'
    with sqlite3.connect(path) as conn:
        conn.executescript("""CREATE TABLE products(id INTEGER PRIMARY KEY,name TEXT NOT NULL,target_url TEXT,created_at TEXT);
        CREATE TABLE boards(id INTEGER PRIMARY KEY,name TEXT NOT NULL,url TEXT,created_at TEXT);
        CREATE TABLE pins(id INTEGER PRIMARY KEY,title TEXT,description TEXT,product_id INTEGER,board_id INTEGER,status TEXT,created_at TEXT);
        INSERT INTO pins VALUES(1,'Legacy','','',NULL,'DRAFT','2020-01-01');""")
    db = Storage(path)
    assert db.get('pins', 1)['title'] == 'Legacy'
    assert db.get('pins', 1)['destination_url'] == ''
    assert db.conn.execute('SELECT COUNT(*) FROM campaign_slots').fetchone()[0] == 0
    db.close()


def test_savepoint_failure_does_not_commit_callers_work(factory):
    conn = factory.conn
    with conn:
        conn.execute('DELETE FROM content_schema_migrations')
    conn.execute("INSERT INTO products(name,created_at) VALUES('uncommitted','today')")
    with pytest.raises(sqlite3.Error):
        content_migrations.migrate(conn)  # Existing new tables deliberately conflict.
    assert conn.in_transaction
    conn.rollback()
    assert factory.storage.all('products') == []


def test_campaign_idempotent_and_editable(factory):
    cid = factory.create_campaign('Month', '2026-02', (4, 4, 4))
    assert cid == factory.create_campaign('Month', '2026-02', (6, 3, 3))
    slots = factory.slots(cid)
    assert len(slots) == 12
    assert [s['slot_index'] for s in slots] == list(range(1, 13))
    assert slots[-1]['scheduled_at'] == '2026-02-28T10:00'
    source = factory.add_source('FREE_TOOL', 'https://ithutir.com/tool', 'Tool')
    factory.edit_slot(slots[0]['id'], source_id=source, board_id=None, content_type='LEAD_GEN', scheduled_at='2026-02-15T11:00')
    assert factory.slot(slots[0]['id'])['content_type'] == 'LEAD_GEN'
    with pytest.raises(ValueError):
        factory.edit_slot(slots[0]['id'], source_id=source, board_id=None, content_type='PRODUCT', scheduled_at='2026-03-01T11:00')


@pytest.mark.parametrize('month,mix', [('2026-13', (6, 3, 3)), ('2026-11', (6, 4, 3)), ('2026-11', (-1, 10, 3)), ('2026-11', (6.0, 3, 3))])
def test_invalid_campaign(factory, month, mix):
    with pytest.raises(ValueError):
        factory.create_campaign('Invalid', month, mix)
    assert factory.slots(1) == []


def test_sources_and_keyword_provenance(factory):
    for kind in ('MANUAL_ARTICLE', 'POD', 'KDP', 'FREE_TOOL', 'AFFILIATE'):
        sid = factory.add_source(kind, 'https://ithutir.com/product?utm_source=pinterest', 'A <b>source</b>')
        assert sid == factory.add_source(kind, 'https://ithutir.com/product', 'Another title')
    sid = factory.sources()[0]['id']
    factory.add_keyword(sid, 'arduino tutorial', 'Manual hypothesis', '2026-11-11')
    row = factory.rows('SELECT * FROM keyword_evidence')[0]
    assert row['search_volume'] is None and row['competition'] is None
    assert row['verification_status'] == 'UNVERIFIED'
    with pytest.raises(ValueError, match='verified evidence'):
        factory.add_keyword(sid, 'keyword', 'Guess', '2026-11-11', search_volume=100)
    factory.add_keyword(sid, 'keyword', 'Provider export', '2026-11-11', status='VERIFIED',
                         evidence_url='https://example.com/report', search_volume=0, competition=0.2,
                         metric_definition='Monthly volume, competition 0–1; US Nov 2026')
    assert factory.rows('SELECT search_volume FROM keyword_evidence ORDER BY id DESC')[0]['search_volume'] == 0
    with pytest.raises(sqlite3.IntegrityError), factory.conn:
        factory.conn.execute("INSERT INTO keyword_evidence(source_id,phrase,evidence_source,observed_at,verification_status,search_volume) VALUES(?,'p','o','2026-11-11','VERIFIED',100)", (sid,))


def test_manual_and_optional_ai_copy_need_image_review(factory, tmp_path):
    _, sid = prepared(factory, tmp_path)
    assert 'Do not invent' in factory.seo_prompt(sid)
    factory.import_ai_copy(sid, json.dumps(dict(title='Draft', description='Draft copy', alt_text='Guessed image')))
    draft = factory.copy(sid)
    assert draft['generator'] == 'AI_ASSISTED_IMPORT' and draft['verification_status'] == 'DRAFT'
    assert draft['image_review_hash'] == ''
    assert any('Preview' in issue for issue in factory.checks(sid)[0])
    with pytest.raises(ValueError):
        factory.import_ai_copy(sid, '[]')
    with pytest.raises(ValueError):
        factory.import_ai_copy(sid, '{bad')
    with pytest.raises(ValueError):
        factory.export_slot(sid)


def test_twelve_exports_retry_and_existing_integrations(factory, tmp_path):
    from pinterest_os.csv_io import export_pins
    from pinterest_os.sheets_exchange import export_pin_rows
    cid, sid = prepared(factory, tmp_path, count=12)
    for slot in factory.slots(cid):
        assert factory.ensure_design_pin(slot['id']) == slot['pin_id']
        assert factory.checks(slot['id'])[0] == []
        factory.review(slot['id'], approve=True, note='Editor: image, copy, board and link checked')
        assert factory.export_slot(slot['id']) == slot['pin_id']
        assert factory.export_slot(slot['id']) == slot['pin_id']
    assert len(factory.storage.all('pins')) == 12
    assert factory.conn.execute('SELECT COUNT(*) FROM pin_schedule').fetchone()[0] == 12
    assert factory.conn.execute("SELECT COUNT(*) FROM pins WHERE status='READY'").fetchone()[0] == 12
    assert factory.conn.execute("SELECT status FROM content_campaigns WHERE id=?", (cid,)).fetchone()[0] == 'EXPORTED'
    assert factory.conn.execute("SELECT COUNT(*) FROM rss_publication_ledger WHERE remote_publication_state='UNKNOWN'").fetchone()[0] == 12
    export_pins(factory.storage, tmp_path / 'pins.csv')
    assert (tmp_path / 'pins.csv').is_file()
    tables = export_pin_rows(factory.storage)
    assert tables
    snapshot = backup_database(factory.conn, tmp_path / 'snapshot.sqlite3')
    restored = Storage(snapshot)
    assert len(ContentFactory(restored).slots(cid)) == 12
    assert len(restored.all('pins')) == 12
    assert restored.conn.execute('PRAGMA foreign_key_check').fetchall() == []
    restored.close()


def test_approval_invalidated_by_changes(factory, tmp_path):
    _, sid = prepared(factory, tmp_path)
    factory.review(sid, approve=True, note='Editor')
    image = QImage(1000, 1500, QImage.Format.Format_RGB32)
    image.fill(0xffdd3300)
    image.save(str(factory.image_path(sid)))
    with pytest.raises(ValueError, match='Fresh human approval'):
        factory.export_slot(sid)
    assert factory.conn.execute('SELECT COUNT(*) FROM pin_schedule').fetchone()[0] == 0
    factory.save_copy(sid, 'New copy', 'New description', 'Orange', image_review_hash=factory.image_hash(sid))
    with pytest.raises(ValueError):
        factory.export_slot(sid)
    factory.review(sid, approve=True, note='Editor')
    source = factory.source(factory.slot(sid)['source_id'])
    factory.update_source_metadata(source['id'], topic='Changed context')
    with pytest.raises(ValueError):
        factory.export_slot(sid)


def test_duplicate_same_image_url_but_different_creative_allowed(factory, tmp_path):
    cid, sid = prepared(factory, tmp_path, count=2)
    second = factory.slots(cid)[1]['id']
    assert not factory.duplicate_candidates(second, factory.image_hash(second))
    shutil.copyfile(factory.image_path(sid), factory.image_path(second))
    assert factory.duplicate_candidates(second, factory.image_hash(second)) == [factory.slot(sid)['pin_id']]
    factory.save_copy(second, 'Another title', 'Another description', 'Green', image_review_hash=factory.image_hash(second))
    with pytest.raises(ValueError, match='Identical creative'):
        factory.review(second, approve=True, note='Editor')


def test_legacy_pin_participates_in_duplicate_detection(factory, tmp_path):
    _, sid = prepared(factory, tmp_path)
    pid = factory.storage.create('pins', title='Legacy', destination_url='https://ithutir.com/article?utm_source=old#top')
    factory.storage.save_pin_design(pid, '{"version":1}', str(factory.image_path(sid)))
    assert factory.duplicate_candidates(sid, factory.image_hash(sid)) == [pid]


def test_affiliate_disclosure_required_in_description(factory, tmp_path):
    _, sid = prepared(factory, tmp_path, source_type='AFFILIATE')
    with pytest.raises(ValueError, match='affiliate disclosure'):
        factory.review(sid, approve=True, note='Editor')
    factory.save_copy(sid, 'Product', 'Affiliate link. Product details.', 'Green design.', disclosure='Affiliate link.',
                      image_review_hash=factory.image_hash(sid))
    factory.review(sid, approve=True, note='Editor')
    factory.export_slot(sid)


def test_export_rolls_back_pin_calendar_and_ledger_on_failure(factory, tmp_path):
    _, sid = prepared(factory, tmp_path)
    factory.review(sid, approve=True, note='Editor')
    with factory.conn:
        factory.conn.execute("CREATE TRIGGER fail_ledger BEFORE INSERT ON rss_publication_ledger BEGIN SELECT RAISE(ABORT,'injected failure'); END")
    with pytest.raises(sqlite3.Error):
        factory.export_slot(sid)
    assert factory.storage.get('pins', factory.slot(sid)['pin_id'])['status'] == 'DRAFT'
    assert factory.slot(sid)['status'] == 'APPROVED'
    assert factory.conn.execute('SELECT COUNT(*) FROM pin_schedule').fetchone()[0] == 0


def test_calendar_conflict_prevents_export(factory, tmp_path):
    _, sid = prepared(factory, tmp_path)
    slot = factory.slot(sid)
    other = factory.storage.create('pins', title='Other', board_id=slot['board_id'])
    factory.storage.create_schedule(other, slot['scheduled_at'])
    factory.review(sid, approve=True, note='Editor')
    with pytest.raises(ValueError, match='Calendar conflict'):
        factory.export_slot(sid)
    assert factory.slot(sid)['status'] == 'APPROVED'


def test_missing_corrupt_wrong_size_image(factory, tmp_path):
    _, sid = prepared(factory, tmp_path)
    path = factory.image_path(sid)
    path.write_bytes(b'not an image')
    with pytest.raises(ValueError, match='readable'):
        factory.image_hash(sid)
    small = QImage(10, 10, QImage.Format.Format_RGB32)
    small.save(str(path))
    with pytest.raises(ValueError, match='1000'):
        factory.image_hash(sid)
    path.unlink()
    with pytest.raises(ValueError, match='missing'):
        factory.image_hash(sid)


def test_publication_evidence_never_inferred_from_feed_or_export(factory, tmp_path):
    _, sid = prepared(factory, tmp_path)
    factory.review(sid, approve=True, note='Editor')
    factory.export_slot(sid)
    ledger = factory.rows('SELECT * FROM rss_publication_ledger')[0]
    assert ledger['pinterest_connection_state'] == 'PINTEREST_CONNECTION_UNKNOWN'
    assert ledger['remote_publication_state'] == 'UNKNOWN'
    with pytest.raises(ValueError):
        factory.confirm_publication(ledger['id'], 'https://example.com/pin/123/')
    factory.confirm_publication(ledger['id'], 'https://www.pinterest.com/pin/123456/')
    ledger = factory.rows('SELECT * FROM rss_publication_ledger')[0]
    assert ledger['remote_publication_state'] == 'PUBLISHED_CONFIRMED'
    assert ledger['pinterest_connection_state'] == 'PINTEREST_CONNECTION_UNKNOWN'
    with pytest.raises(sqlite3.IntegrityError), factory.conn:
        factory.conn.execute('UPDATE rss_publication_ledger SET evidence_ref=NULL')


def test_campaign_analytics_no_invented_attribution_or_multiplied_money(factory, tmp_path):
    cid, sid = prepared(factory, tmp_path)
    pid = factory.slot(sid)['pin_id']
    empty = factory.campaign_metrics(cid)
    assert empty['outbound_clicks'] is None and empty['currencies'] == {}
    with factory.conn:
        factory.conn.execute("INSERT INTO pinterest_metrics VALUES('2026-11-01',?,100,7,2)", (pid,))
        factory.conn.executemany('INSERT INTO business_metrics VALUES(?,?,?,?,?,?,?)',
                                [('2026-11-01', pid, 'USD', 5, 2, 1000, 100), ('2026-11-02', pid, 'USD', 5, 1, 500, 50)])
    session = factory.storage.start_session()
    factory.storage.save_elapsed(session, 60, pin_id=pid)
    result = factory.campaign_metrics(cid)
    assert result['outbound_clicks'] == 7
    assert result['currencies']['USD']['revenue_cents'] == 1500
    assert result['currencies']['USD']['conversions'] == 3
    assert result['time_seconds'] == 60
    assert 'not profit' in result['attribution']


def test_delete_factory_pin_retains_feed_source_and_integrity(factory, tmp_path):
    cid, sid = prepared(factory, tmp_path)
    factory.review(sid, approve=True, note='Editor')
    digest = factory.image_hash(sid)
    pid = factory.export_slot(sid)
    factory.storage.delete_pin(pid)
    assert factory.conn.execute('PRAGMA foreign_key_check').fetchall() == []
    assert factory.rows('SELECT * FROM rss_publication_ledger')[0]['creative_hash'] == digest
    first, second = factory.slots(cid)[:2]
    factory.edit_slot(second['id'], source_id=first['source_id'], board_id=first['board_id'],
                      content_type=second['content_type'], scheduled_at=second['scheduled_at'])
    assert 'pin removed' in factory.duplicate_candidates(second['id'], digest)[0]
    with pytest.raises(ValueError, match='deleted'):
        factory.export_slot(sid)


def test_manual_publishing_enforces_factory_approval_and_preserves_unknown_ledger(factory, tmp_path):
    _, sid = prepared(factory, tmp_path)
    pid = factory.slot(sid)['pin_id']
    schedule = factory.storage.create_schedule(pid, '2026-11-02T14:00')
    with pytest.raises(ValueError, match='Content Factory'):
        factory.storage.confirm_manual_publication(schedule)
    factory.storage.delete_schedule(schedule)
    factory.review(sid, approve=True, note='Editor')
    factory.export_slot(sid)
    factory.storage.update('pins', pid, description='Changed after approval')
    schedule = factory.slot(sid)['schedule_id']
    with pytest.raises(ValueError, match='metadata differs'):
        factory.storage.confirm_manual_publication(schedule)
    factory.reopen_review(sid)
    assert factory.storage.get_schedule(schedule)['status'] == 'CANCELLED'
    factory.review(sid, approve=True, note='Editor reviewed again')
    factory.export_slot(sid)
    schedule = factory.slot(sid)['schedule_id']
    factory.storage.confirm_manual_publication(schedule)
    assert factory.storage.get('pins', pid)['status'] == 'PUBLISHED'
    assert factory.rows('SELECT * FROM rss_publication_ledger')[0]['remote_publication_state'] == 'UNKNOWN'
    with pytest.raises(ValueError, match='Published content'):
        factory.reopen_review(sid)


def test_rss_source_to_export_keeps_article_and_creative_evidence_separate(factory, tmp_path):
    factory.refresh_feed(lambda: b'<rss><channel><item><title>Article</title><link>https://ithutir.com/article</link><guid>one</guid></item></channel></rss>')
    rss_source = factory.sources()[0]['id']
    source_ledger = factory.rows("SELECT * FROM rss_publication_ledger WHERE entry_kind='SOURCE'")[0]
    factory.confirm_publication(source_ledger['id'], 'https://www.pinterest.com/pin/123456/')
    _, sid = prepared(factory, tmp_path)
    slot = factory.slot(sid)
    factory.edit_slot(sid, source_id=rss_source, board_id=slot['board_id'], content_type=slot['content_type'], scheduled_at=slot['scheduled_at'])
    factory.review(sid, approve=True, note='Editor checked article creative')
    pid = factory.export_slot(sid)
    rows = factory.rows('SELECT * FROM rss_publication_ledger ORDER BY id')
    assert [r['remote_publication_state'] for r in rows] == ['PUBLISHED_CONFIRMED', 'UNKNOWN']
    assert all(r['pinterest_connection_state'] == 'PINTEREST_CONNECTION_UNKNOWN' for r in rows)
    factory.storage.delete_pin(pid)
    assert len(factory.rows('SELECT * FROM rss_publication_ledger')) == 2
    assert factory.conn.execute('PRAGMA foreign_key_check').fetchall() == []


def test_full_project_restore_retains_factory_review_and_assets(factory, tmp_path):
    from pinterest_os.project_files import create_project, backup_project, restore_project, DB_NAME
    _, sid = prepared(factory, tmp_path)
    factory.review(sid, approve=True, note='Editor')
    pid = factory.export_slot(sid)
    folder = create_project(factory.conn, tmp_path / 'portable')
    archive = backup_project(folder, tmp_path / 'portable.zip')
    restored_folder = restore_project(archive, tmp_path / 'restored')
    db = Storage(restored_folder / DB_NAME)
    try:
        restored = ContentFactory(db)
        assert restored.image_path(sid).is_file()
        assert restored.publication_issues(pid) == []
        assert restored.export_slot(sid) == pid
        assert db.conn.execute('SELECT COUNT(*) FROM pin_schedule').fetchone()[0] == 1
    finally:
        db.close()


@pytest.mark.parametrize('metrics', [dict(search_volume=-1), dict(search_volume=1.5),
                                    dict(competition=float('nan')), dict(competition=float('inf'))])
def test_keyword_measurements_must_be_finite_and_well_typed(factory, metrics):
    sid = factory.add_source('MANUAL_ARTICLE', 'https://ithutir.com/article', 'Article')
    with pytest.raises(ValueError):
        factory.add_keyword(sid, 'keyword', 'Provider', '2026-11-11', status='VERIFIED',
                            evidence_url='https://example.com/evidence', metric_definition='Monthly US observations', **metrics)


def test_plan_cancel_and_delete_keep_factory_consistent(factory,tmp_path):
    from pinterest_os import content_plan as plan
    _,sid=prepared(factory,tmp_path)
    factory.review(sid,approve=True,note='Editor')
    pid=factory.export_slot(sid)
    entry=factory.slot(sid)['schedule_id']
    with pytest.raises(ValueError):
        plan.delete_entry(factory.storage,entry)
    plan.remove(factory.storage,entry)
    assert plan.get_entry(factory.storage,entry)['status']=='CANCELLED'
    assert factory.slot(sid)['status']=='DRAFT'
    assert factory.slot(sid)['schedule_id'] is None
    plan.delete_entry(factory.storage,entry)
    assert factory.storage.get('pins',pid)
    assert factory.storage.get_pin_design(pid)
    factory.review(sid,approve=True,note='Editor reapproved')
    assert factory.export_slot(sid)==pid
    assert factory.slot(sid)['schedule_id'] is not None
