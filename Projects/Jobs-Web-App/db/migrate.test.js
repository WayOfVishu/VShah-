import test from "node:test";
import assert from "node:assert/strict";
import Database from "better-sqlite3";
import { applyMigrations } from "./migrate.js";

// The migrations attach to a database that already has the dashboard's `jobs`
// table — that's the real shape of jobs.db (PRD req. 17).
function dbWithJobsTable() {
  const db = new Database(":memory:");
  db.exec(`
    CREATE TABLE jobs (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      title      TEXT NOT NULL,
      company    TEXT NOT NULL,
      platform   TEXT NOT NULL,
      timestamp  TEXT NOT NULL,
      status     TEXT NOT NULL DEFAULT 'applied',
      location   TEXT,
      url        TEXT,
      referral   INTEGER NOT NULL DEFAULT 0,
      notes      TEXT,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
  `);
  db.prepare("INSERT INTO jobs (title, company, platform, timestamp) VALUES ('Dev', 'Acme', 'LinkedIn', '2026-01-01')").run();
  return db;
}

function seedDiscovered(db, appliedJobId = null) {
  return db
    .prepare(
      `INSERT INTO discovered_jobs (job_id, sources, title, company, apply_url, status, applied_job_id)
       VALUES ('x1', '["greenhouse"]', 'Dev', 'Acme', 'https://example.test/x1', 'applied', ?)`
    )
    .run(appliedJobId).lastInsertRowid;
}

test("migrations are additive — the existing jobs table and its rows are untouched (req. 17)", () => {
  const db = dbWithJobsTable();
  const before = db.prepare("SELECT * FROM jobs").all();
  const beforeSchema = db.prepare("SELECT sql FROM sqlite_master WHERE name = 'jobs'").get().sql;

  applyMigrations(db);

  assert.deepEqual(db.prepare("SELECT * FROM jobs").all(), before);
  assert.equal(db.prepare("SELECT sql FROM sqlite_master WHERE name = 'jobs'").get().sql, beforeSchema);
  for (const table of ["discovered_jobs", "sources", "overrides"]) {
    assert.ok(
      db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name = ?").get(table),
      `expected table ${table}`
    );
  }
});

test("applyMigrations is idempotent — a second run is a no-op", () => {
  const db = dbWithJobsTable();
  applyMigrations(db);
  const id = seedDiscovered(db);
  applyMigrations(db);
  assert.equal(db.prepare("SELECT COUNT(*) c FROM discovered_jobs").get().c, 1);
  assert.equal(db.prepare("SELECT id FROM discovered_jobs WHERE id = ?").get(id).id, id);
  // Each migration file is recorded exactly once.
  const rows = db.prepare("SELECT filename, COUNT(*) c FROM schema_migrations GROUP BY filename").all();
  assert.ok(rows.every((r) => r.c === 1));
});

// task 7.5 / req. 18: deleting the linked applied-jobs row must preserve the
// discovered record and simply unlink it — never cascade-delete it.
test("deleting an applied jobs row unlinks the discovered row rather than deleting it", () => {
  const db = dbWithJobsTable();
  applyMigrations(db);
  assert.equal(db.pragma("foreign_keys", { simple: true }), 1, "foreign keys must be enforced");

  const jobId = db.prepare("SELECT id FROM jobs LIMIT 1").get().id;
  const discoveredId = seedDiscovered(db, jobId);

  db.prepare("DELETE FROM jobs WHERE id = ?").run(jobId);

  const row = db.prepare("SELECT * FROM discovered_jobs WHERE id = ?").get(discoveredId);
  assert.ok(row, "the discovered row must survive the delete");
  assert.equal(row.applied_job_id, null, "it must be unlinked, not cascade-deleted");
  assert.equal(row.status, "applied", "its own status is unaffected");
});

test("overrides cascade with their discovered job (they are its audit trail)", () => {
  const db = dbWithJobsTable();
  applyMigrations(db);
  const discoveredId = seedDiscovered(db);
  db.prepare("INSERT INTO overrides (discovered_job_id, flagged_text, reason) VALUES (?, 'x', 'y')").run(discoveredId);

  db.prepare("DELETE FROM discovered_jobs WHERE id = ?").run(discoveredId);
  assert.equal(db.prepare("SELECT COUNT(*) c FROM overrides").get().c, 0);
});

test("apply_url is UNIQUE so a re-run cannot duplicate a posting (req. 12)", () => {
  const db = dbWithJobsTable();
  applyMigrations(db);
  seedDiscovered(db);
  assert.throws(() => seedDiscovered(db), /UNIQUE/);
});

test("the status CHECK constraint rejects a status outside req. 18's set", () => {
  const db = dbWithJobsTable();
  applyMigrations(db);
  assert.throws(
    () =>
      db
        .prepare(
          `INSERT INTO discovered_jobs (job_id, sources, title, company, apply_url, status)
           VALUES ('x2', '[]', 'Dev', 'Acme', 'https://example.test/x2', 'bogus')`
        )
        .run(),
    /CHECK/
  );
});
