// The ingest gate: which postings are worth putting in the database at all,
// and which ones you have already applied to.
//
// Tier 1 connectors pull a company's entire public board - the last live run
// brought back ~2900 postings from six companies, welders and accountants
// included. Filtering at ingest keeps the database the size of the job search
// rather than the size of the internet.

import { locationBucket, matchesAny, scoreJob } from "./scoring.js";
import { loadPreferences } from "./preferences.js";
import { dedupKey } from "./dedup.js";

// SQLite writes datetime('now') as "YYYY-MM-DD HH:MM:SS" in UTC, while
// connectors hand back ISO 8601. Both need to parse.
export function parseDate(value) {
  if (!value) return null;
  const text = String(value).trim();
  const iso = /\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(text) ? `${text.replace(" ", "T")}Z` : text;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function ageInDays(value, now = new Date()) {
  const d = parseDate(value);
  if (!d) return null;
  return (now.getTime() - d.getTime()) / 86_400_000;
}

// Fresh means posted within maxAgeDays.
//
// Most connectors give a posted_date, but not all do (WeWorkRemotely's RSS and
// some career pages omit it). A posting with no date is treated as fresh the
// first time it is seen rather than discarded, because "we don't know" is not
// the same as "it's old" - and once it is in the database, first_seen_at gives
// it a real clock. `strict` flips that for callers that would rather lose an
// undated posting than admit a stale one.
export function isFresh(job, { maxAgeDays, now = new Date(), strict = false } = {}) {
  const limit = maxAgeDays ?? loadPreferences().maxAgeDays;
  const posted = ageInDays(job.posted_date, now);
  if (posted !== null) return posted <= limit;

  const seen = ageInDays(job.first_seen_at, now);
  if (seen !== null) return seen <= limit;

  return !strict;
}

// A title that names a graduate program clears the role gate on its own -
// "New Graduate Rotational Program" is worth seeing even though it names no
// engineering discipline.
//
// Only gradKeywords get that exemption, not the whole of levelKeywords. The
// generic level markers ("associate", "junior", "entry level") attach to every
// function in a company, and letting them satisfy the gate pulled in
// "Customer Support Associate" and "(Entry Level) Production Technician" on
// the real corpus. They still count toward the score.
export function matchesRole(job, prefs = loadPreferences()) {
  const title = String(job.title || "");
  return matchesAny(title, prefs.roleKeywords) || matchesAny(title, prefs.gradKeywords);
}

export function isExcludedBySeniority(job, prefs = loadPreferences()) {
  return matchesAny(String(job.title || ""), prefs.excludeTitleKeywords);
}

// Hardcoded rather than a preference: this is a fact about the applicant
// (years of professional experience actually held), not a tunable search
// preference, so it doesn't belong in preferences.json next to location
// weights and keyword lists.
export const EXPERIENCE_CAP_YEARS = 2;

// Catches "3+ years", "3 + years", "1-2+ years", "at least 7 years" etc.
// anywhere near the word "experience" in the description. A years-mention
// with no "experience" nearby (e.g. "10 years in business") is left alone -
// the window, not a stricter phrase match, is what keeps this simple.
const YEARS_MENTION = /\b(\d+)\s*(?:-\s*(\d+)\s*)?\+?\s*years?\b(?:['’]s)?/gi;
const EXPERIENCE_WINDOW_CHARS = 60;

// Highest years-of-experience figure the posting states, or null if it states
// none. Used both to gate ingest and to explain a rejection in the run log.
export function maxRequiredYears(description) {
  if (!description) return null;
  const text = String(description);
  let max = null;
  let match;
  YEARS_MENTION.lastIndex = 0;
  while ((match = YEARS_MENTION.exec(text))) {
    const start = Math.max(0, match.index - EXPERIENCE_WINDOW_CHARS);
    const end = Math.min(text.length, match.index + match[0].length + EXPERIENCE_WINDOW_CHARS);
    if (!/experience/i.test(text.slice(start, end))) continue;
    const lo = Number(match[1]);
    const hi = match[2] ? Number(match[2]) : lo;
    const years = Math.max(lo, hi);
    if (max === null || years > max) max = years;
  }
  return max;
}

export function exceedsExperienceCap(job, capYears = EXPERIENCE_CAP_YEARS) {
  const years = maxRequiredYears(job.description);
  return years !== null && years > capYears;
}

// The single decision point for `npm run discover`. Returns a reason string on
// rejection instead of a bare false, so the run summary can report *why* 2900
// postings became 40 rather than leaving it a mystery.
export function ingestGate(job, prefs = loadPreferences(), now = new Date()) {
  if (!isFresh(job, { maxAgeDays: prefs.maxAgeDays, now, strict: false })) {
    return { keep: false, reason: "stale" };
  }
  if (isExcludedBySeniority(job, prefs)) {
    return { keep: false, reason: "seniority" };
  }
  if (!matchesRole(job, prefs)) {
    return { keep: false, reason: "off-role" };
  }
  if (exceedsExperienceCap(job)) {
    return { keep: false, reason: "experience" };
  }

  const bucket = locationBucket(job, prefs);
  if (bucket === null && prefs.offListLocations === "drop") {
    return { keep: false, reason: "off-location" };
  }

  return { keep: true, reason: null, ...scoreJob(job, prefs) };
}

// ---------------------------------------------------------------------------
// Already applied
// ---------------------------------------------------------------------------

// Two ways a posting can already be spoken for: the discovered row was walked
// through the apply flow (status 'applied', applied_job_id set), or the same
// role was logged by hand in the `jobs` table without ever passing through
// discovery. The second is the common one - the applied log predates the
// scraper by a couple hundred applications - so matching on url alone is not
// enough and normalized title+company is used as a second key.
export function buildAppliedIndex(db) {
  const rows = db.prepare("SELECT title, company, url FROM jobs").all();
  const urls = new Set();
  const keys = new Set();

  for (const row of rows) {
    if (row.url) urls.add(normalizeUrl(row.url));
    keys.add(appliedKey(row));
  }
  return { urls, keys };
}

// Query strings on an apply link are tracking noise (?gh_src=, ?utm_campaign=)
// and differ between the copy you clicked and the copy the connector returned.
export function normalizeUrl(url) {
  if (!url) return "";
  return String(url).split(/[?#]/)[0].replace(/\/+$/, "").toLowerCase();
}

// Deliberately drops location, unlike dedup's key: applying to the Calgary
// posting of a role also means you have applied to its Remote twin.
export function appliedKey(row) {
  return dedupKey({ title: row.title, company: row.company, location: "" });
}

export function isAlreadyApplied(job, index) {
  if (!index) return false;
  const url = normalizeUrl(job.apply_url || job.url);
  if (url && index.urls.has(url)) return true;
  return index.keys.has(appliedKey(job));
}
