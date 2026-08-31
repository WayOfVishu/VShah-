import test from "node:test";
import assert from "node:assert/strict";
import Database from "better-sqlite3";
import { recordSourceSuccess, recordSourceFailure } from "./sourceHealth.js";

function freshDb() {
  const db = new Database(":memory:");
  db.exec(`
    CREATE TABLE sources (
      name            TEXT PRIMARY KEY,
      retry_count     INTEGER NOT NULL DEFAULT 0,
      status          TEXT NOT NULL DEFAULT 'ok',
      last_success_at TEXT
    )
  `);
  return db;
}

test("a single failure is render-failed, not permanent-fail (req. 4: one transient failure isn't alarming)", () => {
  const db = freshDb();
  const result = recordSourceFailure(db, "flaky-career-page");
  assert.equal(result.retryCount, 1);
  assert.equal(result.status, "render-failed");
});

test("3 consecutive failures trips permanent-fail (req. 4)", () => {
  const db = freshDb();
  recordSourceFailure(db, "broken-career-page");
  recordSourceFailure(db, "broken-career-page");
  const third = recordSourceFailure(db, "broken-career-page");

  assert.equal(third.retryCount, 3);
  assert.equal(third.status, "permanent-fail");

  const row = db.prepare("SELECT * FROM sources WHERE name = ?").get("broken-career-page");
  assert.equal(row.status, "permanent-fail");
  assert.equal(row.retry_count, 3);
});

test("a success resets retry_count and status even after prior failures", () => {
  const db = freshDb();
  recordSourceFailure(db, "recovering-source");
  recordSourceFailure(db, "recovering-source");
  recordSourceSuccess(db, "recovering-source");

  const row = db.prepare("SELECT * FROM sources WHERE name = ?").get("recovering-source");
  assert.equal(row.retry_count, 0);
  assert.equal(row.status, "ok");
  assert.ok(row.last_success_at);
});
