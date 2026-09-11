// Loads config/preferences.json — the "what you want" half of the config, kept
// separate from sources.json, which is "where to look".
//
// The file is written in a grouped shape (roles / level / locations / scoring /
// feed) because the flat version had grown to twenty-odd sibling keys with its
// documentation interleaved between them as `_`-prefixed strings, and no reader
// could tell which list fed which decision. That prose now lives in
// config/README.md.
//
// Everything downstream still reads flat names (prefs.roleKeywords,
// prefs.locationWeights, ...). Normalizing here rather than at each call site
// is why scoring.js, jobFilter.js, discover.js and server.js did not have to
// change, and why the older flat file still loads — which is what this module's
// tests write, and what config/backup/ holds.

import { readFileSync, existsSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PREFS_PATH = process.env.JOB_PREFS_PATH || path.join(__dirname, "..", "config", "preferences.json");

// Mirrors config/preferences.json in the flat, post-normalization shape. Used
// verbatim when the file is missing, and key-by-key for anything it omits.
export const DEFAULT_PREFERENCES = {
  // null means no age limit, restored to Infinity below. Failing open is
  // deliberate: with no config, the wrong thing to do is silently hide
  // postings behind a number the user never chose.
  maxAgeDays: null,
  archiveAfterDays: 60,
  experienceCapYears: 2,
  roleKeywords: ["software engineer", "software developer", "data engineer", "machine learning engineer", "developer"],
  primaryRoles: ["software engineer", "software developer", "data engineer", "machine learning engineer"],
  similarRoles: ["developer"],
  levelKeywords: ["new grad", "new graduate", "entry level", "junior"],
  gradKeywords: ["new grad", "new graduate", "recent graduate", "graduate program", "early talent"],
  timingKeywords: ["jan 2027", "january 2027", "2027"],
  excludeTitleKeywords: ["senior", "staff", "principal", "lead", "director", "manager", "intern"],
  synonyms: { ml: "machine learning", rl: "reinforcement learning" },
  locationWeights: { calgary: 0.5, edmonton: 0.2, remote: 0.15, vancouver: 0.1, seattle: 0.05 },
  offListLocations: "drop",
  requireSponsorshipForUS: true,
  usNoSponsorshipPenalty: 0.35,
  scoreWeights: { location: 0.65, keyword: 0.35 },
  similarTitleFactor: 0.7,
  // Off unless configured: with no preferences file, scores stay pure
  // preference and no resume is read.
  resumeWeight: 0,
};

// A file is in the grouped shape if it uses any of the group keys. Anything
// else is read as the original flat file.
const GROUP_KEYS = ["roles", "level", "locations", "scoring", "feed", "synonyms", "timing"];

function isGrouped(raw) {
  return GROUP_KEYS.some((k) => k in raw);
}

// Grouped file -> the flat names the rest of the codebase reads.
//
// roleKeywords deliberately concatenates primary and similar: both clear the
// ingest gate. The split survives separately as primaryRoles/similarRoles so
// scoring.js can rank a "similar" hit below an exact one, instead of treating
// "Research Engineer" as interchangeable with "Software Engineer".
function flatten(raw) {
  const out = {};
  const { roles, level, locations, scoring, feed, timing, synonyms } = raw;

  if (roles) {
    const primary = roles.primary || [];
    const similar = roles.similar || [];
    out.primaryRoles = primary;
    out.similarRoles = similar;
    out.roleKeywords = [...primary, ...similar];
    if (roles.exclude) out.excludeTitleKeywords = roles.exclude;
  }
  if (level) {
    if (level.signals) out.levelKeywords = level.signals;
    if (level.programs) out.gradKeywords = level.programs;
  }
  if (timing) out.timingKeywords = timing;
  if (synonyms) out.synonyms = synonyms;

  if (locations) {
    if (locations.weights) out.locationWeights = locations.weights;
    if (locations.offList !== undefined) out.offListLocations = locations.offList;
    if (locations.requireSponsorshipForUS !== undefined) {
      out.requireSponsorshipForUS = locations.requireSponsorshipForUS;
    }
    if (locations.usNoSponsorshipPenalty !== undefined) {
      out.usNoSponsorshipPenalty = locations.usNoSponsorshipPenalty;
    }
  }
  if (scoring) {
    const pair = {};
    if (scoring.location !== undefined) pair.location = scoring.location;
    if (scoring.keyword !== undefined) pair.keyword = scoring.keyword;
    if (Object.keys(pair).length) out.scoreWeights = pair;
    if (scoring.similarTitleFactor !== undefined) out.similarTitleFactor = scoring.similarTitleFactor;
    if (scoring.resumeWeight !== undefined) out.resumeWeight = scoring.resumeWeight;
  }
  if (feed) {
    if (feed.maxAgeDays !== undefined) out.maxAgeDays = feed.maxAgeDays;
    if (feed.archiveAfterDays !== undefined) out.archiveAfterDays = feed.archiveAfterDays;
    if (feed.experienceCapYears !== undefined) out.experienceCapYears = feed.experienceCapYears;
  }
  return out;
}

let cached = null;

export function loadPreferences({ reload = false } = {}) {
  if (cached && !reload) return cached;

  let fromFile = {};
  if (existsSync(PREFS_PATH)) {
    try {
      fromFile = JSON.parse(readFileSync(PREFS_PATH, "utf8"));
    } catch (err) {
      // A malformed file is worth shouting about rather than silently
      // reverting to defaults — the whole feed's shape depends on it.
      throw new Error(`${PREFS_PATH} is not valid JSON: ${err.message}`);
    }
  }

  // `_`-prefixed keys were the old inline documentation. Still stripped, so a
  // pre-refactor file (config/backup/) loads unchanged.
  const stripped = Object.fromEntries(Object.entries(fromFile).filter(([k]) => !k.startsWith("_")));
  const clean = isGrouped(stripped) ? flatten(stripped) : stripped;

  cached = {
    ...DEFAULT_PREFERENCES,
    ...clean,
    // locationWeights is taken verbatim when supplied, NOT merged over the
    // defaults. Merging made a location impossible to remove: delete "seattle"
    // and the default put it straight back, so the bucket kept resolving and
    // Seattle postings kept being ingested and scored. The set of locations is
    // a list the user owns; a missing entry means "not this one", not "fall
    // back to mine".
    locationWeights: clean.locationWeights || DEFAULT_PREFERENCES.locationWeights,
    // scoreWeights is a fixed pair rather than a set — a missing half means
    // "leave that half alone", so merging is the right behaviour here.
    scoreWeights: { ...DEFAULT_PREFERENCES.scoreWeights, ...(clean.scoreWeights || {}) },
    synonyms: { ...DEFAULT_PREFERENCES.synonyms, ...(clean.synonyms || {}) },
  };
  // "No age limit" isn't valid JSON as Infinity, so it round-trips through
  // `null` on disk (see savePreferences) and is restored here.
  if (cached.maxAgeDays === null) cached.maxAgeDays = Infinity;
  return cached;
}

// Where each flat key lives in the grouped file, so a caller that knows only
// the flat name (server.js writes `maxAgeDays`) still lands in the right group.
// A string is the owning group; a pair is [group, field] where the field is
// named differently inside the group than out.
const GROUP_OF = {
  maxAgeDays: "feed",
  archiveAfterDays: "feed",
  experienceCapYears: "feed",
  offListLocations: ["locations", "offList"],
  requireSponsorshipForUS: ["locations", "requireSponsorshipForUS"],
  usNoSponsorshipPenalty: ["locations", "usNoSponsorshipPenalty"],
  locationWeights: ["locations", "weights"],
};

// Merges `updates` into config/preferences.json on disk and refreshes the
// in-memory cache, so a value set from the dashboard (e.g. the Refresh
// button's freshness window) is the same one discover.js's ingest gate,
// /api/discovered and scripts/rescore.js all see afterward — one stored value
// instead of a run-only override only discover.js ever heard about.
//
// Updates are given in flat names. On a grouped file they are routed into the
// group that owns them; every other key, including any the user has added by
// hand, is preserved untouched.
export function savePreferences(updates) {
  let onDisk = {};
  if (existsSync(PREFS_PATH)) {
    onDisk = JSON.parse(readFileSync(PREFS_PATH, "utf8"));
  }

  let next;
  if (isGrouped(onDisk)) {
    next = { ...onDisk };
    for (const [key, value] of Object.entries(updates)) {
      const target = GROUP_OF[key];
      if (!target) {
        next[key] = value;
      } else if (Array.isArray(target)) {
        const [group, field] = target;
        next[group] = { ...(next[group] || {}), [field]: value };
      } else {
        next[target] = { ...(next[target] || {}), [key]: value };
      }
    }
  } else {
    next = { ...onDisk, ...updates };
  }

  writeFileSync(PREFS_PATH, JSON.stringify(next, null, 2) + "\n");
  cached = null;
  return loadPreferences();
}
