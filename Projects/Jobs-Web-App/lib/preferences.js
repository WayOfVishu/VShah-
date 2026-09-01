// Loads config/preferences.json — the "what you want" half of the config, kept
// separate from sources.json because scripts/bootstrap-sources.js rewrites
// that file wholesale and would otherwise wipe these settings.

import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PREFS_PATH = process.env.JOB_PREFS_PATH || path.join(__dirname, "..", "config", "preferences.json");

// Mirrors config/preferences.json. Used verbatim when the file is missing, and
// key-by-key for anything the file leaves out, so a partial config is valid.
export const DEFAULT_PREFERENCES = {
  maxAgeDays: 3,
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
    locationWeights: { ...DEFAULT_PREFERENCES.locationWeights, ...(clean.locationWeights || {}) },
    scoreWeights: { ...DEFAULT_PREFERENCES.scoreWeights, ...(clean.scoreWeights || {}) },
  };
  return cached;
}
