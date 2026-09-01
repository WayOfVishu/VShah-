#!/usr/bin/env node
// Applies the current config/preferences.json to rows that are already in the
// database - the ~2900 postings ingested before any filtering existed, and any
// row already stored when you later change your preferences.
//
// Rows that fail the gate are archived, not deleted: archiving is reversible
// from the dashboard ("Restore"), and a preference change should never be the
// thing that silently destroys a posting you might want back.
//
// Usage:
//   node scripts/rescore.js            apply the changes
//   node scripts/rescore.js --dry-run  report what would change, touch nothing

import Database from "better-sqlite3";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { applyMigrations } from "../db/migrate.js";
import { loadPreferences } from "../lib/preferences.js";
import { scoreJob } from "../lib/scoring.js";
import {
  isFresh,
  matchesRole,
  isExcludedBySeniority,
  buildAppliedIndex,
  isAlreadyApplied,
} from "../lib/jobFilter.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DB_PATH = process.env.JOBS_DB_PATH || path.join(__dirname, "..", "jobs.db");
const dryRun = process.argv.includes("--dry-run");

// Rows the user has already acted on are left alone. Archiving something you
// queued for tailoring, or that is already logged as applied, would undo your
// own decisions in the name of a config change.
const REWORKABLE = ["new", "archived"];

function main() {
  const db = new Database(DB_PATH);
  db.pragma("journal_mode = WAL");
  applyMigrations(db);

  const prefs = loadPreferences();
  const appliedIndex = buildAppliedIndex(db);
  const rows = db
    .prepare(`SELECT * FROM discovered_jobs WHERE status IN (${REWORKABLE.map(() => "?").join(",")})`)
    .all(...REWORKABLE);

  const updateStmt = db.prepare(`
    UPDATE discovered_jobs
       SET match_score = @match_score, location_bucket = @location_bucket,
           location_score = @location_score, keyword_score = @keyword_score,
           unsponsored_us = @unsponsored_us, status = @status
     WHERE id = @id
  `);

  const counts = { scored: 0, archived: 0, restored: 0, unchanged: 0, reasons: {} };
  const bump = (reason) => (counts.reasons[reason] = (counts.reasons[reason] || 0) + 1);

  const run = db.transaction(() => {
    for (const row of rows) {
      const scored = scoreJob(row, prefs);

      let reason = null;
      if (isExcludedBySeniority(row, prefs)) reason = "seniority";
      else if (!matchesRole(row, prefs)) reason = "off-role";
      else if (scored.bucket === null && prefs.offListLocations === "drop") reason = "off-location";
      else if (!isFresh(row, { maxAgeDays: prefs.maxAgeDays })) reason = "stale";
      else if (isAlreadyApplied(row, appliedIndex)) reason = "applied";

      const status = reason ? "archived" : "new";
      if (reason) bump(reason);

      if (status === "archived" && row.status !== "archived") counts.archived++;
      else if (status === "new" && row.status === "archived") counts.restored++;
      else counts.unchanged++;
      counts.scored++;

      if (!dryRun) {
        updateStmt.run({
          id: row.id,
          match_score: scored.matchScore,
          location_bucket: scored.bucket,
          location_score: scored.locationScore,
          keyword_score: scored.keywordScore,
          unsponsored_us: scored.unsponsoredUS ? 1 : 0,
          status,
        });
      }
    }
  });
  run();

  const active = dryRun
    ? counts.scored - Object.values(counts.reasons).reduce((a, b) => a + b, 0)
    : db.prepare("SELECT COUNT(*) AS n FROM discovered_jobs WHERE status = 'new'").get().n;

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
    const byBucket = db
      .prepare(
        `SELECT COALESCE(location_bucket,'unknown') AS bucket, COUNT(*) AS n
           FROM discovered_jobs WHERE status = 'new'
          GROUP BY bucket ORDER BY n DESC`
      )
      .all();
    if (byBucket.length) {
      console.log(`  By location:`);
      for (const b of byBucket) console.log(`    - ${b.bucket}: ${b.n}`);
    }
  }

  db.close();
}

main();
