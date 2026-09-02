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
import { normalize } from "./lib/normalize.js";
import { buildDedupIndex, findDuplicate, addToIndex } from "./lib/dedup.js";
import { recordSourceSuccess, recordSourceFailure } from "./lib/sourceHealth.js";
import { createRateLimiter } from "./lib/rateLimiter.js";
import { loadPreferences } from "./lib/preferences.js";
import { ingestGate, buildAppliedIndex, isAlreadyApplied, EXPERIENCE_CAP_YEARS } from "./lib/jobFilter.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// One SQLite file for the whole app: server.js and this CLI are two entry
// points over the same jobs.db. Override with JOBS_DB_PATH to point a run at
// a scratch copy.
const DB_PATH = process.env.JOBS_DB_PATH || path.join(__dirname, "jobs.db");
const CONFIG_PATH = path.join(__dirname, "config", "sources.json");
const ARCHIVE_AFTER_DAYS = 60;
const DEFAULT_TIER2_RATE_LIMIT_MS = 2000;

const TIER1_CONNECTORS = { greenhouse, lever, ashby };
const rateLimiter = createRateLimiter();

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

async function runTier1(config, db, ingest, summary) {
  for (const entry of config.tier1Watchlist || []) {
    const connector = TIER1_CONNECTORS[entry.platform];
    if (!connector) {
      console.warn(`  skipping unknown platform "${entry.platform}" for ${entry.name}`);
      continue;
    }
    try {
      const raw = await connector.fetchPostings(entry.slug);
      recordSourceSuccess(db, entry.name);
      summary.fetched += raw.length;
      for (const rawJob of raw) {
        ingest(normalize(entry.platform, rawJob, entry.name));
      }
    } catch (err) {
      const { status } = recordSourceFailure(db, entry.name);
      summary.failures.push({ source: entry.name, status, error: err.message });
    }
  }
}

async function runTier2(config, db, ingest, summary) {
  const keywords = config.tier2Keywords || [];
  const sourceRateLimit = (name) =>
    (config.tier2Sources || []).find((s) => s.name === name)?.rateLimitMs || DEFAULT_TIER2_RATE_LIMIT_MS;

  // --- Remotive: one request per keyword (its API only supports single-term search) ---
  for (const keyword of keywords) {
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

  // --- WeWorkRemotely: category RSS feeds ---
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

function archiveStaleRows(db) {
  const info = db
    .prepare(
      `UPDATE discovered_jobs SET status = 'archived'
       WHERE status = 'new' AND first_seen_at < datetime('now', ?)`
    )
    .run(`-${ARCHIVE_AFTER_DAYS} days`);
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

  // Copied, not used in place: loadPreferences() hands back a shared cached
  // object and the age window below is a per-run override, not a config edit.
  const prefs = { ...loadPreferences() };

  // The dashboard's "Posted ≤ N days" control sets this when the Refresh button
  // starts the run. Without it the ingest window was pinned to
  // preferences.json's maxAgeDays no matter what the UI showed, so widening the
  // filter only ever widened the *display* — the postings it was meant to admit
  // had already been rejected as stale before they reached the database.
  const rawMaxAge = process.env.DISCOVER_MAX_AGE_DAYS;
  if (rawMaxAge !== undefined && rawMaxAge !== "") {
    const n = Number(rawMaxAge);
    // 0 is the UI's "Any age"; isFresh() compares against it numerically, so
    // Infinity is the honest spelling of no upper bound.
    if (Number.isFinite(n) && n >= 0) prefs.maxAgeDays = n === 0 ? Infinity : n;
  }
  const ageLabel = prefs.maxAgeDays === Infinity ? "any age" : `posted within ${prefs.maxAgeDays}d`;

  const summary = { fetched: 0, duplicates: 0, inserted: 0, rejected: {}, failures: [] };
  const ingest = makeIngestor(db, summary, prefs);

  console.log(
    `Filters: ${ageLabel} · ` +
      `${Object.entries(prefs.locationWeights).map(([k, v]) => `${k} ${Math.round(v * 100)}%`).join(" / ")} · ` +
      `off-list locations ${prefs.offListLocations === "drop" ? "dropped" : "kept"}`
  );

  console.log("Running Tier 1 discovery (Greenhouse / Lever / Ashby)...");
  await runTier1(config, db, ingest, summary);

  console.log("Running Tier 2 discovery (Remotive / RemoteOK / WeWorkRemotely / career pages)...");
  await runTier2(config, db, ingest, summary);

  const archived = archiveStaleRows(db);

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
  console.log(`  Archived (60d+ stale): ${archived}`);
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
