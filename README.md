# ITHutir Pinterest OS

Cross-platform, offline-first desktop workspace for organic Pinterest content production. **No Pinterest API or automated posting.** Publishing happens manually in the system browser. Optional Google Sheets exchange is documented in [Google Sheets setup](pinterest_os/GOOGLE_SHEETS_SETUP.md).

## Phase 1: working foundation

- PyQt6 desktop window: FILE, PIN, CONTENT FACTORY, BOARD, CALENDAR, PUBLISHING, ANALYTICS, REPORTS, TIME, SETTINGS, HELP.
- Local SQLite storage for products, boards, pins, work sessions, and time entries.
- A session timer that starts on launch, supports pause/resume, and saves time to SQLite.
- Local pin drafts and board records. Publishing is not automated.
- Content Factory: read-only ITHutir RSS import, manual/product sources, a 12-slot monthly plan, keyword evidence, optional AI copy import, image review and approved local PIN/Calendar export. See the [Content Factory guide](pinterest_os/CONTENT_FACTORY.md) and [test report](pinterest_os/CONTENT_FACTORY_TEST_REPORT.md).

## Run (Linux Mint / Windows / macOS)

Install Python 3.11+ and create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pinterest_os
```

On Windows use `.venv\\Scripts\\activate` and `python` instead of `python3`. PyQt6 requires a desktop environment. SQLite data is stored in the platform-specific application data directory via Qt QStandardPaths.

## Tests

```bash
python -m pip install pytest
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

Use pytest for the complete suite: the repository contains both unittest classes and pytest-style functions. `python -m unittest discover -s tests -v` runs only the unittest portion. The test report records pre-existing failures separately from new coverage.

## Scope and limitations

Calendar, Publishing, Analytics, Reports, TIME and Settings remain the existing local workspace tools. Content Factory reuses Pin Designer and their existing records. It only fetches the public `https://ithutir.com/rss.xml` feed on explicit refresh; feed availability does not establish that any Pinterest account has connected RSS. AI assistance is optional prompt/response exchange with your chosen tool, with a complete manual fallback. No AI API keys are needed.

Automated verification uses Qt's offscreen platform. Desktop interaction on each target OS and live RSS availability still require verification; see the test report for this run's exact limits.

## Safety

Never commit local SQLite files, credentials, exported user content, or virtual environments. Do not use browser automation for account actions.
