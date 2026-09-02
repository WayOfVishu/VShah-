// Re-applies the current preferences to rows already in the database.
//
// The database is a log and the feed is a view over it, so changing a
// preference has to re-judge what was already stored — a row saved under a
// 7-day window is not necessarily one you still want to see under a 3-day one,
// and a row archived under 7 days should come back when you widen to 21.
//
// This used to be reachable only as `node scripts/rescore.js`, which meant
// every preference change came with a terminal chore you had to remember. It
// now runs as part of every discovery run (see discover.js), so changing a
// filter and hitting Refresh is the whole workflow. The script remains as a
// thin wrapper for the --dry-run report.
//
// Rows that fail the gate are archived, not deleted: archiving is reversible
// from the dashboard's Restore button, and a preference change should never be
// the thing that silently destroys a posting you might want back.

import { scoreJob } from "./scoring.js";
import { isFresh, matchesRole, isExcludedBySeniority, buildAppliedIndex, isAlreadyApplied } from "./jobFilter.js";

// Rows the user has already acted on are left alone. Archiving something you
// queued for tailoring, or that is already logged as applied, would undo your
// own decisions in the name of a config change.
export const REWORKABLE = ["new", "archived"];

export function rescoreRows(db, prefs, { dryRun = false } = {}) {
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

  return counts;
}

export function activeCount(db) {
  return db.prepare("SELECT COUNT(*) AS n FROM discovered_jobs WHERE status = 'new'").get().n;
}

export function countsByBucket(db) {
  return db
    .prepare(
      `SELECT COALESCE(location_bucket,'unknown') AS bucket, COUNT(*) AS n
         FROM discovered_jobs WHERE status = 'new'
        GROUP BY bucket ORDER BY n DESC`
    )
    .all();
}
