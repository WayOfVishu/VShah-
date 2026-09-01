import express from "express";
import Database from "better-sqlite3";
import path from "path";
import { readFileSync, existsSync } from "fs";
import { fileURLToPath } from "url";

import { applyMigrations } from "./db/migrate.js";
import { transition, USER_TRIGGERABLE } from "./lib/statusMachine.js";
import { buildTailoringPrompt } from "./lib/promptBuild.js";
import { checkTraceability } from "./lib/traceabilityCheck.js";
import { tailorJob } from "./lib/tailorInvoke.js";
import { loadPreferences } from "./lib/preferences.js";
import { weightedMix } from "./lib/scoring.js";
import { isFresh, buildAppliedIndex, isAlreadyApplied } from "./lib/jobFilter.js";

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

// Wraps a handler so a thrown TransitionError (409) or not-found (404)
// becomes a clean JSON error instead of an unhandled rejection.
const handle = (fn) => async (req, res) => {
  try {
    await fn(req, res);
  } catch (err) {
    res.status(err.statusCode || 500).json({ error: err.message });
  }
};

// The discovered feed. Archived rows are hidden by default (req. 31).
//
// Query params, all optional:
//   sort=mix|score|recent   mix (default) interleaves buckets in your
//                           configured location proportions; score is a flat
//                           best-first ranking; recent is newest-first.
//   maxAgeDays=N            posted within N days; 0 disables the filter.
//                           Defaults to preferences.maxAgeDays.
//   hideApplied=0           include roles already in your applied log.
//   bucket=calgary          restrict to one location bucket.
//
// The freshness filter lives here rather than only at ingest because a row
// ingested three days ago is stale today - the database is a log, and the feed
// is a view over it.
app.get("/api/discovered", (req, res) => {
  const prefs = loadPreferences();
  const includeArchived = req.query.includeArchived === "1";
  const hideApplied = req.query.hideApplied !== "0";
  const sort = ["mix", "score", "recent"].includes(req.query.sort) ? req.query.sort : "mix";
  const maxAgeDays =
    req.query.maxAgeDays === undefined ? prefs.maxAgeDays : Number(req.query.maxAgeDays);

  const where = [];
  if (!includeArchived) where.push("status != 'archived'");
  if (hideApplied) where.push("status != 'applied'");
  if (req.query.bucket) where.push("location_bucket = @bucket");

  let rows = db
    .prepare(
      `SELECT * FROM discovered_jobs
       ${where.length ? `WHERE ${where.join(" AND ")}` : ""}
       ORDER BY match_score IS NULL, match_score DESC, first_seen_at DESC, id DESC`
    )
    .all({ bucket: req.query.bucket || null });

  const total = rows.length;

  // Freshness in JS rather than SQL: posted_date arrives in whatever format
  // each board emits, and isFresh() already knows how to fall back to
  // first_seen_at when a connector gave no date at all.
  if (Number.isFinite(maxAgeDays) && maxAgeDays > 0) {
    rows = rows.filter((row) => isFresh(row, { maxAgeDays }));
  }

  // Roles logged by hand in the applied log, which never passed through the
  // discovery flow and so still read as 'new' here.
  if (hideApplied) {
    const appliedIndex = buildAppliedIndex(db);
    rows = rows.filter((row) => !isAlreadyApplied(row, appliedIndex));
  }

  rows = rows.map(asRow);
  if (sort === "mix") rows = weightedMix(rows, prefs);
  else if (sort === "recent") {
    rows.sort((a, b) => String(b.first_seen_at).localeCompare(String(a.first_seen_at)));
  }

  res.json({
    jobs: rows,
    meta: {
      total,
      shown: rows.length,
      sort,
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

// req. 21-22: "Confirm & Generate". The single approval gate — task 1.0
// established there is no second, tool-level prompt behind this one.
app.post("/api/discovered/:id/tailor", handle(async (req, res) => {
  const result = await tailorJob(db, req.params.id);
  res.status(result.ok ? 200 : 502).json({
    ok: result.ok,
    job: asRow(result.job),
    error: result.error || null,
    traceability: result.traceability || null,
  });
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