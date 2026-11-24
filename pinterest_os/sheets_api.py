"""Opt-in Google Sheets OAuth and safe, explicit worksheet exchange.

Credentials are stored in the operating-system keyring, not SQLite or QSettings.
Requires google-auth-oauthlib, google-api-python-client, keyring.
"""
from __future__ import annotations
import json

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SERVICE = "ITHutir-PinterestOS-GoogleSheets"
ACCOUNT = "oauth-credentials"


def _dependencies():
    try:
        import keyring
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Install optional Google integration: pip install -r requirements-google.txt"
        ) from exc
    return keyring, Credentials, InstalledAppFlow, Request, build


def _load():
    keyring, Credentials, _, Request, build = _dependencies()
    raw = keyring.get_password(SERVICE, ACCOUNT)
    if not raw:
        raise RuntimeError("Not connected. Select Connect Google first.")
    credentials = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    if not credentials.valid:
        if not credentials.refresh_token:
            raise RuntimeError("Google authorization expired. Reconnect.")
        credentials.refresh(Request())
        keyring.set_password(SERVICE, ACCOUNT, credentials.to_json())
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def connect(client_secret_file: str):
    keyring, _, Flow, _, _ = _dependencies()
    flow = Flow.from_client_secrets_file(client_secret_file, SCOPES)
    credentials = flow.run_local_server(host="127.0.0.1", port=0, open_browser=True)
    keyring.set_password(SERVICE, ACCOUNT, credentials.to_json())
    return True


def disconnect():
    keyring, *_ = _dependencies()
    keyring.delete_password(SERVICE, ACCOUNT)


def worksheets(spreadsheet_id: str):
    service = _load()
    result = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id, fields="sheets(properties(sheetId,title))"
    ).execute()
    return [(s["properties"]["sheetId"], s["properties"]["title"])
            for s in result.get("sheets", [])]


def _range(title):
    if not title or len(title) > 100 or any(ch in title for ch in "[]:*?/\\"):
        raise ValueError("Invalid worksheet title")
    return "'" + title.replace("'", "''") + "'"


def read_rows(spreadsheet_id: str, title: str, limit=1000):
    service = _load()
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{_range(title)}!A1:AZ{limit}",
        valueRenderOption="FORMATTED_VALUE"
    ).execute()
    return result.get("values", [])


def create_export_tab(spreadsheet_id: str, title: str, headers, records):
    """Create a NEW worksheet; never overwrite or modify existing user data."""
    if len(records) > 10000:
        raise ValueError("Export limited to 10,000 records")
    if not headers or len(headers) > 52:
        raise ValueError("Invalid export headers")
    service = _load()
    created = service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": title}}}]}
    ).execute()
    sheet_id = created["replies"][0]["addSheet"]["properties"]["sheetId"]
    rows = [list(headers)] + [
        [safe_cell(record.get(field, "")) for field in headers] for record in records
    ]
    try:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{_range(title)}!A1",
            valueInputOption="RAW",
            body={"values": rows},
        ).execute()
    except Exception:
        # A failed upload leaves the new tab in place for inspection/recovery.
        raise
    return sheet_id, len(records)


def safe_cell(value):
    if value is None:
        return ""
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def append_unique_pins(spreadsheet_id: str, title: str, headers, records):
    """Append pins once by stable pin_id. Never change existing remote rows."""
    expected = list(headers)
    if expected[-1:] != ["pin_id"] or len(expected) != 8:
        raise ValueError("Expected eight columns ending with pin_id")
    if len(records) > 10000:
        raise ValueError("Export limited to 10,000 pins")
    service = _load()
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{_range(title)}!A1:H100001",
        valueRenderOption="FORMATTED_VALUE").execute()
    rows = result.get("values", [])
    first_export = not rows
    if rows and list(rows[0]) != expected:
        raise ValueError(
            "Existing worksheet headers do not match: " + ", ".join(expected) +
            ". Existing data was not changed.")
    if any(len(row) > 8 for row in rows[1:]):
        raise ValueError("Unexpected extra columns; export cancelled")
    remote_ids = [str(row[7]).strip() for row in rows[1:] if len(row)>7 and str(row[7]).strip()]
    if len(remote_ids) != len(set(remote_ids)):
        raise ValueError("Duplicate remote pin_id detected; export cancelled")
    existing_ids = set(remote_ids)
    # Legacy rows without IDs cannot be matched safely. Do not guess.
    if any(row and (len(row) < 8 or not str(row[7]).strip()) for row in rows[1:]):
        raise ValueError("Existing PIN rows lack pin_id. Resolve legacy rows before append.")
    pending = []
    for record in records:
        pin_id = str(record["pin_id"]).strip()
        if not pin_id:
            raise ValueError("Missing local pin_id")
        if pin_id in existing_ids:
            continue
        pending.append([safe_cell(record.get(field, "")) for field in expected])
        existing_ids.add(pin_id)
    if first_export:
        # Only initialize a completely empty existing worksheet.
        metadata = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(sheetId,title,gridProperties))").execute()
        sheet = next((item["properties"] for item in metadata.get("sheets", [])
                      if item["properties"]["title"] == title), None)
        if sheet is None:
            raise ValueError("Selected worksheet no longer exists")
        if sheet.get("gridProperties", {}).get("columnCount", 0) < 8:
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"updateSheetProperties": {
                    "properties": {"sheetId": sheet["sheetId"],
                                   "gridProperties": {"columnCount": 8}},
                    "fields": "gridProperties.columnCount"}}]}).execute()
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=f"{_range(title)}!A1:H1",
            valueInputOption="RAW", body={"values": [expected]}).execute()
    # Freeze row one, including on subsequent exports; never modify user rows.
    metadata = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(sheetId,title,gridProperties(frozenRowCount)))").execute()
    sheet = next((item["properties"] for item in metadata.get("sheets", [])
                  if item["properties"]["title"] == title), None)
    if sheet is None:
        raise ValueError("Selected worksheet no longer exists")
    if sheet.get("gridProperties", {}).get("frozenRowCount", 0) < 1:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"updateSheetProperties": {
                "properties": {"sheetId": sheet["sheetId"],
                               "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount"}}]}).execute()
    if pending:
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id, range=f"{_range(title)}!A:H",
            valueInputOption="RAW", insertDataOption="INSERT_ROWS",
            body={"values": pending}).execute()
    return len(pending), len(records)-len(pending)
