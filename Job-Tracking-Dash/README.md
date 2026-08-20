# Sprint Log — 60-Day Job Application Tracker

A local, single-user dashboard for logging and visualizing a 60-day / 360-application job
search sprint. Node.js + Express + SQLite backend, plain HTML/JS + Chart.js frontend —
no build step, no framework, no account/cloud dependency. Your data lives in one file
(`jobs.db`) on your own machine.

## What it tracks per application

- Title, company, platform, applied timestamp (required)
- Status: applied / interview / offer / rejected / no response
- Location, posting URL, whether it came via referral, free-text notes

## What the dashboard shows

- Sprint clock: current day (of 60), total logged, apps/day pace, current daily streak
- Progress bar toward the 360-application goal
- **Daily intensity heatmap** — a 60-cell grid (like a habit tracker) shaded by how many
  applications you logged that day, so a 6-app day visibly "lights up"
- Applications per day (bar)
- Cumulative applications vs. the goal pace line (the "slinky" progress curve)
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

- Change the goal (default 360 applications / 60 days / 6 per day) by editing the
  constants at the top of `public/app.js` (`GOAL_TOTAL`, `GOAL_PER_DAY`, `SPRINT_DAYS`).
- Add more fields (e.g. `salary`, `contact_name`) by adding a column in the `CREATE TABLE`
  statement in `server.js`, adding it to the `COLUMNS` array, and adding a matching
  `<label>` in `public/index.html`.
- Want it accessible from your phone on the same Wi-Fi? Run `node server.js`, find your
  computer's local IP (e.g. `192.168.1.23`), and visit `http://192.168.1.23:3001` from
  your phone's browser.

## Notes on the two "reference" chart types

- **Cumulative chart**: your running total (teal) plotted against a dashed straight-line
  pace to 360 over 60 days, so you can see at a glance whether you're ahead or behind.
- **Heatmap**: the closest equivalent to a "slinky"-style progress spiral that's still
  easy to read at a glance — each of the 60 sprint days as one cell, intensity-coded.
