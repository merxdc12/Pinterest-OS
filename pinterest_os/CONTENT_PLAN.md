# Content Plan — local publishing workflow

The Calendar page is now Content Plan. Existing pin_schedule rows and Content
Factory references are preserved. The migration adds carousel_schedule and
plan_details; before upgrading an existing workspace a verified SQLite backup
is created (for portable projects, outside the manifest-covered directory).

## Workflow
1. Save a pin, or create a carousel from exported PNGs.
2. Use Content Plan / + Schedule pin or carousel, or the direct editor buttons.
3. Choose the content, an explicit board, local date/time and destination URL.
   A pin's copy comes from the library; a carousel has its own description.
4. For owned HTTPS ITHutir links, the plan generates pint UTM parameters and
   retains original URL and generated URL separately. The shared tracking
   sequence allocates unique IDs within a workspace; cross-workspace uniqueness
   is not implemented. External destinations are not rewritten: review partner
   rules and indicate affiliate status; required disclosure must appear in copy.
5. PLANNED can be incomplete. READY and manual publication require QA: metadata,
   board, valid URL, owned UTM / external review, affiliate disclosure when
   indicated, valid images and exact duplicate check on the same board.
   Factory approval is still required; changes to its approved board or URL
   must be made and reviewed in Content Factory first.
6. Day, week, month and list views share the same records. Filter by content,
   board, status or overdue; move pending rows or cancel them without deleting
   the library item.
7. Due entries appear in Publishing. Copy the actual publication metadata;
   export carousel ZIP including publication.json; publish manually on Pinterest
   if the account/interface supports the format. Confirm only after publication.
   Local confirmation does not verify Pinterest remotely. Confirming a carousel
   does not change the independent status of its component pins.

## Compatibility / limits
One pending publication per ordinary pin; create a distinct creative for a
second publication. A carousel can have separate plans on different boards.
Old calendar entries remain visible and use the previous QA rules until edited;
they are not silently assigned tracking IDs. Content Factory still owns its
approval lifecycle. Plan-specific board and URL do not overwrite library metadata;
analytics by actual placement or carousel, export of new tracking IDs into
Google Sheets, account-format eligibility and remote API publishing are not yet
implemented. Exact duplicate detection is based on current ordered file hashes,
not visual similarity or historical immutable image snapshots.

### Schedule management
The action bar separates rescheduling (date and time only), cancellation
(retains CANCELLED history), and permanent deletion of a local planning row.
Each works for pins and carousels; library items, image files and allocated
UTM identifiers remain. Confirmed published rows are protected. A linked
Content Factory export must first be cancelled through its review-withdrawal
workflow, then its cancelled schedule can be deleted. No remote Pinterest
record is changed.
