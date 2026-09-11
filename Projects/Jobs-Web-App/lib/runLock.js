// One discovery run at a time, however it was started.
//
// server.js's in-memory `run` slot already stops two Refresh clicks from
// overlapping, but the daily scheduled task starts discover.js from outside the
// server, where that slot can't see it. Two overlapping runs each build their
// dedup index at start-up, so both try to insert the same new posting, and the
// second trips the UNIQUE index on apply_url and dies halfway through. A lock
// file next to the database is the one thing both entry points can see.

import { openSync, writeSync, closeSync, readFileSync, unlinkSync } from "node:fs";

// A run that has held the lock this long is hung or its process id has been
// recycled; either way it should not block the next one forever.
export const STALE_AFTER_MS = 3 * 60 * 60 * 1000;

function processAlive(pid) {
  try {
    process.kill(pid, 0); // signal 0 = existence check, sends nothing
    return true;
  } catch (err) {
    return err.code === "EPERM"; // exists, just not ours to signal
  }
}

function readHolder(lockPath) {
  try {
    return JSON.parse(readFileSync(lockPath, "utf8"));
  } catch {
    return null;
  }
}

// Returns { acquired: true, release } or { acquired: false, holder }.
//
// A lock whose process is gone — killed from Task Manager, or by the server's
// shutdown handler, neither of which runs exit hooks — is taken over rather
// than obeyed.
export function acquireRunLock(lockPath, { pid = process.pid, now = Date.now(), isAlive = processAlive } = {}) {
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const fd = openSync(lockPath, "wx");
      writeSync(fd, JSON.stringify({ pid, startedAt: new Date(now).toISOString() }));
      closeSync(fd);
      return {
        acquired: true,
        // Only removes the file if it is still ours, so a run that was judged
        // stale and superseded can't delete its successor's lock on the way out.
        release() {
          if (readHolder(lockPath)?.pid !== pid) return;
          try {
            unlinkSync(lockPath);
          } catch {
            // already gone
          }
        },
      };
    } catch (err) {
      if (err.code !== "EEXIST") throw err;
    }

    const holder = readHolder(lockPath);
    const age = holder?.startedAt ? now - Date.parse(holder.startedAt) : Infinity;
    if (holder && isAlive(holder.pid) && age < STALE_AFTER_MS) return { acquired: false, holder };
    try {
      unlinkSync(lockPath);
    } catch {
      // someone else cleared it first; the retry decides who wins
    }
  }
  return { acquired: false, holder: readHolder(lockPath) };
}
