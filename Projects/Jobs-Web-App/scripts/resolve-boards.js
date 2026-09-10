#!/usr/bin/env node
// Resolves config/sources.json's company list into concrete boards and prints
// what was found, without running a full discovery pass. Use after editing the
// company list: `node scripts/resolve-boards.js [--force]`.
import Database from "better-sqlite3";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { applyMigrations } from "../db/migrate.js";
import { resolveBoards, cachedBoards } from "../lib/boardResolver.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const config = JSON.parse(readFileSync(path.join(__dirname, "..", "config", "sources.json"), "utf8"));
const db = new Database(process.env.JOBS_DB_PATH || path.join(__dirname, "..", "jobs.db"));
applyMigrations(db);

const { entries, report } = await resolveBoards(config, db, {
  force: process.argv.includes("--force"),
  log: (l) => console.log(l),
});

console.log(`\n${entries.length} boards resolved`);
console.log(`  found ${report.found} · overrides ${report.overrides} · cached ${report.cached} · probed ${report.probed} · errors ${report.errors}`);

const byCompany = new Map();
for (const e of entries) {
  if (!byCompany.has(e.name)) byCompany.set(e.name, []);
  byCompany.get(e.name).push(`${e.platform}:${e.slug || e.tenant}`);
}
console.log("\nPer company:");
for (const [name, list] of byCompany) console.log(`  ${name.padEnd(16)} ${list.join(", ")}`);

const missing = Object.keys(config.companies).filter((c) => !byCompany.has(c));
if (missing.length) console.log(`\nNo board found: ${missing.join(", ")}`);
