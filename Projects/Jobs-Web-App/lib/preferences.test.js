import test from "node:test";
import assert from "node:assert/strict";
import { writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

// loadPreferences resolves its path once at module load, so the env var has to
// be set before the dynamic import below.
const dir = mkdtempSync(path.join(tmpdir(), "jobs-prefs-"));
const PREFS = path.join(dir, "preferences.json");
process.env.JOB_PREFS_PATH = PREFS;

const { loadPreferences, DEFAULT_PREFERENCES } = await import("./preferences.js");

const write = (obj) => writeFileSync(PREFS, JSON.stringify(obj, null, 2));
const load = () => loadPreferences({ reload: true });

test.after(() => rmSync(dir, { recursive: true, force: true }));

test("a location removed from the file stays removed", () => {
  // Regression: locationWeights used to be spread over DEFAULT_PREFERENCES, so
  // deleting "seattle" from the file put it straight back and Seattle
  // postings kept being ingested and scored. The set of locations is a list
  // the user owns; a missing entry means "not this one", not "use mine".
  write({ locationWeights: { calgary: 0.6, edmonton: 0.2, remote: 0.2 } });
  const prefs = load();

  assert.ok(!("seattle" in prefs.locationWeights));
  assert.ok(!("vancouver" in prefs.locationWeights));
  assert.deepEqual(Object.keys(prefs.locationWeights).sort(), ["calgary", "edmonton", "remote"]);
});

test("falls back to the default location set only when the file omits it entirely", () => {
  write({ maxAgeDays: 14 });
  assert.deepEqual(load().locationWeights, DEFAULT_PREFERENCES.locationWeights);
});

test("scoreWeights still merges, because it is a fixed pair rather than a set", () => {
  // Supplying only one half means "leave the other alone" — unlike
  // locationWeights, an absent key here is not a removal.
  write({ scoreWeights: { location: 0.8 } });
  const { scoreWeights } = load();
  assert.equal(scoreWeights.location, 0.8);
  assert.equal(scoreWeights.keyword, DEFAULT_PREFERENCES.scoreWeights.keyword);
});

test("maxAgeDays comes from the file, not from a default", () => {
  // The freshness window is chosen in the dashboard and saved here. Nothing
  // else may invent one: a hard-coded `selected` option in index.html used to
  // be a second copy of this value, and it overwrote the saved one on every
  // discovery run.
  write({ maxAgeDays: 21 });
  assert.equal(load().maxAgeDays, 21);
});

test("null maxAgeDays is restored as Infinity, so 'Any age' means no limit", () => {
  // Infinity is not valid JSON, so "no age limit" round-trips through null.
  write({ maxAgeDays: null });
  assert.equal(load().maxAgeDays, Infinity);
});

test("with no config file at all, no freshness window is invented", () => {
  // Failing open is deliberate. With nothing configured, silently hiding
  // postings behind a number the user never chose is the worse failure — it is
  // exactly what the old default of 3 days did.
  rmSync(PREFS, { force: true });
  assert.equal(load().maxAgeDays, Infinity);
});

test("`_`-prefixed documentation keys never reach the preferences object", () => {
  write({ _maxAgeDays: "docs about the setting", maxAgeDays: 5 });
  const prefs = load();
  assert.equal(prefs.maxAgeDays, 5);
  assert.ok(!("_maxAgeDays" in prefs));
});

test("a malformed file is shouted about rather than silently defaulted", () => {
  writeFileSync(PREFS, "{ not json");
  assert.throws(() => load(), /not valid JSON/);
});
