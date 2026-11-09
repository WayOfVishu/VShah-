# Tasks: House add-on for Home Assistant

Source: [prd-house-app.md](prd-house-app.md) (§4.2 Phase 2, §6, §7.3)
Prerequisite: [tasks-hardware-setup.md](tasks-hardware-setup.md) tasks 2.0–4.0 are done (HA running, Samba/SSH add-ons, both phones on the Companion app).

## Relevant Files

- `Projects/House-App/.gitignore` - Keeps house data out of the public repo (`*.db`, `*.csv`, `data/`, `.env`, `dist/`, `node_modules/`).
- `Projects/House-App/house/config.yaml` - Add-on manifest: ingress, `homeassistant_api`, sidebar panel, and options (users, possession date).
- `Projects/House-App/house/Dockerfile` - Multi-stage build: Node builds the frontend, then the Python 3.12 slim runtime runs uvicorn.
- `Projects/House-App/house/requirements.txt` - fastapi, uvicorn, python-dateutil, python-multipart, httpx.
- `Projects/House-App/house/app/main.py` - FastAPI app, lifespan (starts the reminder loop), routes, static files.
- `Projects/House-App/house/app/db.py` - SQLite connection (WAL, foreign keys) and the forward-only migration runner.
- `Projects/House-App/house/app/recurrence.py` - Next-due-date calculation (RRULE and after-completion) in `America/Edmonton`.
- `Projects/House-App/house/app/reminders.py` - Due-task query, the duplicate-safe notification loop, complete and snooze.
- `Projects/House-App/house/app/ha.py` - Calls the Supervisor `core/api` (notify), with a dry-run when there's no token.
- `Projects/House-App/house/app/importer.py` - CSV item import, seed loading, warranty tasks.
- `Projects/House-App/house/app/export.py` - JSON + Markdown zip export and the defect report.
- `Projects/House-App/house/migrations/001_init.sql` - Tables: users, items, tasks, log_entries, attachments.
- `Projects/House-App/house/migrations/002_fts.sql` - FTS5 search table and its sync triggers.
- `Projects/House-App/house/seeds/calgary.json` - Generic Calgary maintenance tasks with descriptions and recurrence.
- `Projects/House-App/house/frontend/index.html` - App shell and the bottom tab bar.
- `Projects/House-App/house/frontend/src/main.js` - Router and views (Today, Tasks, House, Log).
- `Projects/House-App/house/frontend/src/api.js` - Fetch wrapper using **relative** URLs (needed for ingress).
- `Projects/House-App/house/frontend/src/style.css` - Mobile-first styles, light and dark.
- `Projects/House-App/house/frontend/vite.config.js` - `base: './'`.
- `Projects/House-App/tests/test_db.py` - Migrations, FTS.
- `Projects/House-App/tests/test_recurrence.py` - Next-due-date logic, including DST and month-end.
- `Projects/House-App/tests/test_reminders.py` - No double-send, retry on failure, "either" goes to both phones.
- `Projects/House-App/tests/test_api.py` - Auth, CRUD, complete → next due, export.
- `Projects/House-App/tests/test_importer.py` - CSV import, seeds can be re-run safely.
- `Projects/House-App/tests/fixtures/items.csv` - Generic sample CSV. **No** real house data.
- `Projects/House-App/README.md` - Dev setup, install steps, and the architecture diagram from the PRD.

### Notes

- Run the tests with `py -m pytest Projects/House-App/tests`. Tests are a separate folder from the add-on, so they aren't shipped inside the image.
- Local dev without HA: `DEV_USER=vihang DATA_DIR=./data-dev uvicorn app.main:app --reload` from `house/`. When `SUPERVISOR_TOKEN` is missing, notifications only print to the log.
- Build the frontend with `node node_modules/vite/bin/vite.js build` from `house/frontend`. PowerShell drops arguments passed after `npm run x --`.
- The local add-on's slug in HA becomes `local_house`. The ingress panel URL is `/hassio/ingress/local_house`.
- Never put the possession date, model/serial numbers or the address in code or seeds. They go in the add-on options or the database only.
- After code changes, run `graphify update .` (repo rule).

## Instructions for Completing Tasks

**IMPORTANT:** As you complete each task, you must check it off in this markdown file by changing `- [ ]` to `- [x]`. This helps track progress and ensures you don't skip any steps.

Example:
- `- [ ] 1.1 Read file` → `- [x] 1.1 Read file` (after completing)

Update the file after completing each sub-task, not just after completing an entire parent task.

## Tasks

- [ ] 0.0 Create feature branch
  - [ ] 0.1 Reuse `Project/House-App` from the hardware task list. If it doesn't exist yet, create it from `main`.
- [ ] 1.0 Scaffold the add-on
  - [ ] 1.1 Create the layout: `Projects/House-App/house/` (the add-on folder, holding everything the image needs) and `Projects/House-App/tests/`
  - [ ] 1.2 Write `Projects/House-App/.gitignore` before any other file
  - [ ] 1.3 Write `config.yaml` with these fields:
    - `name: House`, `slug: house`, `version: 0.1.0`, `arch: [amd64]`
    - `ingress: true`, `ingress_port: 8099`
    - `panel_icon: mdi:home-heart`, `panel_title: House`
    - `homeassistant_api: true`
    - an options schema with `users` (a list of `{ha_user_id, name, notify_service}`) and `possession_date` (a date)
  - [ ] 1.4 Write the multi-stage `Dockerfile`: a `node:20-slim` stage builds the frontend, then the `python:3.12-slim` runtime copies in the app and `dist/`. Command: `uvicorn app.main:app --host 0.0.0.0 --port 8099`.
  - [ ] 1.5 Write `requirements.txt`, and a dev-only `requirements-dev.txt` with pytest
  - [ ] 1.6 Write a minimal `main.py`: `GET /api/health`, plus `GET /api/me`, which echoes `X-Remote-User-Id`, `X-Remote-User-Name` and `X-Ingress-Path`
  - [ ] 1.7 Add dev fallbacks: a `DEV_USER` env var stands in for the ingress headers, and `DATA_DIR` defaults to `/data`
  - [ ] 1.8 Copy `house/` to the HA `/addons/house` share through Samba. In the Add-on Store, choose ⋮ → Check for updates, then install **House** from Local add-ons, start it, and turn on "Show in sidebar".
  - [ ] 1.9 Open the House panel in the Companion app on both phones and confirm `/api/me` shows each person's name
  - [ ] 1.10 Write a `README.md` with dev setup and install steps
- [ ] 2.0 Build the data layer
  - [ ] 2.1 `db.py`: `connect()` opens `DATA_DIR/house.db` with `journal_mode=WAL` and `foreign_keys=ON`
  - [ ] 2.2 Migration runner: a `schema_migrations` table, then each `migrations/NNN_*.sql` file applied in order, one transaction per file, forward-only. Mirror the Jobs-Web-App runner.
  - [ ] 2.3 `001_init.sql`: create these tables:
    - `users`: `ha_user_id` PK, name, notify_service
    - `items`: id, name, category CHECK in the 7 categories, location, body_md, brand, model, serial, install_date, warranty_end, consumable, buy_where, tags, created_at, updated_at
    - `tasks`: id, title, description_md, assignee (a user id or `'either'`), due_at, recurrence_kind CHECK `none|after|calendar`, interval_days, rrule, item_id FK, priority, snoozed_until, last_notified_at, completed_at, active
    - `log_entries`: id, type CHECK `maintenance|repair|defect`, task_id, item_id, user_id, done_at, note_md, cost_cents, room, warranty_period
    - `attachments`: id, owner_type, owner_id, filename, mime, path, created_at
  - [ ] 2.4 `002_fts.sql`: an FTS5 table `search(kind, ref_id, title, body)`, with insert, update and delete triggers on items, tasks and log_entries
  - [ ] 2.5 On startup, load the add-on options from `/data/options.json` and upsert the `users` rows
  - [ ] 2.6 `test_db.py`: migrations apply to an empty DB; running them again does nothing; a word in an item's body is found through FTS
- [ ] 3.0 Build the core logic (recurrence, reminders, notifications)
  - [ ] 3.1 `recurrence.py`, function `next_due(task, completed_at)`:
    - `after`: `completed_at + interval_days`, at 09:00 local time
    - `calendar`: `rrulestr(rrule, dtstart=...)`, the next occurrence after now
    - `none`: returns `None`
  - [ ] 3.2 Store all times as UTC ISO strings. Convert with `ZoneInfo("America/Edmonton")` only at the edges (input and display).
  - [ ] 3.3 `test_recurrence.py`: cover these cases:
    - 90 days after completion
    - every October 1
    - the last day of the month (`BYMONTHDAY=-1`)
    - 09:00 local time held across the DST changes on 2027-03-14 and 2027-11-07
  - [ ] 3.4 `reminders.py` `due_now(conn, now)` returns a task only if all of these hold:
    - it is active and not completed
    - `due_at <= now`
    - it is not snoozed past now
    - local time is 09:00 or later
    - `last_notified_at` is empty or falls on an earlier local date
  - [ ] 3.5 `ha.py` `notify(service, title, message, data)` sends `POST http://supervisor/core/api/services/notify/<service>` with a `Bearer $SUPERVISOR_TOKEN` header and a 10-second timeout. It logs the message instead when no token is set, and it never raises into the loop.
  - [ ] 3.6 Start a background loop in the FastAPI lifespan that runs every 60 seconds:
    - resolve the assignee to notify services (`either` means every user)
    - send the notification, with `data.url` set to `/hassio/ingress/local_house`
    - set `last_notified_at` only after the send succeeds
  - [ ] 3.7 `complete_task()`: write a log entry. If the task recurs, set `due_at = next_due(...)` and clear `last_notified_at`. Otherwise set `completed_at`.
  - [ ] 3.8 `snooze_task(task, days)`: set `snoozed_until`
  - [ ] 3.9 `test_reminders.py`: cover these cases:
    - one send per day, even when the loop runs twice
    - a failed send is retried on the next tick
    - `either` reaches both services
    - completing a recurring task moves the due date forward and resets notifications
- [ ] 4.0 Build the HTTP API
  - [ ] 4.1 Identity dependency: read `X-Remote-User-Id` and return 403 if that user isn't in `users`. Allow the `DEV_USER` fallback only when the `DEV` env var is set.
  - [ ] 4.2 `/api/items`: list (with a category filter), get, create, update, delete
  - [ ] 4.3 `/api/tasks`: list (overdue, today, week, all), get, create, update, delete, plus `POST /{id}/complete` (with an optional note and cost) and `POST /{id}/snooze`
  - [ ] 4.4 `POST /api/tasks/quick`: takes `{title, date}`, assigns `either`, and uses `recurrence_kind=none`
  - [ ] 4.5 `/api/log`: list (filter by item, task or type) and create (including Defect, with room and warranty_period)
  - [ ] 4.6 `GET /api/search?q=`: FTS5 `MATCH` with `snippet()`, grouped by kind
  - [ ] 4.7 Attachments: a multipart upload saved to `DATA_DIR/attachments/<uuid>`. Allow only `image/*` and `application/pdf`, with a 20 MB limit. Serve files only through an authenticated GET.
  - [ ] 4.8 `GET /api/export`: a zip of `data.json`, plus one Markdown file per item and per task, plus `log.md`
  - [ ] 4.9 `GET /api/reports/defects?period=1y`: open defects as Markdown with dates and photo links. For PDF, use the browser's Print to PDF with print CSS; no PDF library.
  - [ ] 4.10 `test_api.py` (TestClient): an unknown user gets 403; a new item is found by search; completing a recurring task advances its due date; the export zip contains the expected files
- [ ] 5.0 Build the frontend
  - [ ] 5.1 Scaffold Vite with vanilla JS in `house/frontend`, `base: './'`. The FastAPI app serves `dist/` at `/`.
  - [ ] 5.2 `api.js`: every call uses a relative path (`api/tasks`, **not** `/api/tasks`), so it works under the ingress prefix
  - [ ] 5.3 App shell: a bottom tab bar (Today, Tasks, House, Log), hash routing, mobile-first CSS, light and dark themes via `prefers-color-scheme`
  - [ ] 5.4 Today view: Overdue (highlighted), Today, This week. Tapping the check mark completes a task; a long-press or menu snoozes it for 1 day or 1 week.
  - [ ] 5.5 Quick-add bar at the top of Today: a title input and `<input type="date">`, submitted on Enter
  - [ ] 5.6 Task detail and edit:
    - a Markdown description, rendered with `marked` and sanitized with `DOMPurify`
    - assignee select and linked-item select
    - recurrence picker: None / Every N days after done / Yearly on a date / Monthly on a day. The picker builds the RRULE; users never type it.
  - [ ] 5.7 House view: items grouped by category, a search box (hitting `/api/search`), and an item detail page showing fields, attachments, linked tasks and log history
  - [ ] 5.8 Log view: the entry list and an add form (type, note, cost, photo; Defect also shows room and warranty period), plus a "Defect report" button that opens a print-ready page
  - [ ] 5.9 Photo capture: `<input type="file" accept="image/*" capture="environment">`
  - [ ] 5.10 Manual check in the Companion app on both iPhones (inside ingress) and in desktop browsers on both laptops
- [ ] 6.0 Seed content and import
  - [ ] 6.1 `seeds/calgary.json`: generic tasks from PRD requirement 33, each with a description (steps, parts, tools) and a recurrence
  - [ ] 6.2 Warranty tasks: build them from the `possession_date` option, never hard-coded. For each period (1, 2, 5 and 10 years), create one-off tasks due 60 days and 14 days before the end date, assigned to `either`.
  - [ ] 6.3 First-run seed review screen: a checklist of the seed tasks to accept or reject. Store a `seeds_applied` flag so it only appears once.
  - [ ] 6.4 CSV import: `POST /api/import/items` with a preview step (parsed rows and errors), then commit. Columns: name, category, location, brand, model, serial, consumable, notes.
  - [ ] 6.5 `tests/fixtures/items.csv` with generic sample rows
  - [ ] 6.6 `test_importer.py`: valid rows import; bad rows are reported, not skipped silently; applying seeds twice creates no duplicates; warranty dates are correct for a fixed test date
- [ ] 7.0 Release
  - [ ] 7.1 Bump `version` in `config.yaml`, copy `house/` to `/addons/house`, then Rebuild and Start
  - [ ] 7.2 In the add-on's Configuration tab, set `users` (both HA user IDs and notify service names from hardware task 4.5) and `possession_date`
  - [ ] 7.3 Run the seed review, import the Phase 0 spreadsheet, and enter any items still open after the 2026-11-24 repair visit as Defect log entries
  - [ ] 7.4 Trigger an HA backup and confirm it includes the House add-on. Restore the add-on alone from that backup and confirm the data survives.
  - [ ] 7.5 Wife test: she quick-adds a task in 15 seconds or less with no instructions. Fix whatever slows her down.
  - [ ] 7.6 Confirm a real due reminder arrives on both phones and that tapping it opens the House panel
  - [ ] 7.7 Run `graphify update .` and `py -m pytest Projects/House-App/tests`, then commit and open a PR into `main`
