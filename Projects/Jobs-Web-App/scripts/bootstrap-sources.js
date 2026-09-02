#!/usr/bin/env node
// PRD req. 8 / Tasks.md 3.1: one-time bootstrap that derives config/sources.json's
// seed values from data the user already has (the existing `jobs` table) instead
// of a hand-typed or invented list.
//
// Usage: node scripts/bootstrap-sources.js

import Database from "better-sqlite3";
import { writeFileSync, readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as greenhouse from "../connectors/greenhouse.js";
import * as lever from "../connectors/lever.js";
import * as ashby from "../connectors/ashby.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// The one shared jobs.db — see discover.js.
const DB_PATH = process.env.JOBS_DB_PATH || path.join(__dirname, "..", "jobs.db");
const OUT_PATH = path.join(__dirname, "..", "config", "sources.json");
const PROBE_DELAY_MS = 150; // light politeness delay for the one-time probe pass

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

// This script only knows how to *discover* Greenhouse, Lever and Ashby boards,
// because those are the three it can find from a company name alone. Workday
// needs a tenant, a cell and a site name; Workable, Recruitee and BambooHR
// need a slug that is not derivable from the company's name either. Those are
// added by hand (or by scripts/probe-workday.js).
//
// So a re-bootstrap merges rather than overwrites. Rewriting tier1Watchlist
// wholesale, which is what this used to do, silently deleted every board the
// probe cannot rediscover — turning "refresh my keywords" into "throw away the
// Calgary employer list". Anything already in the file stays; the probe only
// adds.
function boardKey(entry) {
  return entry.platform === "workday"
    ? `workday:${entry.tenant}/${entry.site}`
    : `${entry.platform}:${entry.slug}`;
}

function readExistingConfig() {
  if (!existsSync(OUT_PATH)) return null;
  try {
    return JSON.parse(readFileSync(OUT_PATH, "utf8"));
  } catch {
    console.warn(`  ${OUT_PATH} is not valid JSON — starting fresh rather than merging into it.`);
    return null;
  }
}

function slugCandidates(company) {
  const cleaned = company
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .trim();
  const noSpace = cleaned.replace(/\s+/g, "");
  const hyphenated = cleaned.replace(/\s+/g, "-");
  return [...new Set([noSpace, hyphenated])].filter(Boolean);
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function findBoard(company) {
  for (const slug of slugCandidates(company)) {
    for (const [platform, connector] of [
      ["greenhouse", greenhouse],
      ["lever", lever],
      ["ashby", ashby],
    ]) {
      try {
        if (await connector.probe(slug)) {
          return { platform, slug };
        }
      } catch {
        // treat any probe error as "no board on this platform" and move on
      }
      await sleep(PROBE_DELAY_MS);
    }
  }
  return null;
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

async function main() {
  if (!existsSync(DB_PATH)) {
    console.error(`jobs.db not found at ${DB_PATH} — start the dashboard once (npm start) to create it, or set JOBS_DB_PATH.`);
    process.exit(1);
  }

  const db = new Database(DB_PATH, { readonly: true });
  const companies = db.prepare("SELECT DISTINCT company FROM jobs").all().map((r) => r.company);
  const titles = db.prepare("SELECT DISTINCT title FROM jobs").all().map((r) => r.title);
  db.close();

  console.log(`Found ${companies.length} distinct companies and ${titles.length} distinct titles in jobs.db.`);

  let keywords;
  let keywordSource;
  if (titles.length < MIN_DISTINCT_TITLES) {
    keywords = PLACEHOLDER_KEYWORDS;
    keywordSource = "placeholder (fewer than 5 distinct titles logged — edit this list)";
  } else {
    keywords = deriveKeywords(titles);
    keywordSource = "derived from jobs.db title history";
  }

  console.log(`Probing ${companies.length} companies against Greenhouse/Lever/Ashby public boards (this can take a few minutes)...`);
  const tier1 = [];
  for (const company of companies) {
    const board = await findBoard(company);
    if (board) {
      console.log(`  found: ${company} -> ${board.platform}/${board.slug}`);
      tier1.push({ name: company, platform: board.platform, slug: board.slug, rateLimitMs: 2000 });
    }
  }

  const existing = readExistingConfig();
  const kept = existing?.tier1Watchlist || [];
  const seen = new Set(kept.map(boardKey));
  const added = tier1.filter((entry) => !seen.has(boardKey(entry)));
  const watchlist = [...kept, ...added];

  const config = {
    _comment: "Bootstrapped from jobs.db (PRD req. 8). Edit freely — this only sets the starting point.",
    _watchlistNote: existing?._watchlistNote,
    tier1SearchKeywords: existing?.tier1SearchKeywords,
    tier1Watchlist: watchlist,
    tier2Keywords: keywords,
    tier2KeywordSource: keywordSource,
    tier2Sources: existing?.tier2Sources || [
      { name: "remotive", rateLimitMs: 2000 },
      { name: "remoteok", rateLimitMs: 2000 },
      { name: "weworkremotely", rateLimitMs: 2000 },
    ],
    tier2WwrCategories: existing?.tier2WwrCategories || [
      "remote-programming-jobs",
      "remote-devops-sysadmin-jobs",
    ],
    tier2CareerPages: existing?.tier2CareerPages || [],
  };
  for (const [k, v] of Object.entries(config)) if (v === undefined) delete config[k];

  writeFileSync(OUT_PATH, JSON.stringify(config, null, 2) + "\n");
  console.log(`\nWrote ${OUT_PATH}`);
  console.log(
    `  Tier 1 watchlist: ${watchlist.length} boards ` +
      `(${kept.length} kept, ${added.length} newly found out of ${companies.length} companies checked)`
  );
  console.log(`  Tier 2 keywords (${keywordSource}): ${keywords.join(", ")}`);
}

main();
