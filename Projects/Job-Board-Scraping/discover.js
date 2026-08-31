#!/usr/bin/env node
// CLI entry point: `npm run discover` (PRD req. 13-16).
// Orchestrates Tier 1 + Tier 2 connectors, normalizes, dedups, inserts new
// discovered_jobs rows, prints a run summary, and sweeps stale rows into
// `archived`. No OS-level scheduler triggers this — the user runs it by hand.

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

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// Shared with the dashboard on purpose (PRD req. 17: one SQLite file, one
// future dashboard tab) even though this is now its own project — override
// with JOBS_DB_PATH if Job-Tracking-Dash isn't a sibling directory.
const DB_PATH = process.env.JOBS_DB_PATH || path.join(__dirname, "..", "Job-Tracking-Dash", "jobs.db");
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

function makeIngestor(db, summary) {
  const rows = db.prepare("SELECT id, job_id, sources, title, company, location, apply_url FROM discovered_jobs").all();
  const index = buildDedupIndex(rows);

  const insertStmt = db.prepare(`
    INSERT INTO discovered_jobs
      (job_id, sources, title, company, location, salary, description, apply_url, posted_date, remote_status, status)
    VALUES
      (@job_id, @sources, @title, @company, @location, @salary, @description, @apply_url, @posted_date, @remote_status, 'new')
  `);
  const mergeSourcesStmt = db.prepare("UPDATE discovered_jobs SET sources = ? WHERE id = ?");

  // Ingests one already-normalized job: merges into an existing dedup match
  // or inserts a new row, keeping the in-memory index current so later
  // sources in the same run can also dedup against it (req. 11-12).
  return function ingest(job) {
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
    const info = insertStmt.run({ ...job, sources: sourcesJson });
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
  applyMigrations(db);

  const summary = { fetched: 0, duplicates: 0, inserted: 0, failures: [] };
  const ingest = makeIngestor(db, summary);

  console.log("Running Tier 1 discovery (Greenhouse / Lever / Ashby)...");
  await runTier1(config, db, ingest, summary);

  console.log("Running Tier 2 discovery (Remotive / RemoteOK / WeWorkRemotely / career pages)...");
  await runTier2(config, db, ingest, summary);

  const archived = archiveStaleRows(db);

  console.log("\n=== Run summary ===");
  console.log(`  Postings fetched:   ${summary.fetched}`);
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
