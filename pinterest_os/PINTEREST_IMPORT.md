# Pinterest read-only import — Phase 1
Settings → Pinterest — імпорт.
Use a Pinterest developer OAuth access token with pins:read, boards:read,
user_accounts:read. Enter the account username and token in the local masked
field. The token is held in memory for the read request, not persisted.
API GET /v5/user_account, /v5/boards and /v5/pins; account identity is checked,
pagination is bounded, repins and known ad-only records are excluded,
only public boards owned by this account are selected. No remote writes.
Review the preview and attest ownership before importing. A verified SQLite
backup precedes the import. Existing board names may be matched uniquely;
existing pin IDs and title conflicts are skipped rather than overwritten.
Imported pins are PUBLISHED locally (API_READ or user attestation provenance),
with no new scheduled publication. Remote IDs, remote URL, remote date and
media type/URL live in separate mapping tables. Original links are preserved.
No image bytes, video, analytics, background synchronization, OAuth exchange
or refresh-token storage are implemented in this phase.

## File import
Native Pinterest privacy archive schema has not been inspected. Unknown archives
are refused, not guessed. Supported JSON or a ZIP containing exactly one root
ithutir_pinterest_import.json manifest (no extraction):
{
  "format": "ITHutir Pinterest Import v1",
  "account": "example",
  "boards": [{"id": "100", "name": "Example board"}],
  "pins": [{"id":"123456789012345678", "board_id":"100", "title":"Example",
            "description":"Example description", "link":"https://ithutir.com/example",
            "created_at":"2026-01-01", "media_type":"image", "media_url":""}]
}
IDs are strings to preserve exact digits. Manifest data is user-attested, not API
verified. No content is uploaded or modified remotely.

Official docs:
https://help.pinterest.com/en/article/download-your-pinterest-data
https://developers.pinterest.com/docs/api/v5/pins-list/
https://developers.pinterest.com/docs/api/v5/boards-list/
https://developers.pinterest.com/docs/api/v5/user_account-get/

## API key manager
The Pinterest import page accepts App ID, optional App Secret, Access Token,
optional Refresh Token and optional known expiration (ISO timestamp with offset).
Save/load/delete use the explicit Linux Secret Service backend, scoped by
username and App ID. No SQLite/QSettings/plaintext fallback. Save clears the
fields; API reads can reload the saved token automatically. For Trial, replace
the 24-hour token manually in the developer portal. OAuth authorization-code
exchange and refresh-token exchange are not yet implemented. Disconnect removes
local credentials, not the remote authorization or imported records.
