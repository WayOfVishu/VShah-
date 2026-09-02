#!/usr/bin/env node
// Reports or applies the current config/preferences.json against rows already
// in the database.
//
// You do not normally need this. Every discovery run — the Refresh button in
// the dashboard — re-applies your preferences to existing rows as its second
// phase, so changing a filter and hitting Refresh is the whole workflow.
//
// What this script still gives you is the --dry-run report: what *would*
// change, without touching anything.
//
// Usage:
//   node scripts/rescore.js --dry-run  report what would change, touch nothing
//   node scripts/rescore.js            apply now, without a discovery run

import Database from "better-sqlite3";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { applyMigrations } from "../db/migrate.js";
import { loadPreferences } from "../lib/preferences.js";
import { rescoreRows, activeCount, countsByBucket } from "../lib/rescore.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DB_PATH = process.env.JOBS_DB_PATH || path.join(__dirname, "..", "jobs.db");
const dryRun = process.argv.includes("--dry-run");

function main() {
  const db = new Database(DB_PATH);
  db.pragma("journal_mode = WAL");
  applyMigrations(db);

  const prefs = loadPreferences();
  const counts = rescoreRows(db, prefs, { dryRun });

  const active = dryRun
    ? counts.scored - Object.values(counts.reasons).reduce((a, b) => a + b, 0)
    : activeCount(db);

  console.log(`\n=== Rescore${dryRun ? " (dry run — nothing written)" : ""} ===`);
  console.log(`  Rows considered:  ${counts.scored}`);
  console.log(`  Newly archived:   ${counts.archived}`);
  console.log(`  Restored to new:  ${counts.restored}`);
  console.log(`  Left as-is:       ${counts.unchanged}`);
  if (Object.keys(counts.reasons).length) {
    console.log(`  Archived because:`);
    for (const [reason, n] of Object.entries(counts.reasons).sort((a, b) => b[1] - a[1])) {
      console.log(`    - ${reason}: ${n}`);
    }
  }
  console.log(`  Active feed now:  ${active}`);

  if (!dryRun) {
    const byBucket = countsByBucket(db);
    if (byBucket.length) {
      console.log(`  By location:`);
      for (const b of byBucket) console.log(`    - ${b.bucket}: ${b.n}`);
    }
  }

  db.close();
}

main();
