"""Persistent tracking IDs with cross-workspace collision resistance. No network or publishing actions."""
from .utm import marketing_url, new_tracking_id, read_tracking_id
from .storage import utc_now

SCHEMA = """CREATE TABLE IF NOT EXISTS pin_tracking (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 pin_id INTEGER UNIQUE REFERENCES pins(id) ON DELETE SET NULL,
 original_url TEXT NOT NULL,
 marketing_url TEXT NOT NULL,
 campaign TEXT NOT NULL,
 term TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL
)"""

def tracking_record(storage, pin_id):
    row = storage.conn.execute(
        "SELECT id,pin_id,original_url,marketing_url,campaign,term,created_at FROM pin_tracking WHERE pin_id=?",
        (pin_id,)).fetchone()
    if row is None:
        return None
    result = dict(zip(("id","pin_id","original_url","marketing_url","campaign","term","created_at"), row))
    result["tracking_id"] = read_tracking_id(result["marketing_url"], "pint")
    return result

def register_pin(storage, pin_id, campaign, term=""):
    """Explicit atomic allocation; existing published URLs cannot be rewritten."""
    conn = storage.conn
    if conn.in_transaction:
        raise ValueError("Tracking allocation requires its own transaction")
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        pin = storage.get("pins", pin_id)
        if not pin:
            raise ValueError("Pin not found")
        existing = tracking_record(storage, pin_id)
        original = pin["destination_url"]
        if existing and (existing["original_url"], existing["campaign"], existing["term"]) == (original, campaign, term):
            return existing
        if pin["status"] == "PUBLISHED":
            raise ValueError("Published pin tracking is immutable; create a new pin")
        if existing:
            # Never silently change attribution under an issued identifier.
            raise ValueError("Tracking already allocated with different details; create a new pin")
        # Validate before allocating; the real ID is assigned by SQLite.
        marketing_url(original, "pint", campaign, "pint_000001", term)
        cursor = conn.execute(
            "INSERT INTO pin_tracking(pin_id,original_url,marketing_url,campaign,term,created_at) VALUES(?,?,?,?,?,?)",
            (pin_id, original, "", campaign, term, utc_now()))
        tracking_id = new_tracking_id("pint")
        url = marketing_url(original, "pint", campaign, tracking_id, term)
        conn.execute("UPDATE pin_tracking SET marketing_url=? WHERE id=?", (url, cursor.lastrowid))
        return tracking_record(storage, pin_id)
