# ITHutir Marketing Source Standard

Pinterest: pint; YouTube: yt; Facebook: fb; TikTok: tik.
Use utm_source, utm_medium=organic_social, utm_campaign (slug), utm_content
(source-prefixed numeric content ID), optional utm_term. Example: pint_000001.

Phase 1 core: utm.marketing_url generates URLs only for owned HTTPS
ithutir.com / www.ithutir.com. It preserves unrelated query fields and
fragments, replaces standard UTM fields without duplication, and rejects
external destinations (including partner links). No remote requests.

Remaining: persistent cross-workspace ID allocation, original and marketing
URL storage, approval-aware publishing UI, CSV/Sheets tracking export,
affiliate validation and analytics integration. Existing pins, database,
and publishing workflow are not changed by this core module.


Update: newly issued content codes use a 39-digit numeric UUID4 representation,
prefixed by source, instead of a database-local sequence. Existing short
codes are read from stored marketing URLs unchanged. This prevents practical
collisions across independently created workspaces and restored snapshots
without a network service; it is probabilistic, not an absolute global
uniqueness guarantee. Existing duplicate legacy codes need separate auditing.
Local SQLite row IDs remain internal. Content Plan uses the same generator
for pin and carousel publication records.

Publishing QA checks the saved marketing URL against original URL, campaign and issued code for explicit owned-URL plans. Legacy schedules without plan details still require migration/review. Settings > Google Sheets > Export UTM tracking registry to NEW worksheet creates a confirmed read-only snapshot of local records (not verified remote publications). Detached allocations remain visible. Never add together repeated snapshots; reconcile by tracking code and investigate conflicting legacy codes. Live Google export requires OAuth and manual confirmation.
