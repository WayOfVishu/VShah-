#!/usr/bin/env node
// What the daily scheduled task runs (installed by scripts/schedule-discovery.js).
//
// Starts discover.js exactly as the Refresh button does. The difference is
// that nobody is watching: the run summary the dashboard would have streamed
// goes to logs/discover-<date>_<time>.log instead, and the newest 30 are kept.
// The feed itself needs nothing from here — the run writes jobs.db, and the
// dashboard reads whatever is in it the next time it's opened.

import { spawn } from "node:child_process";
import { mkdirSync, openSync, closeSync, writeSync, readdirSync, unlinkSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const APP_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const LOG_DIR = path.join(APP_DIR, "logs");
const KEEP_LOGS = 30;

const pad = (n) => String(n).padStart(2, "0");
const now = new Date();
const stamp =
  `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}` + `_${pad(now.getHours())}${pad(now.getMinutes())}`;

mkdirSync(LOG_DIR, { recursive: true });
const logPath = path.join(LOG_DIR, `discover-${stamp}.log`);
const fd = openSync(logPath, "a");
writeSync(fd, `Scheduled discovery run, started ${now.toLocaleString()}\n\n`);

// Timestamped names sort chronologically, so the oldest are simply the first.
function pruneLogs() {
  const logs = readdirSync(LOG_DIR)
    .filter((f) => /^discover-.*\.log$/.test(f))
    .sort();
  for (const old of logs.slice(0, Math.max(0, logs.length - KEEP_LOGS))) {
    try {
      unlinkSync(path.join(LOG_DIR, old));
    } catch {
      // a log another process has open; next run will get it
    }
  }
}

const child = spawn(process.execPath, [path.join(APP_DIR, "discover.js")], {
  cwd: APP_DIR,
  stdio: ["ignore", fd, fd],
  windowsHide: true,
});

child.on("error", (err) => {
  writeSync(fd, `\nCould not start discover.js: ${err.message}\n`);
  closeSync(fd);
  process.exit(1);
});

child.on("close", (code) => {
  writeSync(fd, `\nFinished ${new Date().toLocaleString()}, exit code ${code}\n`);
  closeSync(fd);
  pruneLogs();
  // Passed through so Task Scheduler's "Last Run Result" means something.
  process.exit(code ?? 1);
});
