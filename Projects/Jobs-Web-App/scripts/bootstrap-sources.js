#!/usr/bin/env node
// PRD req. 8 / Tasks.md 3.1: seeds config/sources.json from data the user
// already has (the existing `jobs` table) instead of a hand-typed list.
//
// Usage: node scripts/bootstrap-sources.js
//
// This used to probe Greenhouse/Lever/Ashby to work out which board each
// company posted to, and wrote the answer into a tier1Watchlist of
// company-plus-platform pairs. It no longer does either. sources.json now names
// companies only, and lib/boardResolver.js finds the boards at discovery time
// across every enabled platform — so the pairing cannot go stale here, and a
// company that dual-posts is picked up on both boards rather than on whichever
// one this script happened to probe first.
//
// What is left is the part that genuinely needs the database: which companies
// the user has actually applied to, and what they call the roles they want.
//
// Merging, not overwriting. Rewriting the file wholesale (which this once did)
// silently deleted every board the probe could not rediscover, turning "refresh
// my keywords" into "throw away the Calgary employer list". Anything already in
// the file stays; this only adds.

import Database from "better-sqlite3";
import { writeFileSync, readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// The one shared jobs.db — see discover.js.
const DB_PATH = process.env.JOBS_DB_PATH || path.join(__dirname, "..", "jobs.db");
const OUT_PATH = path.join(__dirname, "..", "config", "sources.json");

const MIN_DISTINCT_TITLES = 5;
const PLACEHOLDER_KEYWORDS = [
  "software engineer",
  "data scientist",
  "product manager",
  "data engineer",
  "machine learning engineer",
  "devops engineer",
  "backend engineer",
  "frontend engineer",
  "qa engineer",
  "engineering manager",
];

const SENIORITY_WORDS = [
  "staff", "senior", "sr", "junior", "jr", "lead", "principal", "intern",
  "internship", "new grad", "graduate", "level 1", "level 2", "level 3",
  "entry level", "co-op", "coop", "associate", "director", "vp",
];

// The shape a fresh file starts from, when there is no sources.json at all.
const DEFAULT_PLATFORMS = {
  greenhouse: { enabled: true, autoResolve: true, rateLimitMs: 2000 },
  ashby: { enabled: true, autoResolve: true, rateLimitMs: 2000 },
  lever: { enabled: true, autoResolve: true, rateLimitMs: 2000 },
  workable: { enabled: true, autoResolve: true, rateLimitMs: 600 },
  recruitee: { enabled: true, autoResolve: true, rateLimitMs: 600 },
  bamboohr: { enabled: true, autoResolve: true, rateLimitMs: 600 },
  // Addressed by tenant + cell + site, none of which is derivable from a
  // company name, so it is never probed — see scripts/probe-workday.js.
  workday: { enabled: true, autoResolve: false, rateLimitMs: 600 },
};

function readExistingConfig() {
  if (!existsSync(OUT_PATH)) return null;
  try {
    return JSON.parse(readFileSync(OUT_PATH, "utf8"));
  } catch {
    console.warn(`  ${OUT_PATH} is not valid JSON — starting fresh rather than merging into it.`);
    return null;
  }
}

function normalizeTitleToKeyword(title) {
  let t = title.toLowerCase();
  t = t.replace(/\([^)]*\)/g, " "); // drop parenthetical clauses
  for (const word of SENIORITY_WORDS) {
    t = t.replace(new RegExp(`\\b${word}\\b`, "g"), " ");
  }
  t = t.replace(/[^a-z0-9\s]/g, " ").replace(/\s+/g, " ").trim();
  return t;
}

function deriveKeywords(titles) {
  const counts = new Map();
  for (const title of titles) {
    const key = normalizeTitleToKeyword(title);
    if (!key) continue;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([key]) => key)
    .slice(0, 15);
}

// Case-insensitive, so "1password" from the job log does not become a second
// entry beside a hand-added "1Password".
function alreadyListed(companies, name) {
  const wanted = name.trim().toLowerCase();
  return Object.keys(companies).some((c) => c.trim().toLowerCase() === wanted);
}

async function main() {
  if (!existsSync(DB_PATH)) {
    console.error(`jobs.db not found at ${DB_PATH} — start the dashboard once (npm start) to create it, or set JOBS_DB_PATH.`);
    process.exit(1);
  }

  const db = new Database(DB_PATH, { readonly: true });
  const loggedCompanies = db.prepare("SELECT DISTINCT company FROM jobs").all().map((r) => r.company);
  const titles = db.prepare("SELECT DISTINCT title FROM jobs").all().map((r) => r.title);
  db.close();

  console.log(`Found ${loggedCompanies.length} distinct companies and ${titles.length} distinct titles in jobs.db.`);

  let keywords;
  let keywordSource;
  if (titles.length < MIN_DISTINCT_TITLES) {
    keywords = PLACEHOLDER_KEYWORDS;
    keywordSource = "placeholder (fewer than 5 distinct titles logged — edit this list)";
  } else {
    keywords = deriveKeywords(titles);
    keywordSource = "derived from jobs.db title history";
  }

  const existing = readExistingConfig();
  const companies = { ...(existing?.companies || {}) };

  let added = 0;
  for (const name of loggedCompanies) {
    if (!name || alreadyListed(companies, name)) continue;
    // An empty object means "look for this company on every enabled platform".
    companies[name] = {};
    added++;
    console.log(`  added company: ${name}`);
  }

  const config = {
    platforms: existing?.platforms || DEFAULT_PLATFORMS,
    companies,
    aggregators: existing?.aggregators || {
      remotive: { enabled: true, rateLimitMs: 2000 },
      remoteok: { enabled: true, rateLimitMs: 2000 },
    },
    careerPages: existing?.careerPages || [],
    searchKeywords: {
      workday: existing?.searchKeywords?.workday || [
        "software engineer", "software developer", "data engineer",
        "data scientist", "machine learning", "python", "backend", "new grad",
      ],
      aggregators: keywords,
    },
    resolution: existing?.resolution || { cacheDays: 30, slugCandidateStyle: ["nospace", "hyphenated"] },
  };

  writeFileSync(OUT_PATH, JSON.stringify(config, null, 2) + "\n");
  console.log(`\nWrote ${OUT_PATH}`);
  console.log(`  Companies: ${Object.keys(companies).length} (${added} newly added from jobs.db)`);
  console.log(`  Aggregator keywords: ${keywordSource}`);
  console.log(`\nRun "node discover.js --resolve" to find boards for the new companies.`);
}

main();
