# Content Factory Phase 1 — final test report

Date: 2026-11-11. Issue: [merxdc12/Dyrektor_Sale #1](https://github.com/merxdc12/Dyrektor_Sale/issues/1). Baseline commit: `464ef5c`.

## Results

| Verification | Result |
| --- | --- |
| Untouched baseline, complete pytest suite | **88 passed, 4 failed** in 6.07s |
| Final complete pytest suite | **148 passed, 4 failed** in 6.97s |
| New Content Factory coverage within the final suite | **60 passed, 0 failed** |
| Previously passing tests | **All 88 still pass** |
| Existing test files | Unchanged |
| Python compilation | Passed |
| `git diff --check` | Passed |
| Offscreen planner/review screenshots | Captured and visually inspected |
| Live ITHutir RSS | **Not verified**: network access failed |
| Pinterest RSS account connection | **Unknown**; no account-side evidence requested or claimed |

The suite is not entirely green. The same four failures reproduce on an untouched archive of the baseline and on the implementation. They were not changed as part of this scoped task:

| Existing test | Observed failure on both versions |
| --- | --- |
| `test_board_logic.py::test_board_categories_and_assignment` | Test expects no match for `esp32`; existing board search includes the description containing ESP32. |
| `test_product_profitability.py::test_product_contribution_and_roi` | Expects contribution `6000`; existing financial completeness rules return `None`. |
| `test_project_files.py::ProjectTests::test_project_backup_restore_and_asset_rebase` | Tests a restored relative asset path against the process working directory rather than the restored project root. |
| `test_publishing_logic.py::test_manual_confirmation_requires_complete_pin` | Case-sensitive pattern `Already` does not match existing message `Pin already marked as published`. |

Final pytest output:

```text
FAILED tests/test_board_logic.py::test_board_categories_and_assignment
FAILED tests/test_product_profitability.py::test_product_contribution_and_roi
FAILED tests/test_project_files.py::ProjectTests::test_project_backup_restore_and_asset_rebase
FAILED tests/test_publishing_logic.py::test_manual_confirmation_requires_complete_pin
4 failed, 148 passed in 6.97s
```

## Environment and reproducibility

Python 3.12.3, PyQt6/Qt 6.12.0, pytest 9.2.0, SQLite from Python's standard library, Linux with `QT_QPA_PLATFORM=offscreen`. The system initially lacked importable PyQt6 and pytest. Cached compatible wheels were extracted into `/tmp/content-factory-qt`; no system packages or unrelated project files were changed. Qt settings were isolated under `/tmp`.

The untouched baseline was created with `git archive HEAD` into `/tmp/content-factory-baseline`, before any commits. Both baseline and final suites used:

```bash
PYTHONPATH=/tmp/content-factory-qt \
QT_QPA_PLATFORM=offscreen \
XDG_CONFIG_HOME=/tmp/content-factory-config \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python3 -m pytest -q -p no:cacheprovider
```

After normal dependency installation, the portable commands are:

```bash
python -m pip install -r requirements.txt pytest
QT_QPA_PLATFORM=offscreen python -m pytest -q
QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_content_factory.py tests/test_content_feed.py tests/test_content_factory_ui.py
python -m compileall -q pinterest_os tests/test_content_factory.py tests/test_content_feed.py tests/test_content_factory_ui.py
git diff --check
```

## New coverage

- Additive migration of existing and older schemas; preserved legacy rows and custom tables; foreign-key integrity; restart idempotency; automatic pre-migration snapshots; restore and re-migrate; failure rollback across startup DDL; savepoint isolation; backup collision handling.
- RSS parsing for Media RSS content/thumbnail, image enclosures and encoded HTML images; missing/unsafe images; sanitization; canonicalization; meaningful query preservation; invalid XML, DTD/entity and encoding rejection; item/byte bounds; HTTP GET/timeout/redirect restrictions; network errors; persistent refresh state; stable GUID/URL aliases and conflicting-alias handling.
- Exactly twelve editable slots, mix and month validation, month-end scheduling, and repeated creation without duplicate inserts.
- Manual source types and keyword provenance; unknown metrics stay null; unsupported, negative, nonfinite and incorrectly typed metrics rejected; verified metrics require evidence and a scale/period definition.
- Manual copy without AI credentials; optional AI JSON import; draft revision provenance; no implicit image attestation; malformed responses; title/description and image-grounded review workflow.
- Decode and size checks on real PNGs; corrupt, missing and wrong-size images; image-hash attestation; explicit human approval; affiliate disclosure; stale image/source/copy approval rejection; exact creative+URL detection including legacy pins and retained ledger history after pin deletion.
- All twelve approved slots exported into the existing PIN and Calendar records; retry idempotency; calendar conflicts; atomic rollback of PIN/Calendar/ledger writes; existing CSV and Sheets export compatibility; campaign financial/time evidence without multiplied rows or inferred attribution.
- Source-level RSS publication evidence remains separate from per-creative evidence; no feed/export/local-publication step invents an account connection or remote publication confirmation.
- Existing manual Publishing rejects unapproved or changed factory content; return-to-review cancels pending schedules; explicitly published content cannot be withdrawn as draft.
- Full project backup and restore retains factory metadata, approval validity and rebased creative assets.
- Real Qt page construction, six sub-tabs, slot editing, user-facing errors, worker completion, stale worker results after project changes, reuse of the existing 1000×1500 Designer, navigation to existing Calendar/Publishing/Analytics/TIME/BOARD/PIN and main-window project switching.

## Screenshots and limits

- [Planner screenshot](docs/content_factory_planner.png)
- [Review screenshot](docs/content_factory_review.png)

Screenshots use a clearly labelled synthetic local workspace, with no live-source or account-connection claims. They verify layout via Qt's offscreen rendering, not an interactive desktop session on every supported operating system.

Live RSS preflight attempted `https://ithutir.com/rss.xml` via web access and a bounded HTTPS curl GET. Web access reported it inaccessible; curl returned `Could not resolve host: ithutir.com`. Therefore actual current feed contents and live image tags could not be confirmed. Fixture coverage is not presented as a successful live fetch. Recheck using Planner's read-only refresh when network access is available.

No deployment, merge, publishing, website change, remote branch push or PR creation was performed. Code, documentation, tests and screenshots remain local for review.
