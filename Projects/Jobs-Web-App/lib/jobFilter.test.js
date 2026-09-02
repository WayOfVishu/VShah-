import { test } from "node:test";
import assert from "node:assert/strict";
import Database from "better-sqlite3";
import {
  isFresh,
  ageInDays,
  matchesRole,
  isExcludedBySeniority,
  maxRequiredYears,
  exceedsExperienceCap,
  ingestGate,
  buildAppliedIndex,
  isAlreadyApplied,
  normalizeUrl,
} from "./jobFilter.js";
import { DEFAULT_PREFERENCES } from "./preferences.js";

const prefs = {
  ...DEFAULT_PREFERENCES,
  maxAgeDays: 3,
  roleKeywords: ["software engineer", "data engineer", "machine learning engineer", "developer"],
  levelKeywords: ["new grad", "new graduate", "entry level", "junior"],
  gradKeywords: ["new grad", "new graduate", "graduate program", "graduate rotational"],
  excludeTitleKeywords: ["senior", "staff", "principal", "lead", "director", "manager", "intern"],
};

const NOW = new Date("2026-09-01T12:00:00Z");
const daysAgo = (n) => new Date(NOW.getTime() - n * 86_400_000).toISOString();

// --- freshness -------------------------------------------------------------

test("parses both ISO and SQLite datetime formats", () => {
  assert.ok(Math.abs(ageInDays("2026-08-29T12:00:00Z", NOW) - 3) < 1e-6);
  assert.ok(Math.abs(ageInDays("2026-08-29 12:00:00", NOW) - 3) < 1e-6);
  assert.equal(ageInDays("not a date", NOW), null);
});

test("keeps postings inside the window and drops the ones outside it", () => {
  assert.equal(isFresh({ posted_date: daysAgo(1) }, { maxAgeDays: 3, now: NOW }), true);
  assert.equal(isFresh({ posted_date: daysAgo(2.9) }, { maxAgeDays: 3, now: NOW }), true);
  assert.equal(isFresh({ posted_date: daysAgo(4) }, { maxAgeDays: 3, now: NOW }), false);
  assert.equal(isFresh({ posted_date: daysAgo(30) }, { maxAgeDays: 3, now: NOW }), false);
});

test("an undated posting falls back to first_seen_at", () => {
  assert.equal(isFresh({ posted_date: null, first_seen_at: daysAgo(1) }, { maxAgeDays: 3, now: NOW }), true);
  assert.equal(isFresh({ posted_date: null, first_seen_at: daysAgo(9) }, { maxAgeDays: 3, now: NOW }), false);
});

test("a posting with no date at all is admitted once, unless strict", () => {
  const undated = { posted_date: null, first_seen_at: null };
  assert.equal(isFresh(undated, { maxAgeDays: 3, now: NOW }), true);
  assert.equal(isFresh(undated, { maxAgeDays: 3, now: NOW, strict: true }), false);
});

// --- role and seniority gates ---------------------------------------------

test("role keywords are matched against the title", () => {
  assert.equal(matchesRole({ title: "Software Engineer, Platform" }, prefs), true);
  assert.equal(matchesRole({ title: "Machine Learning Engineer" }, prefs), true);
  assert.equal(matchesRole({ title: "TIG Welder (Starship) - Level 4/5" }, prefs), false);
  assert.equal(matchesRole({ title: "Accounts Payable Specialist" }, prefs), false);
});

test("a graduate-program title clears the role gate on its own", () => {
  assert.equal(matchesRole({ title: "New Graduate Rotational Program" }, prefs), true);
});

test("a generic level marker does not clear the role gate by itself", () => {
  // Both of these got through on the real corpus when the whole of
  // levelKeywords was allowed to satisfy the gate.
  assert.equal(matchesRole({ title: "Customer Support Associate, Bilingual" }, prefs), false);
  assert.equal(matchesRole({ title: "(Entry Level) Production Technician - PCBA" }, prefs), false);
  // ...but paired with a real role keyword it still passes.
  assert.equal(matchesRole({ title: "Entry Level Software Engineer" }, prefs), true);
});

test("seniority markers are excluded", () => {
  assert.equal(isExcludedBySeniority({ title: "Senior Software Engineer" }, prefs), true);
  assert.equal(isExcludedBySeniority({ title: "Staff Data Engineer" }, prefs), true);
  assert.equal(isExcludedBySeniority({ title: "Engineering Manager" }, prefs), true);
  assert.equal(isExcludedBySeniority({ title: "Software Engineer Intern" }, prefs), true);
  assert.equal(isExcludedBySeniority({ title: "Software Engineer" }, prefs), false);
});

test("a seniority word inside a longer word does not trigger", () => {
  assert.equal(isExcludedBySeniority({ title: "Leadership Program Software Engineer" }, prefs), false);
});

// --- experience cap ---------------------------------------------------------

test("reads the real Top Hat phrasing (space before the plus)", () => {
  assert.equal(maxRequiredYears("You are:\n\n• 3 + years of experience in full-stack software development."), 3);
});

test("takes the top of a stated range", () => {
  assert.equal(maxRequiredYears("1-2+ years of experience in analytics, data engineering, or similar work."), 2);
});

test("catches 'experience' stated before the years figure, not just after", () => {
  assert.equal(maxRequiredYears("Minimum experience needed of 3+ years as a full stack developer."), 3);
});

test("a years mention with no 'experience' nearby is not a requirement", () => {
  assert.equal(maxRequiredYears("Top Hat has served 750+ universities for over 10 years."), null);
});

test("no description means no known requirement", () => {
  assert.equal(maxRequiredYears(null), null);
  assert.equal(maxRequiredYears(""), null);
});

test("2 years or less clears the cap; anything higher does not", () => {
  assert.equal(exceedsExperienceCap({ description: "1+ years of experience required." } ), false);
  assert.equal(exceedsExperienceCap({ description: "2+ years of experience required." } ), false);
  assert.equal(exceedsExperienceCap({ description: "3+ years of experience required." } ), true);
  assert.equal(exceedsExperienceCap({ description: "at least 7 years of industry experience." } ), true);
});

// --- the ingest gate -------------------------------------------------------

const fresh = (over) => ({
  title: "Software Engineer",
  location: "Calgary, AB",
  description: "Build things.",
  posted_date: daysAgo(1),
  apply_url: "https://example.com/jobs/1",
  ...over,
});

test("an on-target posting is kept and scored", () => {
  const result = ingestGate(fresh({ title: "New Grad Software Engineer" }), prefs, NOW);
  assert.equal(result.keep, true);
  assert.equal(result.bucket, "calgary");
  assert.ok(result.matchScore > 0.8);
});

test("each rejection reports why", () => {
  assert.deepEqual(
    ingestGate(fresh({ posted_date: daysAgo(10) }), prefs, NOW),
    { keep: false, reason: "stale" }
  );
  assert.deepEqual(
    ingestGate(fresh({ title: "Senior Software Engineer" }), prefs, NOW),
    { keep: false, reason: "seniority" }
  );
  assert.deepEqual(
    ingestGate(fresh({ title: "TIG Welder (Starship) - Level 4/5" }), prefs, NOW),
    { keep: false, reason: "off-role" }
  );
  assert.deepEqual(
    ingestGate(fresh({ description: "You are: 3+ years of experience in full-stack development." }), prefs, NOW),
    { keep: false, reason: "experience" }
  );
  assert.deepEqual(
    ingestGate(fresh({ location: "Toronto, ON" }), prefs, NOW),
    { keep: false, reason: "off-location" }
  );
});

test("the SpaceX welder that topped the old feed is now rejected", () => {
  const welder = {
    title: "TIG Welder (Starship) - Level 4/5",
    company: "SpaceX",
    location: "Starbase, TX",
    posted_date: daysAgo(1),
  };
  assert.equal(ingestGate(welder, prefs, NOW).keep, false);
});

test("off-list locations survive when the preference says keep", () => {
  const keepPrefs = { ...prefs, offListLocations: "keep" };
  const result = ingestGate(fresh({ location: "Toronto, ON" }), keepPrefs, NOW);
  assert.equal(result.keep, true);
  assert.equal(result.bucket, null);
  // No location weight, so the keyword half is all it has.
  assert.equal(result.locationScore, 0);
});

test("a posting with no location is kept and bucketed unknown", () => {
  const result = ingestGate(fresh({ location: null }), prefs, NOW);
  assert.equal(result.keep, true);
  assert.equal(result.bucket, "unknown");
});

// --- already applied -------------------------------------------------------

function appliedDb() {
  const db = new Database(":memory:");
  db.exec(`
    CREATE TABLE jobs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL, company TEXT NOT NULL, url TEXT
    )
  `);
  const insert = db.prepare("INSERT INTO jobs (title, company, url) VALUES (?, ?, ?)");
  insert.run("Software Engineer", "StackAdapt", "https://boards.greenhouse.io/stackadapt/jobs/42");
  insert.run("Data Engineer", "Benevity", null);
  return db;
}

test("matches an applied role by apply url", () => {
  const index = buildAppliedIndex(appliedDb());
  assert.equal(
    isAlreadyApplied({ apply_url: "https://boards.greenhouse.io/stackadapt/jobs/42" }, index),
    true
  );
});

test("tracking parameters do not defeat the url match", () => {
  const index = buildAppliedIndex(appliedDb());
  assert.equal(
    isAlreadyApplied(
      { apply_url: "https://boards.greenhouse.io/stackadapt/jobs/42?gh_src=abc&utm_campaign=x" },
      index
    ),
    true
  );
  assert.equal(normalizeUrl("https://x.com/a/?b=1#c"), "https://x.com/a");
});

test("matches a hand-logged application on title and company", () => {
  const index = buildAppliedIndex(appliedDb());
  // Applied to it manually months ago, no url recorded, different board.
  assert.equal(
    isAlreadyApplied({ title: "Data Engineer", company: "Benevity", apply_url: "https://elsewhere/x" }, index),
    true
  );
});

test("location is ignored when matching an application", () => {
  const index = buildAppliedIndex(appliedDb());
  // The Remote twin of a role you applied to in Calgary is the same role.
  assert.equal(
    isAlreadyApplied(
      { title: "Data Engineer", company: "Benevity", location: "Remote", apply_url: "https://x/1" },
      index
    ),
    true
  );
});

test("a genuinely new role is not flagged as applied", () => {
  const index = buildAppliedIndex(appliedDb());
  assert.equal(
    isAlreadyApplied({ title: "Machine Learning Engineer", company: "Attabotics", apply_url: "https://x/9" }, index),
    false
  );
});
