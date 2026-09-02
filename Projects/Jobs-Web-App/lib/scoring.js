// Turns a normalized posting into a location bucket and a 0-1 match_score, and
// orders a scored list into the balanced feed.
//
// Two things are being asked of the location percentages at once:
//   * as a *ranking* signal, normalized against the largest weight, they form
//     the location half of match_score (Calgary 1.00, Edmonton 0.40, ...);
//   * as a *mix*, taken at face value, they set the proportions of the default
//     feed - roughly half Calgary, a fifth Edmonton, and so on - so a Seattle
//     or Vancouver role still surfaces instead of being buried under Calgary.

import { loadPreferences } from "./preferences.js";
import { isTrulyRemote } from "./remote.js";

// Each bucket's patterns are tried against the location string and, for
// `remote`, the connector's remote_status flag.
//
// Vancouver is the trap here: Vancouver, WA is a Portland suburb, not British
// Columbia, so the BC pattern has to rule out the Washington one explicitly.
const BUCKET_PATTERNS = {
  calgary: [/\bcalgary\b/i, /\byyc\b/i],
  edmonton: [/\bedmonton\b/i, /\byeg\b/i],
  vancouver: [/\bvancouver\b(?!\s*,?\s*(wa\b|washington))/i, /\bburnaby\b/i, /\brichmond\s*,?\s*bc\b/i],
  seattle: [/\bseattle\b/i, /\bbellevue\s*,?\s*wa\b/i, /\bredmond\s*,?\s*wa\b/i, /\bvancouver\s*,?\s*(wa\b|washington)/i],
  remote: [/\bremote\b/i, /\bwork from home\b/i, /\banywhere\b/i, /\bdistributed\b/i, /\btelecommute\b/i],
};

// "US" is matched case-sensitively throughout. Lowercase "us" is the English
// pronoun, and matching it case-insensitively made "Build things with us" read
// as a US work-authorization restriction. "United States" is safe either way.
const US_ABBR = "(?:U\\.S\\.A?|USA?)";
const US_RESTRICTED = new RegExp(
  `\\b(?:${US_ABBR}|[Uu]nited [Ss]tates)[\\s-]*(?:only|based|residents?|citizens?)\\b` +
    `|\\bmust be (?:located|based) in the (?:${US_ABBR}|[Uu]nited [Ss]tates)\\b`
);
const SPONSORSHIP_MENTION = /\b(?:sponsor\w*|visa|work(?:ing)? authorization|work permit|h-?1b|tn visa|relocation (?:support|assistance))\b/i;

// A US state, used only to decide whether a posting is US-restricted for
// work-authorization purposes.
//
// Two-letter codes count only in the "City, ST" shape and only capitalised.
// Matched loosely, they are a minefield: `\bor\b` made the word "or" into
// Oregon, so "Remote or Hybrid" was a US posting, and `\bca\b` made the
// Canadian country code into California, so "Vancouver, BC, CA" was too —
// both penalising exactly the Canadian remote roles that matter most here.
// CA is therefore left out of the code list entirely and California is matched
// by name.
const US_STATE_CODES =
  "AL|AK|AZ|AR|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY";
const US_STATE_NAMES =
  "California|Colorado|Texas|New York|Washington|Oregon|Illinois|Massachusetts|Florida|Georgia|Arizona|Nevada|Utah|Virginia|Maryland|Pennsylvania|New Jersey|Ohio|Michigan|Minnesota|Wisconsin|North Carolina";
const US_LOCATION = new RegExp(
  `,\\s*(?:${US_STATE_CODES})\\b|\\b(?:${US_STATE_NAMES})\\b|\\bUnited States\\b|\\bUSA\\b`
);

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Word-boundary phrase match, so "lead" hits "Team Lead" but not "Leadership".
// A phrase that starts or ends with punctuation ("sr.") gets the boundary
// dropped on that side, since \b would never fire there.
export function matchesPhrase(haystack, phrase) {
  if (!haystack || !phrase) return false;
  const term = phrase.trim();
  if (!term) return false;
  const lead = /^[a-z0-9]/i.test(term) ? "\\b" : "";
  const tail = /[a-z0-9]$/i.test(term) ? "\\b" : "";
  return new RegExp(`${lead}${escapeRegExp(term)}${tail}`, "i").test(haystack);
}

export function matchesAny(haystack, phrases = []) {
  return phrases.some((p) => matchesPhrase(haystack, p));
}

// Resolves a posting to its highest-weighted matching bucket: a role listed as
// "Calgary, AB / Remote" is a Calgary job, not a remote one.
// Returns null when a location is stated but matches nothing (off-list), and
// "unknown" when no location is stated at all.
export function locationBucket(job, prefs = loadPreferences()) {
  const text = [job.location, job.remote_status].filter(Boolean).join(" ").trim();

  if (!text) return "unknown";

  const matched = Object.keys(prefs.locationWeights).filter((bucket) => {
    // The remote bucket is the one that cannot be decided from the location
    // string. A posting saying "Remote" may be US-only (a TN visa problem) or
    // hybrid-in-another-city (a relocation problem); either way it is not a
    // remote job *he can take*, so the description gets the deciding vote.
    // See lib/remote.js.
    if (bucket === "remote") return isTrulyRemote(job);
    return (BUCKET_PATTERNS[bucket] || []).some((re) => re.test(text));
  });

  if (matched.length === 0) return null;
  return matched.reduce((best, b) =>
    (prefs.locationWeights[b] || 0) > (prefs.locationWeights[best] || 0) ? b : best
  );
}

// True when the posting is fenced to the United States and never mentions
// sponsorship - the case that should stop eating the Seattle share.
export function isUnsponsoredUS(job, bucket, prefs = loadPreferences()) {
  if (!prefs.requireSponsorshipForUS) return false;

  const locationText = String(job.location || "");
  const body = [job.title, job.description].filter(Boolean).join("\n");
  const usFenced =
    bucket === "seattle" ||
    US_RESTRICTED.test(locationText) ||
    US_RESTRICTED.test(body) ||
    (bucket === "remote" && US_LOCATION.test(locationText) && !/\bcanada\b/i.test(locationText));

  if (!usFenced) return false;
  return !SPONSORSHIP_MENTION.test(body);
}

// 0-1, normalized so the top-weighted location scores a flat 1.0 rather than
// its raw 0.5 - otherwise even a perfect match would cap match_score at 0.5.
export function locationScore(job, prefs = loadPreferences(), bucket = locationBucket(job, prefs)) {
  if (!bucket || bucket === "unknown") return 0;
  const weights = prefs.locationWeights;
  const max = Math.max(...Object.values(weights));
  let score = (weights[bucket] || 0) / (max || 1);
  if (isUnsponsoredUS(job, bucket, prefs)) score *= prefs.usNoSponsorshipPenalty;
  return score;
}

// 0-1 across three independent signals: the role itself, the new-grad level,
// and the Jan 2027 start window. Title hits count more than description hits -
// a description that merely name-drops "machine learning" is not an ML role.
export function keywordScore(job, prefs = loadPreferences()) {
  const title = String(job.title || "");
  const description = String(job.description || "");

  const role = matchesAny(title, prefs.roleKeywords) ? 1 : matchesAny(description, prefs.roleKeywords) ? 0.4 : 0;
  const level = matchesAny(title, prefs.levelKeywords) ? 1 : matchesAny(description, prefs.levelKeywords) ? 0.5 : 0;
  const timing = matchesAny(title, prefs.timingKeywords) ? 1 : matchesAny(description, prefs.timingKeywords) ? 0.7 : 0;

  return 0.5 * role + 0.3 * level + 0.2 * timing;
}

// The full picture for one posting: its bucket, its score, and the parts the
// score came from, so the dashboard can explain a ranking rather than just
// asserting one.
export function scoreJob(job, prefs = loadPreferences()) {
  const bucket = locationBucket(job, prefs);
  const loc = locationScore(job, prefs, bucket);
  const kw = keywordScore(job, prefs);
  const { location: wLoc, keyword: wKw } = prefs.scoreWeights;

  return {
    bucket,
    locationScore: Number(loc.toFixed(4)),
    keywordScore: Number(kw.toFixed(4)),
    unsponsoredUS: bucket ? isUnsponsoredUS(job, bucket, prefs) : false,
    matchScore: Number((wLoc * loc + wKw * kw).toFixed(4)),
  };
}

// Orders a scored list so the buckets appear in the configured proportions.
//
// Stride scheduling: the k-th best job in a bucket of weight w is handed the
// virtual position (k + 0.5) / w, and everything is sorted by that. Calgary at
// 0.5 emits a row every 2 positions and Seattle at 0.05 every 20, which is the
// 50/20/15/10/5 split by construction - without needing to know how long the
// list is, and degrading gracefully when a bucket runs dry.
//
// "unknown"-bucket rows carry no location evidence to mix on, so they are
// appended after the mix rather than competing inside it.
export function weightedMix(jobs, prefs = loadPreferences()) {
  const weights = prefs.locationWeights;
  const buckets = new Map();
  const unknown = [];

  for (const job of jobs) {
    const bucket = job.location_bucket || "unknown";
    if (bucket === "unknown" || !weights[bucket]) {
      unknown.push(job);
      continue;
    }
    if (!buckets.has(bucket)) buckets.set(bucket, []);
    buckets.get(bucket).push(job);
  }

  const positioned = [];
  for (const [bucket, rows] of buckets) {
    rows.sort((a, b) => (b.match_score ?? 0) - (a.match_score ?? 0));
    rows.forEach((job, k) => positioned.push({ job, pos: (k + 0.5) / weights[bucket] }));
  }
  positioned.sort((a, b) => a.pos - b.pos);

  unknown.sort((a, b) => (b.match_score ?? 0) - (a.match_score ?? 0));
  return [...positioned.map((p) => p.job), ...unknown];
}
