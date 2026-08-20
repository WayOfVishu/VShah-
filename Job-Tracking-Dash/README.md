# Job Search Dashboard

A local, single-user, one-stop dashboard for logging and visualizing job applications —
open-ended, not tied to any fixed day count. Node.js + Express + SQLite backend, plain
HTML/JS + Chart.js frontend — no build step, no framework, no account/cloud dependency.
Your data lives in one file (`jobs.db`) on your own machine.

## What it tracks per application

- Title, company, platform, applied timestamp (required)
- Status: applied / interview / offer / rejected / no response
- Location, posting URL, whether it came via referral, free-text notes

## What the dashboard shows

- Stat strip: total logged, days active (since your first entry), apps/day pace, current
  daily streak — all uncapped, they just keep accumulating
- **Daily intensity heatmap** — a GitHub-contribution-style grid shaded by how many
  applications you logged each day. It grows with your history instead of resetting at
  a fixed day count, and scrolls horizontally once it gets wide
- **Application pipeline (Sankey diagram)** — every application flows from the platform
  you applied on into its current outcome (interview / offer / rejected / no response /
  still awaiting response), so you can see at a glance which platforms are actually
  converting
- Applications per day (bar)
- Cumulative applications over time (line)
- 7-day rolling average (smooths out daily noise)
- Breakdown by platform, by status, by day of week, and top 10 companies applied to
- Full searchable/editable/deletable log table
- One-click CSV export of every field, for further analysis in Excel/Sheets

## Requirements

- [Node.js](https://nodejs.org) 18 or newer (includes npm)

## Setup

1. Unzip the project and open a terminal in the `job-tracker` folder.
2. Install dependencies:

   ```bash
   npm install
   ```

3. Start the server:

   ```bash
   npm start
   ```

4. Open **http://localhost:3001** in your browser.

That's it — no separate frontend build, no environment variables, no external database
to configure. The first time you add an entry, a `jobs.db` SQLite file is created
automatically in the project folder.

## Daily use

Each day, fill out the "Log an application" form once per application (title, company,
platform, and the applied timestamp are required; everything else is optional but feeds
the richer charts — e.g. fill in `status` later once you hear back, or check "referral"
if a contact got you the application in). Click **Edit** on any row in the log table to
update it later, or **Delete** to remove a bad entry.

## Restarting later

Your data persists in `jobs.db` between sessions. Just run `npm start` again from the
project folder any day you want to log more applications or check your charts — no need
to reinstall anything unless you delete `node_modules`.

## Backing up / moving your data

- **CSV**: click "Export CSV" in the app, or visit `http://localhost:3001/api/export`.
- **Full backup**: just copy the `jobs.db` file — it's the entire database.

## Project structure

```
job-tracker/
├── package.json
├── server.js          # Express API + static file server
├── jobs.db            # created automatically on first run (SQLite)
└── public/
    ├── index.html      # dashboard shell
    ├── style.css       # theme
    └── app.js          # data fetching, charts, table, form logic
```

## API reference

| Method | Route              | Purpose                                  |
|--------|---------------------|-------------------------------------------|
| GET    | `/api/jobs`         | List all logged applications              |
| POST   | `/api/jobs`         | Create one (title/company/platform/timestamp required) |
| PUT    | `/api/jobs/:id`      | Update one (partial fields accepted)      |
| DELETE | `/api/jobs/:id`      | Remove one                                |
| GET    | `/api/export`       | Download every field as CSV               |

## Customizing

- Add more fields (e.g. `salary`, `contact_name`) by adding a column in the `CREATE TABLE`
  statement in `server.js`, adding it to the `COLUMNS` array, and adding a matching
  `<label>` in `public/index.html`.
- Want it accessible from your phone on the same Wi-Fi? Run `node server.js`, find your
  computer's local IP (e.g. `192.168.1.23`), and visit `http://192.168.1.23:3001` from
  your phone's browser.

## Third-party libraries

Both are loaded from jsDelivr in `public/index.html` — no npm install needed for them,
they're plain `<script>` tags:

- [Chart.js](https://www.chartjs.org/) — all the bar/line/doughnut charts
- [chartjs-chart-sankey](https://github.com/kurkle/chartjs-chart-sankey) — the pipeline
  diagram. It registers a `sankey` chart type on top of Chart.js automatically.
