#!/usr/bin/env node
// Discovery run (PRD req. 13-16). Started as a child process by the Refresh
// button in the Discovered view; still runnable directly as `node discover.js`.
// Orchestrates Tier 1 + Tier 2 connectors, normalizes, dedups, inserts new
// discovered_jobs rows, prints a run summary, and sweeps stale rows into
// `archived`. No OS-level scheduler triggers this — the user runs it by hand.
// stdout is what the dashboard shows as the run log, so the summary below is
// user-facing output, not debug logging.

import Database from "better-sqlite3";
import path from "node:path";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { applyMigrations } from "./db/migrate.js";
import * as greenhouse from "./connectors/greenhouse.js";
import * as lever from "./connectors/lever.js";
import * as ashby from "./connectors/ashby.js";
import * as remotive from "./connectors/remotive.js";
import * as remoteok from "./connectors/remoteok.js";
import * as weworkremotely from "./connectors/weworkremotely.js";
import * as careerpage from "./connectors/careerpage.js";
import * as workday from "./connectors/workday.js";
import * as workable from "./connectors/workable.js";
import * as recruitee from "./connectors/recruitee.js";
import * as bamboohr from "./connectors/bamboohr.js";
import { normalize } from "./lib/normalize.js";
import { buildDedupIndex, findDuplicate, addToIndex } from "./lib/dedup.js";
import { recordSourceSuccess, recordSourceFailure } from "./lib/sourceHealth.js";
import { createRateLimiter } from "./lib/rateLimiter.js";
import { loadPreferences } from "./lib/preferences.js";
import { rescoreRows, activeCount } from "./lib/rescore.js";
import {
  ingestGate,
  buildAppliedIndex,
  isAlreadyApplied,
  matchesRole,
  isExcludedBySeniority,
  EXPERIENCE_CAP_YEARS,
} from "./lib/jobFilter.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// One SQLite file for the whole app: server.js and this CLI are two entry
// points over the same jobs.db. Override with JOBS_DB_PATH to point a run at
// a scratch copy.
const DB_PATH = process.env.JOBS_DB_PATH || path.join(__dirname, "jobs.db");
const CONFIG_PATH = path.join(__dirname, "config", "sources.json");
const DEFAULT_TIER2_RATE_LIMIT_MS = 2000;
// How many boards to fetch at once. They are all different hosts and the rate
// limiter is per-host, so this costs no single employer any extra traffic — it
// only stops the run from idling while one board's throttle counts down.
const BOARD_CONCURRENCY = 6;

// Two connector shapes, because two kinds of board.
//
// A slug board is addressed by one string and hands back its whole contents in
// one request: fetchPostings("stackadapt").
//
// An entry board needs more than a slug (Workday wants tenant + host + site),
// or has to be searched rather than listed, or withholds descriptions until a
// second request. Those take the whole config entry plus the shared throttle:
// fetchPostings(entry, opts).
const SLUG_CONNECTORS = { greenhouse, lever, ashby };
const ENTRY_CONNECTORS = { workday, workable, recruitee, bamboohr };
const rateLimiter = createRateLimiter();

// Which postings are worth a second request for their description.
//
// Workday's list endpoint and BambooHR's both omit the body, and the ingest
// gate's experience cap needs it. Fetching every posting's detail would mean
// ~900 requests against BMO alone to keep a handful. The title-level gates —
// role match and seniority exclusion — are the same ones ingestGate applies
// first and need no description, so running them here decides the question
// before we spend the request.
// Runs `fn` over `items` with at most `size` in flight.
//
// Boards are fetched concurrently because they are different hosts, and the
// rate limiter throttles per host — so two boards never wait on each other,
// and running them one after another spent the entire wall clock idle. `fn`
// returns a thunk that performs the (synchronous) database work, which the
// caller invokes in completion order: fetches overlap, writes do not.
async function mapPool(items, size, fn) {
  let i = 0;
  const workers = Array.from({ length: Math.min(size, items.length) }, async () => {
    while (i < items.length) {
      const commit = await fn(items[i++]);
      if (typeof commit === "function") commit();
    }
  });
  await Promise.all(workers);
}

function makeDetailPredicate(prefs) {
  return (rawJob) => {
    const title = rawJob.title || rawJob.jobOpeningName || "";
    return matchesRole({ title }, prefs) && !isExcludedBySeniority({ title }, prefs);
  };
}

function upsertSourcesList(existingSourcesJson, sourceName) {
  const list = JSON.parse(existingSourcesJson);
  if (!list.includes(sourceName)) list.push(sourceName);
  return JSON.stringify(list);
}

function makeIngestor(db, summary, prefs) {
  const rows = db.prepare("SELECT id, job_id, sources, title, company, location, apply_url FROM discovered_jobs").all();
  const index = buildDedupIndex(rows);
  const appliedIndex = buildAppliedIndex(db);

  const insertStmt = db.prepare(`
    INSERT INTO discovered_jobs
      (job_id, sources, title, company, location, salary, description, apply_url, posted_date, remote_status, status,
       match_score, location_bucket, location_score, keyword_score, unsponsored_us)
    VALUES
      (@job_id, @sources, @title, @company, @location, @salary, @description, @apply_url, @posted_date, @remote_status, 'new',
       @match_score, @location_bucket, @location_score, @keyword_score, @unsponsored_us)
  `);
  const mergeSourcesStmt = db.prepare("UPDATE discovered_jobs SET sources = ? WHERE id = ?");

  // Ingests one already-normalized job: applies the preference gate, then
  // merges into an existing dedup match or inserts a new row, keeping the
  // in-memory index current so later sources in the same run can also dedup
  // against it (req. 11-12).
  return function ingest(job) {
    // Rejections are counted before dedup so the summary reports what the
    // filters actually removed, not what survived them.
    const gate = ingestGate(job, prefs);
    if (!gate.keep) {
      summary.rejected[gate.reason] = (summary.rejected[gate.reason] || 0) + 1;
      return;
    }
    if (isAlreadyApplied(job, appliedIndex)) {
      summary.rejected.applied = (summary.rejected.applied || 0) + 1;
      return;
    }

    const dup = findDuplicate(job, index);
    if (dup) {
      summary.duplicates++;
      const merged = upsertSourcesList(dup.sources, job.source);
      if (merged !== dup.sources) {
        mergeSourcesStmt.run(merged, dup.id);
        dup.sources = merged;
      }
      return;
    }
    const sourcesJson = JSON.stringify([job.source]);
    const info = insertStmt.run({
      ...job,
      sources: sourcesJson,
      match_score: gate.matchScore,
      location_bucket: gate.bucket,
      location_score: gate.locationScore,
      keyword_score: gate.keywordScore,
      unsponsored_us: gate.unsponsoredUS ? 1 : 0,
    });
    summary.inserted++;
    addToIndex(index, { ...job, id: info.lastInsertRowid, sources: sourcesJson });
  };
}

async function runTier1(config, db, ingest, summary, prefs) {
  const shouldFetchDetail = makeDetailPredicate(prefs);
  // Workday is searched, not listed, so it needs the search terms. Reusing
  // roleKeywords rather than tier2Keywords keeps one list as the definition of
  // "a role I would take" across the whole run.
  const keywords = config.tier1SearchKeywords || prefs.roleKeywords || [];

  const boards = (config.tier1Watchlist || []).filter((entry) => {
    if (SLUG_CONNECTORS[entry.platform] || ENTRY_CONNECTORS[entry.platform]) return true;
    console.warn(`  skipping unknown platform "${entry.platform}" for ${entry.name}`);
    return false;
  });

  let done = 0;
  await mapPool(boards, BOARD_CONCURRENCY, async (entry) => {
    const slugConnector = SLUG_CONNECTORS[entry.platform];
    const entryConnector = ENTRY_CONNECTORS[entry.platform];
    const startedAt = Date.now();
    try {
      const raw = slugConnector
        ? await slugConnector.fetchPostings(entry.slug)
        : await entryConnector.fetchPostings(entry, {
            throttledFetch: rateLimiter.throttledFetch,
            rateLimitMs: entry.rateLimitMs || DEFAULT_TIER2_RATE_LIMIT_MS,
            keywords,
            shouldFetchDetail,
          });
      const secs = ((Date.now() - startedAt) / 1000).toFixed(1);
      // Returned rather than run here: the caller invokes it in completion
      // order, so the synchronous database writes never interleave.
      return () => {
        recordSourceSuccess(db, entry.name);
        summary.fetched += raw.length;
        for (const rawJob of raw) ingest(normalize(entry.platform, rawJob, entry.name));
        // Per-board progress. A run over 29 boards is minutes long, and a
        // silent log for all of it is indistinguishable from a hang.
        console.log(`  [${++done}/${boards.length}] ${entry.name}: ${raw.length} postings (${secs}s)`);
      };
    } catch (err) {
      return () => {
        const { status } = recordSourceFailure(db, entry.name);
        summary.failures.push({ source: entry.name, status, error: err.message });
        console.log(`  [${++done}/${boards.length}] ${entry.name}: FAILED — ${err.message}`);
      };
    }
  });
}

async function runTier2(config, db, ingest, summary) {
  const keywords = config.tier2Keywords || [];
  const sourceRateLimit = (name) =>
    (config.tier2Sources || []).find((s) => s.name === name)?.rateLimitMs || DEFAULT_TIER2_RATE_LIMIT_MS;

  // `tier2Sources` is the list of sources to actually run, not just a table of
  // rate limits. It used to be only the latter — every source below ran
  // unconditionally, so deleting one from the config changed its throttle and
  // nothing else, and the file quietly lied about what a run would do.
  const enabled = (name) => (config.tier2Sources || []).some((s) => s.name === name);

  // --- Remotive: one request per keyword (its API only supports single-term search) ---
  for (const keyword of enabled("remotive") ? keywords : []) {
    try {
      const raw = await remotive.fetchPostings(keyword, {
        throttledFetch: rateLimiter.throttledFetch,
        rateLimitMs: sourceRateLimit("remotive"),
      });
      recordSourceSuccess(db, "remotive");
      summary.fetched += raw.length;
      for (const rawJob of raw) ingest(normalize("remotive", rawJob));
    } catch (err) {
      const { status } = recordSourceFailure(db, "remotive");
      summary.failures.push({ source: "remotive", status, error: err.message });
    }
  }

  // --- RemoteOK: one request total, filtered locally against all keywords ---
  if (enabled("remoteok")) {
    try {
      const raw = await remoteok.fetchPostings(keywords, {
        throttledFetch: rateLimiter.throttledFetch,
        rateLimitMs: sourceRateLimit("remoteok"),
      });
      recordSourceSuccess(db, "remoteok");
      summary.fetched += raw.length;
      for (const rawJob of raw) ingest(normalize("remoteok", rawJob));
    } catch (err) {
      const { status } = recordSourceFailure(db, "remoteok");
      summary.failures.push({ source: "remoteok", status, error: err.message });
    }
  }

  // --- WeWorkRemotely: category RSS feeds ---
  // Off by default: WeWorkRemotely charges the applicant to apply, so its
  // postings cost you money to act on. The connector is kept because nothing
  // is wrong with it — re-add { "name": "weworkremotely" } to tier2Sources to
  // turn it back on.
  if (enabled("weworkremotely")) {
    try {
      const raw = await weworkremotely.fetchPostings(config.tier2WwrCategories, {
        throttledFetch: rateLimiter.throttledFetch,
        rateLimitMs: sourceRateLimit("weworkremotely"),
      });
      recordSourceSuccess(db, "weworkremotely");
      summary.fetched += raw.length;
      for (const rawJob of raw) ingest(normalize("weworkremotely", rawJob));
    } catch (err) {
      const { status } = recordSourceFailure(db, "weworkremotely");
      summary.failures.push({ source: "weworkremotely", status, error: err.message });
    }
  }

  // --- Career pages: schema.org JobPosting via Playwright (req. 3-4) ---
  for (const entry of config.tier2CareerPages || []) {
    try {
      const raw = await careerpage.fetchPostings(entry.url);
      recordSourceSuccess(db, entry.name);
      summary.fetched += raw.length;
      for (const rawJob of raw) ingest(normalize("careerpage", rawJob, entry.name));
    } catch (err) {
      const { status } = recordSourceFailure(db, entry.name);
      summary.failures.push({ source: entry.name, status, error: err.message });
    }
  }
}

function archiveStaleRows(db, prefs) {
  const days = prefs.archiveAfterDays;
  if (!Number.isFinite(days) || days <= 0) return 0; // no sweep configured
  const info = db
    .prepare(
      `UPDATE discovered_jobs SET status = 'archived'
       WHERE status = 'new' AND first_seen_at < datetime('now', ?)`
    )
    .run(`-${days} days`);
  return info.changes;
}

async function main() {
  if (!existsSync(CONFIG_PATH)) {
    console.error(`${CONFIG_PATH} not found. Run "node scripts/bootstrap-sources.js" first.`);
    process.exit(1);
  }
  const config = JSON.parse(readFileSync(CONFIG_PATH, "utf8"));

  const db = new Database(DB_PATH);
  db.pragma("journal_mode = WAL");
  // The dashboard is serving reads off this same file while this run writes
  // to it — the Refresh button starts this process from inside the server.
  db.pragma("busy_timeout = 5000");
  applyMigrations(db);

  // The dashboard's "Posted ≤ N days" control writes straight into
  // preferences.json (see /api/discover in server.js) before this process is
  // spawned, so the ingest window here is always whatever Refresh was last
  // run with - the same value the live view and rescore.js fall back to.
  const prefs = loadPreferences();
  const ageLabel = prefs.maxAgeDays === Infinity ? "any age" : `posted within ${prefs.maxAgeDays}d`;

  const summary = { fetched: 0, duplicates: 0, inserted: 0, rejected: {}, failures: [] };
  const ingest = makeIngestor(db, summary, prefs);

  console.log(
    `Filters: ${ageLabel} · ` +
      `${Object.entries(prefs.locationWeights).map(([k, v]) => `${k} ${Math.round(v * 100)}%`).join(" / ")} · ` +
      `off-list locations ${prefs.offListLocations === "drop" ? "dropped" : "kept"}`
  );

  const platforms = [...new Set((config.tier1Watchlist || []).map((e) => e.platform))].sort();
  console.log(
    `Running Tier 1 discovery over ${(config.tier1Watchlist || []).length} boards ` +
      `(${platforms.join(" / ") || "none configured"})...`
  );
  await runTier1(config, db, ingest, summary, prefs);

  // Named from the config rather than a fixed string, so turning a source off
  // is visible in the run log instead of the log still claiming it ran.
  const tier2Names = [
    ...(config.tier2Sources || []).map((s) => s.name),
    ...((config.tier2CareerPages || []).length ? ["career pages"] : []),
  ];
  console.log(`Running Tier 2 discovery (${tier2Names.join(" / ") || "none configured"})...`);
  await runTier2(config, db, ingest, summary);

  // Phase two: re-judge rows that were already here under the preferences in
  // force *now*. Finding new postings is only half of what "Refresh" should
  // mean — if you widened the freshness window, the postings it now admits are
  // mostly ones already sitting in the database as `archived`, and no amount
  // of fetching would bring them back. This is what used to be the separate
  // `node scripts/rescore.js` chore.
  console.log("Re-applying your filters to postings already saved...");
  const rescored = rescoreRows(db, prefs);

  const archived = archiveStaleRows(db, prefs);

  console.log("\n=== Run summary ===");
  console.log(`  Postings fetched:   ${summary.fetched}`);

  // A gate that quietly eats 98% of a run looks identical to a broken
  // connector unless it says so. Each reason is reported separately, so a
  // keyword list that is too narrow is distinguishable from a location list
  // that is too narrow.
  const REJECT_LABELS = {
    stale: `older than ${prefs.maxAgeDays === Infinity ? "the age limit" : `${prefs.maxAgeDays}d`}`,
    "off-role": "title matched no role keyword",
    seniority: "senior / staff / intern title",
    experience: `asks for more than ${EXPERIENCE_CAP_YEARS} years' experience`,
    "off-location": "location off your list",
    applied: "already in your applied log",
  };
  const rejectedTotal = Object.values(summary.rejected).reduce((a, b) => a + b, 0);
  console.log(`  Filtered out:       ${rejectedTotal}`);
  for (const [reason, label] of Object.entries(REJECT_LABELS)) {
    if (summary.rejected[reason]) console.log(`    - ${label}: ${summary.rejected[reason]}`);
  }

  console.log(`  Duplicates merged:  ${summary.duplicates}`);
  console.log(`  New postings saved: ${summary.inserted}`);

  // The rescore's own tally. "Brought back" is the one to watch after widening
  // a filter: it is postings that were already found and had been archived
  // under the old setting.
  console.log(`  Re-checked existing: ${rescored.scored}`);
  if (rescored.restored > 0) console.log(`    - brought back into the feed: ${rescored.restored}`);
  if (rescored.archived > 0) console.log(`    - archived (no longer match): ${rescored.archived}`);
  console.log(`  Archived (${prefs.archiveAfterDays}d+ in feed): ${archived}`);
  console.log(`  Active feed now:    ${activeCount(db)}`);
  if (summary.failures.length > 0) {
    console.log(`  Source failures:`);
    for (const f of summary.failures) {
      console.log(`    - ${f.source}: ${f.status} (${f.error})`);
    }
  }
  const permFail = db.prepare("SELECT name FROM sources WHERE status = 'permanent-fail'").all();
  if (permFail.length > 0) {
    console.log(`  ⚠ PERMANENT-FAIL sources needing investigation: ${permFail.map((s) => s.name).join(", ")}`);
  }

  db.close();
}

main();
