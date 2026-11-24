"""Additive Content Factory migration, with no implicit executescript commits."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

VERSION = 1
SCHEMA = """
CREATE TABLE content_sources (
 id INTEGER PRIMARY KEY,
 source_type TEXT NOT NULL CHECK(source_type IN ('RSS_ARTICLE','MANUAL_ARTICLE','POD','KDP','FREE_TOOL','AFFILIATE')),
 canonical_url TEXT NOT NULL, guid TEXT, title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
 topic TEXT NOT NULL DEFAULT '', board_id INTEGER REFERENCES boards(id) ON DELETE SET NULL,
 product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
 image_url TEXT NOT NULL DEFAULT '', published_at TEXT, updated_at TEXT NOT NULL,
 feed_url TEXT, fetch_status TEXT NOT NULL DEFAULT 'MANUAL', last_seen_at TEXT,
 UNIQUE(source_type,canonical_url)
);
CREATE TABLE content_source_aliases (
 feed_url TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('GUID','URL')),
 value TEXT NOT NULL, source_id INTEGER NOT NULL REFERENCES content_sources(id) ON DELETE CASCADE,
 PRIMARY KEY(feed_url,kind,value)
);
CREATE TABLE content_feed_refresh (
 feed_url TEXT PRIMARY KEY, attempted_at TEXT NOT NULL, succeeded_at TEXT,
 status TEXT NOT NULL CHECK(status IN ('OK','ERROR')), message TEXT NOT NULL
);
CREATE TABLE content_campaigns (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, month TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','EXPORTED')),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(name,month)
);
CREATE TABLE campaign_slots (
 id INTEGER PRIMARY KEY, campaign_id INTEGER NOT NULL REFERENCES content_campaigns(id) ON DELETE CASCADE,
 slot_index INTEGER NOT NULL CHECK(slot_index BETWEEN 1 AND 12),
 source_id INTEGER REFERENCES content_sources(id) ON DELETE SET NULL,
 pin_id INTEGER UNIQUE REFERENCES pins(id) ON DELETE SET NULL,
 board_id INTEGER REFERENCES boards(id) ON DELETE SET NULL,
 content_type TEXT NOT NULL CHECK(content_type IN ('EDUCATIONAL','LEAD_GEN','PRODUCT')),
 scheduled_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'DRAFT'
 CHECK(status IN ('DRAFT','APPROVED','EXPORTED')),
 schedule_id INTEGER REFERENCES pin_schedule(id) ON DELETE SET NULL,
 UNIQUE(campaign_id,slot_index)
);
CREATE TABLE keyword_evidence (
 id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES content_sources(id) ON DELETE CASCADE,
 phrase TEXT NOT NULL, evidence_source TEXT NOT NULL, evidence_url TEXT,
 observed_at TEXT NOT NULL, verification_status TEXT NOT NULL
 CHECK(verification_status IN ('UNVERIFIED','VERIFIED')),
 search_volume INTEGER CHECK(search_volume IS NULL OR (typeof(search_volume)='integer' AND search_volume>=0)),
 competition REAL CHECK(competition IS NULL OR competition>=0), metric_definition TEXT,
 CHECK((search_volume IS NULL AND competition IS NULL) OR
 (verification_status='VERIFIED' AND evidence_url IS NOT NULL AND length(evidence_url)>0
 AND metric_definition IS NOT NULL AND length(metric_definition)>0))
);
CREATE TABLE pin_copy_drafts (
 id INTEGER PRIMARY KEY, slot_id INTEGER NOT NULL REFERENCES campaign_slots(id) ON DELETE CASCADE,
 title TEXT NOT NULL, description TEXT NOT NULL, alt_text TEXT NOT NULL DEFAULT '',
 disclosure TEXT NOT NULL DEFAULT '', generator TEXT NOT NULL,
 verification_status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(verification_status='DRAFT'),
 image_review_hash TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL,
 created_at TEXT NOT NULL, UNIQUE(slot_id,revision)
);
CREATE TABLE content_reviews (
 id INTEGER PRIMARY KEY, slot_id INTEGER NOT NULL REFERENCES campaign_slots(id) ON DELETE CASCADE,
 checks_json TEXT NOT NULL, decision TEXT NOT NULL CHECK(decision IN ('APPROVED','CHANGES_REQUESTED')),
 fingerprint TEXT NOT NULL, reviewer_note TEXT NOT NULL, reviewed_at TEXT NOT NULL
);
CREATE TABLE rss_publication_ledger (
 id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES content_sources(id) ON DELETE CASCADE,
 feed_url TEXT, canonical_url TEXT NOT NULL, board_id INTEGER REFERENCES boards(id) ON DELETE SET NULL,
 local_pin_id INTEGER REFERENCES pins(id) ON DELETE SET NULL, feed_seen_at TEXT,
 entry_kind TEXT NOT NULL DEFAULT 'SOURCE' CHECK(entry_kind IN ('SOURCE','CREATIVE')),
 creative_hash TEXT NOT NULL DEFAULT '',
 eligibility_state TEXT NOT NULL CHECK(eligibility_state IN ('RSS_ELIGIBLE','NOT_IN_FEED')),
 pinterest_connection_state TEXT NOT NULL DEFAULT 'PINTEREST_CONNECTION_UNKNOWN'
 CHECK(pinterest_connection_state IN ('PINTEREST_CONNECTION_UNKNOWN','CONNECTED_CONFIRMED')),
 remote_publication_state TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(remote_publication_state IN ('UNKNOWN','PUBLISHED_CONFIRMED')),
 evidence_ref TEXT, checked_at TEXT,
 CHECK((remote_publication_state='UNKNOWN' AND pinterest_connection_state='PINTEREST_CONNECTION_UNKNOWN')
 OR (evidence_ref IS NOT NULL AND length(evidence_ref)>0))
);
CREATE UNIQUE INDEX ux_content_feed_ledger ON rss_publication_ledger(source_id) WHERE entry_kind='SOURCE';
CREATE UNIQUE INDEX ux_content_pin_ledger ON rss_publication_ledger(local_pin_id) WHERE local_pin_id IS NOT NULL;
CREATE UNIQUE INDEX ux_content_creative_ledger ON rss_publication_ledger(canonical_url,creative_hash) WHERE creative_hash!='';
CREATE INDEX idx_content_slot_source ON campaign_slots(source_id);
CREATE INDEX idx_content_review_slot ON content_reviews(slot_id,id);
CREATE INDEX idx_content_keyword_source ON keyword_evidence(source_id);
"""


def needs_migration(conn: sqlite3.Connection) -> bool:
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='content_schema_migrations'").fetchone()
    return not exists or not conn.execute(
        "SELECT 1 FROM content_schema_migrations WHERE version=?", (VERSION,)).fetchone()


def backup_before_migration(conn: sqlite3.Connection, path: Path) -> Path | None:
    """Snapshot an existing workspace before *any* startup schema changes."""
    if not needs_migration(conn) or not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone():
        return None
    from .workspace import backup_database
    destination = path.with_name(path.name + '.pre-content-factory.sqlite3')
    if destination.exists():
        destination = path.with_name(path.name + f'.pre-content-factory-{uuid4().hex[:8]}.sqlite3')
    return backup_database(conn, destination)


def migrate(conn: sqlite3.Connection) -> None:
    # SAVEPOINT also makes direct use atomic; a caller's transaction is never committed.
    conn.execute('SAVEPOINT content_factory_migration')
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS content_schema_migrations '
                     '(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
        if needs_migration(conn):
            for statement in SCHEMA.split(';'):
                if statement.strip():
                    conn.execute(statement)
            conn.execute("INSERT INTO content_schema_migrations VALUES (?,datetime('now'))", (VERSION,))
        conn.execute('RELEASE content_factory_migration')
    except Exception:
        conn.execute('ROLLBACK TO content_factory_migration')
        conn.execute('RELEASE content_factory_migration')
        raise
