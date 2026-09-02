// Loads config/preferences.json — the "what you want" half of the config, kept
// separate from sources.json because scripts/bootstrap-sources.js rewrites
// that file wholesale and would otherwise wipe these settings.

import { readFileSync, existsSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PREFS_PATH = process.env.JOB_PREFS_PATH || path.join(__dirname, "..", "config", "preferences.json");

// Mirrors config/preferences.json. Used verbatim when the file is missing, and
// key-by-key for anything the file leaves out, so a partial config is valid.
export const DEFAULT_PREFERENCES = {
  // Last resort only — used if config/preferences.json is missing entirely.
  // The live value is whatever the dashboard's "Posted within" control is set
  // to, which is saved here the moment it changes. Nothing else may invent a
  // window: this used to be duplicated as a hard-coded `selected` option in
  // index.html, and the two disagreed.
  //
  // null means no age limit. Failing open is deliberate — with no config, the
  // wrong thing to do is silently hide postings behind a number the user never
  // chose, which is the failure this default caused before.
  maxAgeDays: null,
  // How long a posting nobody acted on stays in the feed before the run sweeps
  // it to `archived`. Separate from maxAgeDays: that is about how old a
  // posting was when found, this is about how long we keep showing it.
  archiveAfterDays: 60,
  roleKeywords: ["software engineer", "software developer", "data engineer", "machine learning engineer", "developer"],
  levelKeywords: ["new grad", "new graduate", "entry level", "junior"],
  gradKeywords: ["new grad", "new graduate", "recent graduate", "graduate program", "early talent"],
  timingKeywords: ["jan 2027", "january 2027", "2027"],
  excludeTitleKeywords: ["senior", "staff", "principal", "lead", "director", "manager", "intern"],
  locationWeights: { calgary: 0.5, edmonton: 0.2, remote: 0.15, vancouver: 0.1, seattle: 0.05 },
  offListLocations: "drop",
  requireSponsorshipForUS: true,
  usNoSponsorshipPenalty: 0.35,
  scoreWeights: { location: 0.65, keyword: 0.35 },
};

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

  // `_`-prefixed keys are the inline documentation in preferences.json.
  const clean = Object.fromEntries(Object.entries(fromFile).filter(([k]) => !k.startsWith("_")));

  cached = {
    ...DEFAULT_PREFERENCES,
    ...clean,
    // locationWeights is taken verbatim when the file supplies it, NOT merged
    // over the defaults. Merging made a location impossible to remove: delete
    // "seattle" from the file and the default put it straight back, so the
    // bucket kept resolving and Seattle postings kept being ingested and
    // scored. The set of locations is a list the user owns, and an empty slot
    // in it means "not this one", not "fall back to mine".
    locationWeights: clean.locationWeights || DEFAULT_PREFERENCES.locationWeights,
    // scoreWeights is a fixed pair rather than a set — a missing half means
    // "leave that half alone", so merging is the right behaviour here.
    scoreWeights: { ...DEFAULT_PREFERENCES.scoreWeights, ...(clean.scoreWeights || {}) },
  };
  // "No age limit" isn't valid JSON as Infinity, so it round-trips through
  // `null` on disk (see savePreferences) and is restored here.
  if (cached.maxAgeDays === null) cached.maxAgeDays = Infinity;
  return cached;
}

// Merges `updates` into config/preferences.json on disk and refreshes the
// in-memory cache, so a value set from the dashboard (e.g. the Refresh
// button's freshness window) is the same one discover.js's ingest gate,
// this process's own /api/discovered default, and scripts/rescore.js all see
// afterward - one stored value instead of a run-only override that only
// discover.js ever heard about.
//
// Top-level merge only: every other key (including the `_`-prefixed inline
// docs) is preserved untouched.
export function savePreferences(updates) {
  let onDisk = {};
  if (existsSync(PREFS_PATH)) {
    onDisk = JSON.parse(readFileSync(PREFS_PATH, "utf8"));
  }
  const next = { ...onDisk, ...updates };
  writeFileSync(PREFS_PATH, JSON.stringify(next, null, 2) + "\n");
  cached = null;
  return loadPreferences();
}
