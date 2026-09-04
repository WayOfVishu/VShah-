import express from "express";
import Database from "better-sqlite3";
import path from "path";
import { readFileSync, existsSync } from "fs";
import { fileURLToPath } from "url";
import { spawn } from "node:child_process";

import { applyMigrations } from "./db/migrate.js";
import { transition, USER_TRIGGERABLE } from "./lib/statusMachine.js";
import { buildTailoringPrompt } from "./lib/promptBuild.js";
import { checkTraceability } from "./lib/traceabilityCheck.js";
import { tailorJob } from "./lib/tailorInvoke.js";
import { renderMarkdownToPdf } from "./lib/pdfExport.js";
import { loadPreferences, savePreferences } from "./lib/preferences.js";
import { weightedMix } from "./lib/scoring.js";
import {
  isFresh,
  buildAppliedIndex,
  isAlreadyApplied,
  exceedsExperienceCap,
  parseDate,
} from "./lib/jobFilter.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const app = express();
const PORT = process.env.PORT || 3001;

// ---------------------------------------------------------------------------
// Database
// ---------------------------------------------------------------------------
// Same env var discover.js honours, so both entry points can be pointed at a
// scratch copy for testing. Defaults to the real file, unchanged.
const db = new Database(process.env.JOBS_DB_PATH || path.join(__dirname, "jobs.db"));
db.pragma("journal_mode = WAL");
// A discovery run is a second writer on this file, started by the Refresh
// button while the dashboard keeps serving reads. WAL allows that, but a write
// that collides with one still fails instantly unless it is told to wait.
db.pragma("busy_timeout = 5000");

db.exec(`
  CREATE TABLE IF NOT EXISTS jobs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    company    TEXT NOT NULL,
    platform   TEXT NOT NULL,
    timestamp  TEXT NOT NULL,          -- ISO datetime the application went out
    status     TEXT NOT NULL DEFAULT 'applied',  -- applied | interview | rejected | offer | ghosted
    location   TEXT,
    url        TEXT,
    referral   INTEGER NOT NULL DEFAULT 0,
    notes      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
  )
`);

// Applies db/migrations/*.sql — the `discovered_jobs`,
// `sources`, and `overrides` tables (PRD req. 17-19). Additive only; the
// `jobs` table above is untouched. discover.js runs the same migration set, so
// whichever entry point starts first, both see the same schema.
applyMigrations(db);

const COLUMNS = ["title", "company", "platform", "timestamp", "status", "location", "url", "referral", "notes"];

// ---------------------------------------------------------------------------
// Middleware
// ---------------------------------------------------------------------------
app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));

// ---------------------------------------------------------------------------
// API — CRUD
// ---------------------------------------------------------------------------
app.get("/api/jobs", (req, res) => {
  const jobs = db.prepare("SELECT * FROM jobs ORDER BY timestamp ASC").all();
  res.json(jobs);
});

app.post("/api/jobs", (req, res) => {
  const body = req.body || {};
  const { title, company, platform, timestamp } = body;
  if (!title || !company || !platform || !timestamp) {
    return res.status(400).json({ error: "title, company, platform, and timestamp are required." });
  }
  const stmt = db.prepare(`
    INSERT INTO jobs (title, company, platform, timestamp, status, location, url, referral, notes)
    VALUES (@title, @company, @platform, @timestamp, @status, @location, @url, @referral, @notes)
  `);
  const info = stmt.run({
    title,
    company,
    platform,
    timestamp,
    status: body.status || "applied",
    location: body.location || null,
    url: body.url || null,
    referral: body.referral ? 1 : 0,
    notes: body.notes || null
  });
  res.status(201).json(db.prepare("SELECT * FROM jobs WHERE id = ?").get(info.lastInsertRowid));
});

app.put("/api/jobs/:id", (req, res) => {
  const existing = db.prepare("SELECT * FROM jobs WHERE id = ?").get(req.params.id);
  if (!existing) return res.status(404).json({ error: "Job not found." });

  const merged = { ...existing, ...req.body, id: existing.id };
  merged.referral = merged.referral ? 1 : 0;

  db.prepare(`
    UPDATE jobs SET
      title = @title, company = @company, platform = @platform, timestamp = @timestamp,
      status = @status, location = @location, url = @url, referral = @referral, notes = @notes
    WHERE id = @id
  `).run(merged);

  res.json(db.prepare("SELECT * FROM jobs WHERE id = ?").get(req.params.id));
});

app.delete("/api/jobs/:id", (req, res) => {
  const info = db.prepare("DELETE FROM jobs WHERE id = ?").run(req.params.id);
  if (info.changes === 0) return res.status(404).json({ error: "Job not found." });
  res.status(204).end();
});

// ---------------------------------------------------------------------------
// API — Discovered jobs (PRD req. 30-32)
//
// Entirely additive: no existing /api/jobs* route or the `jobs` table changes.
// The status machine in lib/statusMachine.js is the single
// authority on legal transitions — these handlers never write `status`
// directly, so no endpoint can quietly move a row to `tailored` without going
// through the confirmation + generation path (PRD §8).
// ---------------------------------------------------------------------------
const asRow = (row) => (row ? { ...row, sources: JSON.parse(row.sources || "[]") } : row);

// Newest-first by the date the table actually shows — posted_date, falling
// back to first_seen_at when a connector gave none. Sorting on first_seen_at
// alone put an Aug 4 posting above an Aug 11 one, because a single ingest run
// stamps every row it brings back with the same second and the tie then fell
// through to insertion order.
//
// Dates are compared as parsed timestamps, not strings: posted_date arrives in
// whatever format each board emits ("Thu, 14 May 2026 09:14:28 +0000" from an
// RSS feed, "2026-09-03T19:30:20-04:00" from a JSON API), so a lexical compare
// across two sources is meaningless. Rows whose date will not parse sort last
// rather than jumping to the top on a NaN comparison.
function postedTime(row) {
  const d = parseDate(row.posted_date) || parseDate(row.first_seen_at);
  return d ? d.getTime() : null;
}

function byNewestPosted(a, b) {
  const ta = postedTime(a);
  const tb = postedTime(b);
  if (ta === null && tb === null) return 0;
  if (ta === null) return 1;
  if (tb === null) return -1;
  return tb - ta;
}

// Wraps a handler so a thrown TransitionError (409) or not-found (404)
// becomes a clean JSON error instead of an unhandled rejection.
const handle = (fn) => async (req, res) => {
  try {
    await fn(req, res);
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
};

// Rows that still need a decision from the user — the default view.
const ACTIVE_STATUSES = ["new", "queued", "generating", "tailored"];

// The discovered feed. Archived rows are hidden by default (req. 31).
//
// Query params, all optional:
//   status=active|all|<one status>
//                           active (default) is the needs-a-decision set;
//                           all is everything except archived.
//   q=text                  substring match on title / company / location /
//                           source. Runs over the whole table, not just the
//                           rows a client happens to be holding.
//   sort=mix|score|recent   score (default) is a flat best-first ranking; mix
//                           interleaves buckets in your configured location
//                           proportions; recent is newest-first by posted_date
//                           (first_seen_at when a connector gave no date).
//   maxAgeDays=N            posted within N days; 0 disables the filter.
//                           Defaults to preferences.maxAgeDays - a one-off
//                           override for browsing, not a config edit.
//   hideApplied=0           include roles already in your applied log.
//   bucket=calgary,remote   restrict to these location buckets. Comma-
//                           separated; omit for all of them.
//
// The freshness filter lives here rather than only at ingest because a row
// ingested three days ago is stale today - the database is a log, and the feed
// is a view over it. (The ingest window itself is persisted to
// preferences.json by /api/discover, so it, this default, and
// scripts/rescore.js all agree on the same value between runs.)
app.get("/api/discovered", (req, res) => {
  const prefs = loadPreferences();
  const status = req.query.status || "active";
  const sort = ["mix", "score", "recent"].includes(req.query.sort) ? req.query.sort : "score";
  const maxAgeDays =
    req.query.maxAgeDays === undefined ? prefs.maxAgeDays : Number(req.query.maxAgeDays);
  // Asking to see applied or archived rows and then hiding them would empty the
  // table out from under the request, so the narrower filter wins.
  const hideApplied = req.query.hideApplied !== "0" && !["applied", "archived"].includes(status);

  // `bucket` is a comma-separated list: the location filter is multi-select,
  // so "Calgary + Remote" is one request rather than two.
  const buckets = String(req.query.bucket || "")
    .split(",")
    .map((b) => b.trim())
    .filter(Boolean);

  const where = [];
  const params = { status };
  if (status === "active") where.push(`status IN (${ACTIVE_STATUSES.map((s) => `'${s}'`).join(", ")})`);
  else if (status === "all") where.push("status != 'archived'");
  else where.push("status = @status");

  if (hideApplied) where.push("status != 'applied'");
  if (buckets.length) {
    // Bound as named parameters rather than interpolated — these arrive
    // straight off the query string.
    buckets.forEach((b, i) => (params[`bucket${i}`] = b));
    where.push(`location_bucket IN (${buckets.map((_, i) => `@bucket${i}`).join(", ")})`);
  }

  let rows = db
    .prepare(
      `SELECT * FROM discovered_jobs
       ${where.length ? `WHERE ${where.join(" AND ")}` : ""}
       ORDER BY match_score IS NULL, match_score DESC, first_seen_at DESC, id DESC`
    )
    .all(params);

  const total = rows.length;

  const q = String(req.query.q || "").trim().toLowerCase();
  if (q) {
    rows = rows.filter((row) =>
      [row.title, row.company, row.location, row.sources].join(" ").toLowerCase().includes(q)
    );
  }

  // Freshness in JS rather than SQL: posted_date arrives in whatever format
  // each board emits, and isFresh() already knows how to fall back to
  // first_seen_at when a connector gave no date at all.
  if (Number.isFinite(maxAgeDays) && maxAgeDays > 0) {
    rows = rows.filter((row) => isFresh(row, { maxAgeDays }));
  }

  // Same reasoning as the freshness filter above: rows ingested before this
  // gate existed (or whose description changed since) still need to be kept
  // out of the feed, not just future ones.
  rows = rows.filter((row) => !exceedsExperienceCap(row));

  // Roles logged by hand in the applied log, which never passed through the
  // discovery flow and so still read as 'new' here.
  if (hideApplied) {
    const appliedIndex = buildAppliedIndex(db);
    rows = rows.filter((row) => !isAlreadyApplied(row, appliedIndex));
  }

  rows = rows.map(asRow);
  if (sort === "mix") rows = weightedMix(rows, prefs);
  else if (sort === "recent") rows.sort(byNewestPosted);

  res.json({
    jobs: rows,
    meta: {
      total,
      shown: rows.length,
      sort,
      status,
      query: q || null,
      maxAgeDays: Number.isFinite(maxAgeDays) && maxAgeDays > 0 ? maxAgeDays : null,
      hideApplied,
      locationWeights: prefs.locationWeights,
      // null and "unknown" are different failures: null means a location was
      // stated and matched none of your buckets, "unknown" means none was
      // stated at all. Only legacy rows carry either, since the ingest gate
      // now drops off-list postings outright.
      buckets: rows.reduce((acc, r) => {
        const b = r.location_bucket || "off-list";
        acc[b] = (acc[b] || 0) + 1;
        return acc;
      }, {}),
    },
  });
});

// req. 19/31: source health for the persistent banner.
app.get("/api/discovered/sources", (req, res) => {
  res.json(db.prepare("SELECT * FROM sources ORDER BY status DESC, name ASC").all());
});

app.get("/api/discovered/:id", (req, res) => {
  const row = db.prepare("SELECT * FROM discovered_jobs WHERE id = ?").get(req.params.id);
  if (!row) return res.status(404).json({ error: "Discovered job not found." });
  res.json(asRow(row));
});

// req. 22: the confirmation preview. Shows the *exact* prompt that will be
// sent, built by the same function the real invocation uses, plus which
// injection rules the sanitizer fired (req. 24) so a scrubbed posting is
// visible to the user rather than silently altered behind their back.
app.get("/api/discovered/:id/preview", handle((req, res) => {
  const row = db.prepare("SELECT * FROM discovered_jobs WHERE id = ?").get(req.params.id);
  if (!row) return res.status(404).json({ error: "Discovered job not found." });
  const built = buildTailoringPrompt(asRow(row));
  res.json({
    job: asRow(row),
    prompt: built.prompt,
    posting: built.posting,
    outputPath: built.outputPath,
    baseResumePath: built.baseResumePath,
    sanitization: built.sanitization,
  });
}));

// req. 21: the user-triggerable transitions — queue, reject, dismiss, and the
// explicit manual reset that un-terminates a rejected row. `generating` and
// `tailored` are deliberately not reachable here.
app.post("/api/discovered/:id/status", handle((req, res) => {
  const to = (req.body || {}).status;
  if (!USER_TRIGGERABLE.includes(to)) {
    return res.status(400).json({
      error: `status must be one of: ${USER_TRIGGERABLE.join(", ")} (reaching "tailored" requires the tailoring flow).`,
    });
  }
  res.json(asRow(transition(db, req.params.id, to)));
}));

// req. 21-22: the approval gate. Clicking "Tailor" on a row *is* the
// confirmation — it names one specific posting, and nothing generates without
// it — so the row is queued here rather than in a second preview step the user
// has to click through. `tailorJob` still refuses anything that isn't `queued`,
// so the state machine remains the thing enforcing it (PRD §8), not this
// handler's good manners.
//
// What the removed preview used to surface — that the sanitizer scrubbed
// injection patterns out of a posting (req. 24) — comes back in the response
// so the caller can still show it. It must not become invisible just because
// the screen it lived on is gone.
app.post("/api/discovered/:id/tailor", handle(async (req, res) => {
  const row = db.prepare("SELECT id, status FROM discovered_jobs WHERE id = ?").get(req.params.id);
  if (!row) return res.status(404).json({ error: "Discovered job not found." });
  if (row.status === "new") transition(db, row.id, "queued");

  const result = await tailorJob(db, req.params.id);
  res.status(result.ok ? 200 : 502).json({
    ok: result.ok,
    job: asRow(result.job),
    error: result.error || null,
    traceability: result.traceability || null,
    sanitization: result.sanitization || null,
  });
}));

// The tailored draft as a file download. The dashboard hits this straight after
// a successful generation, so "Tailor" ends with a file in the user's
// downloads rather than in a modal they have to copy out of.
//
// Converted to PDF on the way out, not at generation time: application forms
// take PDF, not the .md Claude writes, and rendering on demand means an
// applicant who hand-edits the draft on disk still gets the current content,
// not a stale snapshot from generation time.
app.get("/api/discovered/:id/draft/download", handle(async (req, res) => {
  const row = db.prepare("SELECT * FROM discovered_jobs WHERE id = ?").get(req.params.id);
  if (!row) return res.status(404).json({ error: "Discovered job not found." });
  if (!row.resume_path) return res.status(404).json({ error: "No tailored draft for this job yet." });
  if (!existsSync(row.resume_path)) {
    return res.status(410).json({ error: `Draft file is missing from disk: ${row.resume_path}` });
  }
  const markdown = readFileSync(row.resume_path, "utf8");
  const pdf = await renderMarkdownToPdf(markdown);
  const filename = `${path.basename(row.resume_path, ".md")}.pdf`;
  res.setHeader("Content-Type", "application/pdf");
  res.setHeader("Content-Disposition", `attachment; filename="${filename}"`);
  res.send(pdf);
}));

// req. 23 / §6: the draft plus its flagged lines, returned together with the
// base resume so the approval view can highlight flags directly against it
// rather than tucking them in a separate log.
app.get("/api/discovered/:id/draft", handle((req, res) => {
  const row = db.prepare("SELECT * FROM discovered_jobs WHERE id = ?").get(req.params.id);
  if (!row) return res.status(404).json({ error: "Discovered job not found." });
  if (!row.resume_path) return res.status(404).json({ error: "No tailored draft for this job yet." });
  if (!existsSync(row.resume_path)) {
    return res.status(410).json({ error: `Draft file is missing from disk: ${row.resume_path}` });
  }

  const draft = readFileSync(row.resume_path, "utf8");
  const built = buildTailoringPrompt(asRow(row));
  const traceability = checkTraceability(draft, built.baseResume);
  const overrides = db
    .prepare("SELECT * FROM overrides WHERE discovered_job_id = ? ORDER BY timestamp ASC")
    .all(row.id);

  // A flagged line the user has already overridden is resolved, not
  // outstanding — the audit trail is what clears it.
  const overridden = new Set(overrides.map((o) => o.flagged_text));
  res.json({
    job: asRow(row),
    draft,
    baseResume: built.baseResume,
    baseResumePath: built.baseResumePath,
    traceability: {
      ...traceability,
      flagged: traceability.flagged.map((f) => ({ ...f, overridden: overridden.has(f.text) })),
    },
    overrides,
  });
}));

// req. 23: approving a flagged line requires a short reason, written to the
// audit trail. This is the only way a below-threshold line is accepted —
// nothing gets silently rubber-stamped past a fabrication flag.
app.post("/api/discovered/:id/overrides", handle((req, res) => {
  const { flagged_text: flaggedText, reason } = req.body || {};
  if (!flaggedText || !String(reason || "").trim()) {
    return res.status(400).json({ error: "flagged_text and a non-empty reason are both required." });
  }
  const row = db.prepare("SELECT id FROM discovered_jobs WHERE id = ?").get(req.params.id);
  if (!row) return res.status(404).json({ error: "Discovered job not found." });

  const info = db
    .prepare("INSERT INTO overrides (discovered_job_id, flagged_text, reason) VALUES (?, ?, ?)")
    .run(row.id, flaggedText, String(reason).trim());
  res.status(201).json(db.prepare("SELECT * FROM overrides WHERE id = ?").get(info.lastInsertRowid));
}));

app.get("/api/discovered/:id/overrides", (req, res) => {
  res.json(
    db.prepare("SELECT * FROM overrides WHERE discovered_job_id = ? ORDER BY timestamp ASC").all(req.params.id)
  );
});

// req. 32: mark applied — creates the corresponding row in the existing
// applied-jobs log, pre-filled from the discovered job, and links the two via
// applied_job_id. Wrapped in a transaction so a discovered row can never end
// up `applied` without its `jobs` row, or vice versa.
app.post("/api/discovered/:id/apply", handle((req, res) => {
  const row = db.prepare("SELECT * FROM discovered_jobs WHERE id = ?").get(req.params.id);
  if (!row) return res.status(404).json({ error: "Discovered job not found." });

  const body = req.body || {};
  const sources = JSON.parse(row.sources || "[]");

  const run = db.transaction(() => {
    const info = db
      .prepare(
        `INSERT INTO jobs (title, company, platform, timestamp, status, location, url, referral, notes)
         VALUES (@title, @company, @platform, @timestamp, @status, @location, @url, @referral, @notes)`
      )
      .run({
        title: body.title || row.title,
        company: body.company || row.company,
        // The discovered board is the platform — that's what the user applied through.
        platform: body.platform || sources[0] || "Company Site",
        timestamp: body.timestamp || new Date().toISOString(),
        status: body.status || "applied",
        location: body.location ?? row.location ?? null,
        url: body.url || row.apply_url,
        referral: body.referral ? 1 : 0,
        notes: body.notes ?? (row.resume_path ? `Tailored resume: ${row.resume_path}` : null),
      });
    const appliedJobId = info.lastInsertRowid;
    const updated = transition(db, row.id, "applied", { applied_job_id: appliedJobId });
    return { updated, appliedJobId };
  });

  const { updated, appliedJobId } = run();
  res.status(201).json({
    discovered: asRow(updated),
    job: db.prepare("SELECT * FROM jobs WHERE id = ?").get(appliedJobId),
  });
}));

// ---------------------------------------------------------------------------
// API — discovery runs
// ---------------------------------------------------------------------------
// Discovery is driven from the Refresh button in the Discovered view. It runs
// as a child process rather than inline: a run takes minutes, drives Playwright
// against real job boards, and writes thousands of rows. Forking keeps the
// dashboard responsive while it works, and keeps a connector that crashes hard
// from taking the server down with it.
//
// State is deliberately in-memory and single-slot. There is one user and one
// database; a run history would be a second source of truth about what the
// feed already shows.
const DISCOVER_SCRIPT = path.join(__dirname, "discover.js");
const SOURCES_CONFIG = path.join(__dirname, "config", "sources.json");
const MAX_LOG_LINES = 400;

let run = null;

function startDiscoveryRun() {
  // The freshness control is a filter on the *run*, not just on the table -
  // the ingest gate drops a stale posting before it is ever written. Its value
  // is persisted to preferences.json by the caller before this is invoked, so
  // discover.js's own loadPreferences() call picks it up directly.
  const child = spawn(process.execPath, [DISCOVER_SCRIPT], { cwd: __dirname, env: process.env });

  run = {
    status: "running",
    startedAt: new Date().toISOString(),
    finishedAt: null,
    exitCode: null,
    log: [],
    child,
  };

  // discover.js already prints a structured run summary — the gate tolls, the
  // insert count, the per-source failures. Streaming its stdout verbatim means
  // the button reports exactly what the CLI did, with no second format to keep
  // in sync.
  const append = (chunk) => {
    // Windows line endings arrive as "line\r"; trimEnd strips the CR while
    // leaving the summary’s leading indentation intact.
    for (const raw of chunk.toString().split("\n")) {
      const line = raw.trimEnd();
      if (line !== "") run.log.push(line);
    }
    if (run.log.length > MAX_LOG_LINES) run.log.splice(0, run.log.length - MAX_LOG_LINES);
  };
  child.stdout.on("data", append);
  child.stderr.on("data", append);

  child.on("error", (err) => {
    run.status = "failed";
    run.finishedAt = new Date().toISOString();
    run.child = null;
    run.log.push(`could not start discovery: ${err.message}`);
  });

  child.on("close", (code) => {
    run.status = code === 0 ? "done" : "failed";
    run.exitCode = code;
    run.finishedAt = new Date().toISOString();
    run.child = null;
  });

  return run;
}

// The child handle is not serializable, and the client has no use for it.
const runState = () => {
  if (!run) return { status: "idle", log: [] };
  const { child, ...rest } = run;
  return rest;
};

app.post("/api/discover", (req, res) => {
  if (run?.status === "running") {
    return res.status(409).json({ error: "A discovery run is already in progress." });
  }
  if (!existsSync(SOURCES_CONFIG)) {
    return res
      .status(400)
      .json({ error: 'config/sources.json not found. Run "npm run bootstrap-sources" first.' });
  }
  // No freshness value is read from the request any more. The control saves
  // its own choice through POST /api/preferences the moment it changes, and
  // discover.js calls loadPreferences() itself, so the run already uses the
  // selected window. Accepting it here as well gave two writers for one value.
  startDiscoveryRun();
  res.status(202).json(runState());
});

app.get("/api/discover/status", (req, res) => res.json(runState()));

// The stored preferences the dashboard's controls need to render themselves.
//
// This exists so the freshness dropdown can be *built* from the saved value
// instead of shipping its own default. The markup used to hard-code
// `<option value="3" selected>`, which meant the control always booted to 3
// days no matter what was saved — and because the Refresh button persists
// whatever the control reads, that invented 3 overwrote the stored value on
// every run. The number you pick is now the only number in play.
// The only writer of the freshness window. The control persists a change the
// moment it is made, so the value survives a page reload and the next
// discovery run reads the same one — rather than the window being a
// browser-session thing that a run had to be told about separately.
app.post("/api/preferences", (req, res) => {
  const requested = (req.body || {}).maxAgeDays;
  if (requested === undefined) {
    return res.status(400).json({ error: "maxAgeDays is required." });
  }
  const days = Number(requested);
  if (!Number.isFinite(days) || days < 0) {
    return res.status(400).json({ error: "maxAgeDays must be a number of days, or 0 for no limit." });
  }
  // 0 is the UI's "Any age"; stored as null since Infinity isn't valid JSON
  // (loadPreferences() converts it back on read).
  const prefs = savePreferences({ maxAgeDays: days === 0 ? null : days });
  res.json({ maxAgeDays: Number.isFinite(prefs.maxAgeDays) ? prefs.maxAgeDays : null });
});

app.get("/api/preferences", (req, res) => {
  const prefs = loadPreferences({ reload: true });
  res.json({
    // Infinity is not valid JSON; null is how "no age limit" travels, the same
    // way it is stored (see savePreferences).
    maxAgeDays: Number.isFinite(prefs.maxAgeDays) ? prefs.maxAgeDays : null,
    archiveAfterDays: prefs.archiveAfterDays,
    locationWeights: prefs.locationWeights,
  });
});

// ---------------------------------------------------------------------------
// API — CSV export (every column, for spreadsheet-side analysis)
// ---------------------------------------------------------------------------
app.get("/api/export", (req, res) => {
  const jobs = db.prepare("SELECT * FROM jobs ORDER BY timestamp ASC").all();
  const headers = ["id", ...COLUMNS, "created_at"];
  const escape = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const csv = [
    headers.join(","),
    ...jobs.map((j) => headers.map((h) => escape(j[h])).join(","))
  ].join("\n");

  res.setHeader("Content-Type", "text/csv");
  res.setHeader("Content-Disposition", 'attachment; filename="job-applications.csv"');
  res.send(csv);
});

app.listen(PORT, () => {
  console.log(`\n  Job Application Tracker running at http://localhost:${PORT}\n`);
});

// ---------------------------------------------------------------------------
// Graceful shutdown — flush WAL on Ctrl+C
// ---------------------------------------------------------------------------
function shutdown(signal) {
  console.log(`\nReceived ${signal}. Flushing WAL and shutting down...`);

  // Otherwise a half-finished discovery run keeps scraping, and the Playwright
  // browsers it started outlive the server that started them.
  if (run?.child) run.child.kill();

  try {
    // Force checkpoint: merge WAL into main DB
    db.pragma("wal_checkpoint(FULL)");

    // Close database connection cleanly
    db.close();

    console.log("Database safely closed.");
  } catch (err) {
    console.error("Error during shutdown:", err);
  } finally {
    process.exit(0);
  }
}

process.on("SIGINT", shutdown);   // Ctrl+C
process.on("SIGTERM", shutdown);  // e.g. Docker stop