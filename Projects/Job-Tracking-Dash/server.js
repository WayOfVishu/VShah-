import express from "express";
import Database from "better-sqlite3";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = process.env.PORT || 3001;

// ---------------------------------------------------------------------------
// Database
// ---------------------------------------------------------------------------
const db = new Database(path.join(__dirname, "jobs.db"));
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