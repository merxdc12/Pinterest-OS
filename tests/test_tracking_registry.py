import pytest
from pinterest_os.storage import Storage
from pinterest_os.tracking_registry import register_pin, tracking_record

def new_pin(s, url="https://ithutir.com/a"):
    return s.create("pins", title="Test", destination_url=url)

def test_persistence_and_no_reuse(tmp_path):
    path = tmp_path / "test.sqlite3"
    s = Storage(path)
    pin = new_pin(s)
    first = register_pin(s, pin, "electronics")
    assert first["tracking_id"].startswith("pint_")
    assert len(first["tracking_id"]) == 44
    assert register_pin(s, pin, "electronics") == first
    assert s.get("pins", pin)["destination_url"] == first["original_url"]
    s.conn.close()
    s = Storage(path)
    assert tracking_record(s, pin) == first
    s.delete_pin(pin)
    second = register_pin(s, new_pin(s), "electronics")
    assert second["tracking_id"] != first["tracking_id"]
    assert s.conn.execute("SELECT pin_id FROM pin_tracking WHERE id=1").fetchone() == (None,)

def test_external_rejected_and_atomic(tmp_path):
    s = Storage(tmp_path / "test.sqlite3")
    with pytest.raises(ValueError):
        register_pin(s, new_pin(s, "https://amazon.com/a?tag=example"), "electronics")
    assert s.conn.execute("SELECT count(*) FROM pin_tracking").fetchone()[0] == 0
    assert register_pin(s, new_pin(s), "electronics")["tracking_id"].startswith("pint_")

def test_immutable_details(tmp_path):
    s = Storage(tmp_path / "test.sqlite3")
    pin = new_pin(s)
    first = register_pin(s, pin, "electronics")
    with pytest.raises(ValueError):
        register_pin(s, pin, "other")
    assert tracking_record(s, pin) == first

def test_published_pin_not_retroactively_registered(tmp_path):
    s = Storage(tmp_path / "test.sqlite3")
    pin = s.create("pins", title="Published", destination_url="https://ithutir.com/a", status="PUBLISHED")
    with pytest.raises(ValueError):
        register_pin(s, pin, "electronics")
    assert tracking_record(s, pin) is None


def test_independent_workspaces_and_restored_snapshot(tmp_path):
    from pinterest_os.workspace import backup_database
    a = Storage(tmp_path / "a.sqlite3")
    b = Storage(tmp_path / "b.sqlite3")
    backup_database(a.conn, tmp_path / "restored.sqlite3")
    restored = Storage(tmp_path / "restored.sqlite3")
    codes = [register_pin(db, new_pin(db), "electronics")["tracking_id"]
             for db in (a, b, restored)]
    assert len(set(codes)) == 3


def test_legacy_code_preserved(tmp_path):
    s = Storage(tmp_path / "legacy.sqlite3")
    pin = new_pin(s)
    original = "https://ithutir.com/a"
    from pinterest_os.utm import marketing_url
    url = marketing_url(original, "pint", "electronics", "pint_000001")
    with s.conn:
        s.conn.execute("INSERT INTO pin_tracking(pin_id,original_url,marketing_url,campaign,created_at) VALUES(?,?,?,?,?)",
                       (pin, original, url, "electronics", "2026-11-24"))
    assert register_pin(s, pin, "electronics")["tracking_id"] == "pint_000001"
    assert tracking_record(s, pin)["marketing_url"] == url
