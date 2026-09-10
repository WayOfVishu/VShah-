// Turns the company list in config/sources.json into the concrete boards
// discover.js should fetch.
//
// The file used to name boards: "StackAdapt is on Greenhouse". That made every
// entry a guess about where a company posts, and a wrong guess was silent — a
// role posted only to Ashby by a company hand-filed under Greenhouse was never
// seen, and nothing in the run said so. sources.json now names *companies*, and
// this module looks for each one on every enabled platform, so a company that
// moves boards or dual-posts is picked up either way. Duplicate hits are not a
// problem: lib/dedup.js already collapses the same role arriving from two
// platforms and merges the `sources` list on the surviving row.
//
// The cost of that is a cross-product of probes — companies x platforms x slug
// spellings — which is far too slow to repeat every run. Every answer is cached
// in board_cache (db/migrations/004), including the negatives, since most cells
// in the cross-product are misses and re-probing them is the bulk of the work.
//
// Two things cannot be probed from a company name, and both fall back to an
// explicit `boards` override in sources.json:
//   * Workday, which is addressed by tenant + cell + site ("wd3",
//     "ENBRIDGE_Careers") rather than a slug. Its platform entry therefore sets
//     autoResolve: false. scripts/probe-workday.js finds the three parts.
//   * any company whose slug is not derivable from its name.

import * as greenhouse from "../connectors/greenhouse.js";
import * as lever from "../connectors/lever.js";
import * as ashby from "../connectors/ashby.js";
import * as workable from "../connectors/workable.js";
import * as recruitee from "../connectors/recruitee.js";
import * as bamboohr from "../connectors/bamboohr.js";

// Only the platforms addressable by a single slug can be auto-resolved.
const PROBERS = { greenhouse, lever, ashby, workable, recruitee, bamboohr };

const DEFAULT_CACHE_DAYS = 30;
const PROBE_DELAY_MS = 120;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// "Neo Financial" -> ["neofinancial", "neo-financial"]. The two spellings cover
// essentially every slug in the current watchlist; "1Password" -> "1password"
// and "Top Hat" -> "top-hat" both fall out of this.
export function slugCandidates(company) {
  const cleaned = String(company)
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .trim();
  const candidates = [cleaned.replace(/\s+/g, ""), cleaned.replace(/\s+/g, "-")];
  return [...new Set(candidates)].filter(Boolean);
}

function readCache(db, company, platform) {
  return db
    .prepare("SELECT identifier, found, origin, checked_at FROM board_cache WHERE company = ? AND platform = ?")
    .get(company, platform);
}

function writeCache(db, company, platform, identifier, origin = "probe") {
  db.prepare(
    `INSERT INTO board_cache (company, platform, identifier, found, origin, checked_at)
     VALUES (?, ?, ?, ?, ?, datetime('now'))
     ON CONFLICT(company, platform) DO UPDATE SET
       identifier = excluded.identifier,
       found      = excluded.found,
       origin     = excluded.origin,
       checked_at = excluded.checked_at`
  ).run(company, platform, identifier === null ? null : JSON.stringify(identifier), identifier ? 1 : 0, origin);
}

// An override never goes stale — it was stated by hand, not guessed.
function isFresh(row, cacheDays) {
  if (!row) return false;
  if (row.origin === "override") return true;
  const age = (Date.now() - new Date(`${row.checked_at.replace(" ", "T")}Z`).getTime()) / 86_400_000;
  return Number.isFinite(age) && age < cacheDays;
}

// Probes one company against one platform, trying each slug spelling. Returns
// the winning slug, or null for a clean "not on this platform".
//
// A thrown probe is NOT a miss: a timeout or a 503 says nothing about whether
// the board exists, and caching it as absent would hide the company until the
// entry expired. Those return undefined and are left uncached, so the next run
// asks again.
async function probePlatform(platform, company, probers = PROBERS) {
  const prober = probers[platform];
  if (!prober?.probe) return null;

  let errored = false;
  for (const slug of slugCandidates(company)) {
    try {
      if (await prober.probe(slug)) return slug;
    } catch {
      errored = true;
    }
    await sleep(PROBE_DELAY_MS);
  }
  return errored ? undefined : null;
}

// Shapes a cached/override identifier back into the entry object the connectors
// expect: slug platforms take a bare string, Workday takes its three parts.
function toEntry(company, platform, identifier, rateLimitMs) {
  const base = { name: company, platform, rateLimitMs };
  return typeof identifier === "string" ? { ...base, slug: identifier } : { ...base, ...identifier };
}

// The boards to fetch this run, plus a report of how each was arrived at.
//
// `force` re-probes everything, ignoring cache freshness — what
// `npm run discover -- --resolve` is for after editing the company list.
//
// `probers` is injectable so the tests stay hermetic; the connectors' own
// tests do the same with `throttledFetch`.
export async function resolveBoards(config, db, { force = false, log = () => {}, probers = PROBERS } = {}) {
  const platforms = config.platforms || {};
  const companies = config.companies || {};
  const cacheDays = config.resolution?.cacheDays ?? DEFAULT_CACHE_DAYS;

  const entries = [];
  const report = { probed: 0, cached: 0, overrides: 0, found: 0, errors: 0 };

  for (const [company, settings] of Object.entries(companies)) {
    const overrides = settings?.boards || {};

    // An explicit override wins outright and is never probed.
    for (const [platform, identifier] of Object.entries(overrides)) {
      if (platforms[platform]?.enabled === false) continue;
      writeCache(db, company, platform, identifier, "override");
      entries.push(toEntry(company, platform, identifier, platforms[platform]?.rateLimitMs));
      report.overrides++;
      report.found++;
    }

    // `platforms` on a company narrows the search to a subset, for the case
    // where a slug is known to collide with an unrelated company's board.
    const searchable = settings?.platforms || Object.keys(platforms);

    for (const platform of searchable) {
      const conf = platforms[platform];
      if (!conf?.enabled || conf.autoResolve === false) continue;
      if (platform in overrides) continue;

      const cached = readCache(db, company, platform);
      if (!force && isFresh(cached, cacheDays)) {
        report.cached++;
        if (cached.found) {
          entries.push(toEntry(company, platform, JSON.parse(cached.identifier), conf.rateLimitMs));
          report.found++;
        }
        continue;
      }

      const slug = await probePlatform(platform, company, probers);
      report.probed++;
      if (slug === undefined) {
        report.errors++;
        continue; // transient failure — leave the cache alone and retry next run
      }
      writeCache(db, company, platform, slug);
      if (slug) {
        entries.push(toEntry(company, platform, slug, conf.rateLimitMs));
        report.found++;
        log(`    resolved ${company} -> ${platform}:${slug}`);
      }
    }
  }

  return { entries, report };
}

// What the resolver currently believes, for `npm run discover -- --list-boards`
// and for eyeballing a collision (two companies resolving to the same slug on
// the same platform is the failure mode auto-resolution can produce).
export function cachedBoards(db) {
  return db
    .prepare("SELECT company, platform, identifier, found, origin, checked_at FROM board_cache ORDER BY company, platform")
    .all()
    .map((r) => ({ ...r, identifier: r.identifier ? JSON.parse(r.identifier) : null }));
}
