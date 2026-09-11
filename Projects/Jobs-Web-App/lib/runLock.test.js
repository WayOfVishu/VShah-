import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, existsSync, writeFileSync, readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { acquireRunLock, STALE_AFTER_MS } from "./runLock.js";

const freshLockPath = () => path.join(mkdtempSync(path.join(os.tmpdir(), "runlock-")), "jobs.db.discover.lock");

test("the first run takes the lock and releasing it removes the file", () => {
  const lockPath = freshLockPath();
  const lock = acquireRunLock(lockPath, { pid: 101 });
  assert.equal(lock.acquired, true);
  assert.equal(JSON.parse(readFileSync(lockPath, "utf8")).pid, 101);
  lock.release();
  assert.equal(existsSync(lockPath), false);
});

test("a second run is turned away while the first is alive", () => {
  const lockPath = freshLockPath();
  acquireRunLock(lockPath, { pid: 101 });
  const second = acquireRunLock(lockPath, { pid: 202, isAlive: () => true });
  assert.equal(second.acquired, false);
  assert.equal(second.holder.pid, 101);
});

test("a lock left by a dead process is taken over", () => {
  const lockPath = freshLockPath();
  acquireRunLock(lockPath, { pid: 101 }); // never released: killed mid-run
  const second = acquireRunLock(lockPath, { pid: 202, isAlive: () => false });
  assert.equal(second.acquired, true);
  assert.equal(JSON.parse(readFileSync(lockPath, "utf8")).pid, 202);
});

test("a lock held past the stale limit is taken over even if the pid looks alive", () => {
  const lockPath = freshLockPath();
  const now = Date.now();
  acquireRunLock(lockPath, { pid: 101, now: now - STALE_AFTER_MS - 1000 });
  const second = acquireRunLock(lockPath, { pid: 202, now, isAlive: () => true });
  assert.equal(second.acquired, true);
});

test("a superseded run's release doesn't delete its successor's lock", () => {
  const lockPath = freshLockPath();
  const first = acquireRunLock(lockPath, { pid: 101 });
  acquireRunLock(lockPath, { pid: 202, isAlive: () => false });
  first.release();
  assert.equal(JSON.parse(readFileSync(lockPath, "utf8")).pid, 202);
});

test("an unreadable lock file is treated as stale", () => {
  const lockPath = freshLockPath();
  writeFileSync(lockPath, "not json");
  assert.equal(acquireRunLock(lockPath, { pid: 303 }).acquired, true);
});
