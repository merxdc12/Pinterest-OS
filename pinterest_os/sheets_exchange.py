"""Validated, append-only local pin imports and read-only export snapshots."""
from __future__ import annotations
from .csv_io import FIELDS as PIN_FIELDS
from .storage import utc_now

TIME_FIELDS = ("entry_id","session_id","task","pin_id","product_id_snapshot",
               "product_name_snapshot","attribution_known","seconds","created_at")
METRIC_FIELDS = ("date","pin_id","impressions","outbound_clicks","saves")


def parse_pin_rows(rows, storage):
    if not rows or list(rows[0]) != list(PIN_FIELDS):
        raise ValueError("Expected pin columns: " + ", ".join(PIN_FIELDS))
    if len(rows) > 10001:
        raise ValueError("Too many pin rows (max 10000)")
    boards = {row["name"]: row["id"] for row in storage.all("boards")}
    products = {row["name"]: row["id"] for row in storage.all("products")}
    result = []
    for index, values in enumerate(rows[1:], 2):
        if len(values) > len(PIN_FIELDS):
            raise ValueError(f"Row {index}: too many cells")
        record = dict(zip(PIN_FIELDS, list(values) + [""] * (len(PIN_FIELDS) - len(values))))
        title = record["title"].strip()
        status = record["status"].strip() or "DRAFT"
        board = record["board"].strip()
        product = record["product"].strip()
        if not title or len(title) > 300:
            raise ValueError(f"Row {index}: title required (max 300 chars)")
        if status not in {"DRAFT", "IN_REVIEW", "READY", "PUBLISHED"}:
            raise ValueError(f"Row {index}: invalid status")
        if status == "PUBLISHED":
            raise ValueError(f"Row {index}: PUBLISHED cannot be imported as verified; use DRAFT")
        if board and board not in boards:
            raise ValueError(f"Row {index}: unknown board '{board}'")
        if product and product not in products:
            raise ValueError(f"Row {index}: unknown product '{product}'")
        if len(record["description"]) > 5000 or len(record["destination_url"]) > 4096:
            raise ValueError(f"Row {index}: text too long")
        result.append((title, record["description"], record["destination_url"],
                       status, boards.get(board), products.get(product), utc_now()))
    return result


def import_pin_rows(storage, records):
    with storage.conn:
        storage.conn.executemany(
            """INSERT INTO pins(title,description,destination_url,status,board_id,product_id,created_at)
               VALUES(?,?,?,?,?,?,?)""", records)
    return len(records)


def export_pin_rows(storage):
    boards = {r["id"]: r["name"] for r in storage.all("boards")}
    products = {r["id"]: r["name"] for r in storage.all("products")}
    return [{**{key: pin.get(key) or "" for key in PIN_FIELDS[:4]},
             "board": boards.get(pin.get("board_id"), ""),
             "product": products.get(pin.get("product_id"), "")}
            for pin in storage.all("pins")]


def export_time_rows(storage):
    query = """SELECT id,session_id,task,pin_id,product_id_snapshot,
                      product_name_snapshot,attribution_known,seconds,created_at
               FROM time_entries ORDER BY id"""
    return [dict(zip(TIME_FIELDS, ("" if v is None else v for v in row)))
            for row in storage.conn.execute(query)]


def export_metric_rows(storage):
    return [dict(zip(METRIC_FIELDS, row)) for row in storage.conn.execute(
        """SELECT date,pin_id,impressions,outbound_clicks,saves
           FROM pinterest_metrics ORDER BY date,pin_id""")]


def ensure_new_pins(storage, records):
    """Fail closed on duplicate metadata; do not silently re-import a worksheet."""
    existing = {
        (r["title"], r["description"], r["destination_url"], r["status"],
         r["board_id"], r["product_id"])
        for r in storage.all("pins")
    }
    seen = set()
    for row in records:
        signature = row[:6]
        if signature in existing or signature in seen:
            raise ValueError("Duplicate pin detected; import cancelled to avoid duplicate records")
        seen.add(signature)


def parse_metric_rows(rows, storage):
    """Validate full import before any SQLite mutation; local pin IDs only."""
    from datetime import date
    if not rows or list(rows[0]) != list(METRIC_FIELDS):
        raise ValueError("Expected metric columns: " + ", ".join(METRIC_FIELDS))
    if len(rows) > 10001:
        raise ValueError("Too many metric rows")
    pins = {int(pin["id"]) for pin in storage.all("pins")}
    seen = set()
    parsed = []
    for index, values in enumerate(rows[1:], 2):
        if len(values) != len(METRIC_FIELDS):
            raise ValueError(f"Row {index}: expected 5 cells")
        day, pin, impressions, clicks, saves = [str(x).strip() for x in values]
        try:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError()
            pin_id = int(pin)
            counts = [int(x) for x in (impressions, clicks, saves)]
        except ValueError as exc:
            raise ValueError(f"Row {index}: invalid date, pin ID or counts") from exc
        if pin_id not in pins or any(v < 0 for v in counts):
            raise ValueError(f"Row {index}: unknown pin or negative count")
        key = (day, pin_id)
        if key in seen:
            raise ValueError(f"Row {index}: duplicate metric key")
        seen.add(key)
        parsed.append((day, pin_id, *counts))
    return parsed


def import_metric_rows(storage, records):
    """Only NEW date/pin records are allowed; existing history cannot be overwritten."""
    with storage.conn:
        existing = {
            (day, pin) for day, pin in storage.conn.execute(
                "SELECT date,pin_id FROM pinterest_metrics")
        }
        if any(row[:2] in existing for row in records):
            raise ValueError("Existing date/pin metrics conflict; no rows imported")
        storage.conn.executemany(
            """INSERT INTO pinterest_metrics(date,pin_id,impressions,outbound_clicks,saves)
               VALUES(?,?,?,?,?)""", records)
    return len(records)


def export_pin_rows_with_ids(storage):
    """Stable short sequential PIN ID with date, shared by PNG and Google Sheets.

    Example: 0007-20261111. The sequence is the permanent local pin number;
    the date is assigned when the export ID is first generated, not each export.
    """
    from datetime import datetime
    pins = storage.all("pins")
    with storage.conn:
        storage.conn.execute(
            "CREATE TABLE IF NOT EXISTS google_pin_export_ids "
            "(pin_id INTEGER PRIMARY KEY, export_id TEXT NOT NULL UNIQUE)")
        for pin in pins:
            local_id = int(pin["id"])
            existing = storage.conn.execute(
                "SELECT export_id FROM google_pin_export_ids WHERE pin_id=?",
                (local_id,)).fetchone()
            if existing:
                # Keep previously issued identifiers: replacing them would
                # create duplicate records in already synchronized worksheets.
                continue
            today = datetime.now().strftime("%Y%m%d")
            export_id = f"{local_id:04d}-{today}"
            storage.conn.execute(
                "INSERT INTO google_pin_export_ids(pin_id,export_id) VALUES(?,?)",
                (local_id, export_id))
    ids = dict(storage.conn.execute(
        "SELECT pin_id,export_id FROM google_pin_export_ids").fetchall())
    return [{**row, "tags": pin.get("tags") or "", "pin_id": ids[pin["id"]]}
            for pin, row in zip(pins, export_pin_rows(storage))]


TRACKING_FIELDS = ("tracking_code", "utm_source", "utm_medium", "campaign",
                   "content_kind", "local_content_id", "title", "board",
                   "original_url", "marketing_url", "scheduled_at", "local_status",
                   "created_at", "registry_state")

def export_tracking_rows(storage):
    """Read-only registry snapshot, including detached historical allocations."""
    from .content_plan import entries
    from .utm import read_tracking_id
    plans = {}
    for row in entries(storage, "0001-01-01", "9999-12-31"):
        if row["tracking_id"]:
            plans.setdefault(row["tracking_id"], []).append(row)
    result = []
    for key, pin_id, original, url, campaign, created in storage.conn.execute(
            "SELECT id,pin_id,original_url,marketing_url,campaign,created_at FROM pin_tracking ORDER BY id"):
        code = read_tracking_id(url, "pint")
        linked = plans.get(key, [])
        pin = storage.get("pins", pin_id) if pin_id else None
        for row in linked or [None]:
            result.append(dict(zip(TRACKING_FIELDS, (
                code, "pint", "organic_social", campaign,
                row["kind"] if row else ("PIN" if pin else ""),
                (row["pin_id"] or row["carousel_id"]) if row else (pin_id or ""),
                row["title"] if row else ((pin or {}).get("title") or ""),
                (row["board_name"] or "") if row else "",
                original, url, row["scheduled_at"] if row else "",
                row["status"] if row else ((pin or {}).get("status") or ""),
                created, "PLANNED_RECORD" if row else ("PIN_RECORD" if pin else "DETACHED")
            ))))
    return result
