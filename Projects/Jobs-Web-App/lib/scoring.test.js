import { test } from "node:test";
import assert from "node:assert/strict";
import {
  locationBucket,
  locationScore,
  keywordScore,
  scoreJob,
  weightedMix,
  isUnsponsoredUS,
  matchesPhrase,
} from "./scoring.js";
import { DEFAULT_PREFERENCES } from "./preferences.js";

const prefs = {
  ...DEFAULT_PREFERENCES,
  roleKeywords: ["software engineer", "data engineer", "machine learning engineer", "developer"],
  levelKeywords: ["new grad", "new graduate", "entry level", "junior"],
  timingKeywords: ["jan 2027", "january 2027", "2027"],
};

// --- phrase matching -------------------------------------------------------

test("matchesPhrase respects word boundaries", () => {
  assert.equal(matchesPhrase("Team Lead, Platform", "lead"), true);
  assert.equal(matchesPhrase("Leadership Development Program", "lead"), false);
  assert.equal(matchesPhrase("Software Engineer II", "software engineer"), true);
});

test("matchesPhrase handles a trailing period in the phrase", () => {
  assert.equal(matchesPhrase("Sr. Software Engineer", "sr."), true);
  assert.equal(matchesPhrase("Software Engineer", "sr."), false);
});

// --- location buckets ------------------------------------------------------

test("resolves the five preferred locations", () => {
  assert.equal(locationBucket({ location: "Calgary, AB" }, prefs), "calgary");
  assert.equal(locationBucket({ location: "Edmonton, Alberta" }, prefs), "edmonton");
  assert.equal(locationBucket({ location: "Vancouver, BC" }, prefs), "vancouver");
  assert.equal(locationBucket({ location: "Seattle, WA" }, prefs), "seattle");
  assert.equal(locationBucket({ location: "Remote" }, prefs), "remote");
});

test("Vancouver WA is Seattle-area, not British Columbia", () => {
  assert.equal(locationBucket({ location: "Vancouver, WA" }, prefs), "seattle");
  assert.equal(locationBucket({ location: "Vancouver, Washington" }, prefs), "seattle");
  assert.equal(locationBucket({ location: "Vancouver, British Columbia" }, prefs), "vancouver");
});

test("a hybrid posting takes its highest-weighted bucket", () => {
  // Calgary (0.5) beats remote (0.15) - it is a Calgary job you may work
  // remotely, not a remote job that happens to mention Calgary.
  assert.equal(locationBucket({ location: "Calgary, AB / Remote" }, prefs), "calgary");
  assert.equal(locationBucket({ location: "Edmonton or Vancouver" }, prefs), "edmonton");
  // Remote (15%) outranks Vancouver (10%) in the configured weights, so this
  // one lands in remote rather than vancouver.
  assert.equal(locationBucket({ location: "Remote - Vancouver or Seattle" }, prefs), "remote");
});

test("the remote_status flag alone is enough for the remote bucket", () => {
  assert.equal(locationBucket({ location: "", remote_status: "remote" }, prefs), "remote");
});

test("off-list returns null, absent returns unknown", () => {
  assert.equal(locationBucket({ location: "Toronto, ON" }, prefs), null);
  assert.equal(locationBucket({ location: "Starbase, TX" }, prefs), null);
  assert.equal(locationBucket({ location: null }, prefs), "unknown");
  assert.equal(locationBucket({ location: "  " }, prefs), "unknown");
});

// --- location scoring ------------------------------------------------------

test("location score normalizes the top preference to 1.0", () => {
  assert.equal(locationScore({ location: "Calgary, AB" }, prefs), 1);
  assert.equal(locationScore({ location: "Edmonton, AB" }, prefs), 0.4);
  assert.equal(locationScore({ location: "Vancouver, BC" }, prefs), 0.2);
  assert.equal(locationScore({ location: "Toronto, ON" }, prefs), 0);
});

test("remote keeps its full weight when it is not fenced to the US", () => {
  const job = { location: "Remote (Canada)", remote_status: "remote", description: "Work anywhere in Canada." };
  assert.equal(locationScore(job, prefs), 0.3);
});

// --- work authorization ----------------------------------------------------

test("a Seattle role silent on sponsorship is penalized", () => {
  const job = { title: "Software Engineer", location: "Seattle, WA", description: "Join our team." };
  assert.equal(isUnsponsoredUS(job, "seattle", prefs), true);
  // 0.05/0.5 = 0.1, then * 0.35
  assert.ok(Math.abs(locationScore(job, prefs) - 0.035) < 1e-9);
});

test("a Seattle role that mentions sponsorship keeps its full weight", () => {
  const job = {
    title: "Software Engineer",
    location: "Seattle, WA",
    description: "We sponsor visas for exceptional candidates.",
  };
  assert.equal(isUnsponsoredUS(job, "seattle", prefs), false);
  assert.ok(Math.abs(locationScore(job, prefs) - 0.1) < 1e-9);
});

test("a US-only remote role is treated like Seattle", () => {
  const job = {
    title: "Data Engineer",
    location: "Remote",
    remote_status: "remote",
    description: "This role is US only.",
  };
  assert.equal(isUnsponsoredUS(job, "remote", prefs), true);
});

test("US fencing is off entirely when the preference is disabled", () => {
  const open = { ...prefs, requireSponsorshipForUS: false };
  const job = { title: "Software Engineer", location: "Seattle, WA", description: "Join our team." };
  assert.equal(isUnsponsoredUS(job, "seattle", open), false);
});

// --- keyword scoring -------------------------------------------------------

test("a title hit outscores a description-only hit", () => {
  const inTitle = keywordScore({ title: "Software Engineer", description: "" }, prefs);
  const inBody = keywordScore({ title: "Widget Wrangler", description: "software engineer work" }, prefs);
  assert.ok(inTitle > inBody);
});

test("new-grad and Jan 2027 signals stack", () => {
  const plain = keywordScore({ title: "Software Engineer", description: "" }, prefs);
  const full = keywordScore(
    { title: "New Grad Software Engineer", description: "Starting January 2027." },
    prefs
  );
  assert.ok(full > plain);
  assert.ok(Math.abs(full - (0.5 + 0.3 + 0.2 * 0.7)) < 1e-9);
});

test("an unrelated posting scores zero on keywords", () => {
  assert.equal(keywordScore({ title: "TIG Welder (Starship) - Level 4/5", description: "Weld." }, prefs), 0);
});

// --- combined score --------------------------------------------------------

test("the ideal posting outranks every compromise", () => {
  const ideal = scoreJob(
    { title: "New Graduate Software Engineer", location: "Calgary, AB", description: "Start January 2027." },
    prefs
  );
  const seattle = scoreJob(
    { title: "New Graduate Software Engineer", location: "Seattle, WA", description: "Start January 2027." },
    prefs
  );
  const edmonton = scoreJob({ title: "Software Engineer", location: "Edmonton, AB", description: "" }, prefs);

  assert.equal(ideal.bucket, "calgary");
  assert.ok(ideal.matchScore > edmonton.matchScore);
  assert.ok(edmonton.matchScore > seattle.matchScore);
  assert.ok(ideal.matchScore <= 1);
});

// --- the balanced mix ------------------------------------------------------

function makeJobs(bucket, n) {
  return Array.from({ length: n }, (_, i) => ({
    id: `${bucket}-${i}`,
    location_bucket: bucket,
    match_score: 1 - i / 1000,
  }));
}

test("the mix approximates the configured proportions", () => {
  const jobs = [
    ...makeJobs("calgary", 100),
    ...makeJobs("edmonton", 100),
    ...makeJobs("remote", 100),
    ...makeJobs("vancouver", 100),
    ...makeJobs("seattle", 100),
  ];
  const top = weightedMix(jobs, prefs).slice(0, 100);
  const share = (b) => top.filter((j) => j.location_bucket === b).length;

  // Each within a couple of rows of its target out of 100.
  assert.ok(Math.abs(share("calgary") - 50) <= 2, `calgary ${share("calgary")}`);
  assert.ok(Math.abs(share("edmonton") - 20) <= 2, `edmonton ${share("edmonton")}`);
  assert.ok(Math.abs(share("remote") - 15) <= 2, `remote ${share("remote")}`);
  assert.ok(Math.abs(share("vancouver") - 10) <= 2, `vancouver ${share("vancouver")}`);
  assert.ok(Math.abs(share("seattle") - 5) <= 2, `seattle ${share("seattle")}`);
});

test("the mix keeps each bucket internally ranked by score", () => {
  const jobs = [...makeJobs("calgary", 10), ...makeJobs("seattle", 10)];
  const calgary = weightedMix(jobs, prefs).filter((j) => j.location_bucket === "calgary");
  const scores = calgary.map((j) => j.match_score);
  assert.deepEqual(scores, [...scores].sort((a, b) => b - a));
});

test("a thin bucket does not stall the feed", () => {
  // Only one Seattle row exists; Calgary should still fill the rest.
  const jobs = [...makeJobs("calgary", 20), ...makeJobs("seattle", 1)];
  const mixed = weightedMix(jobs, prefs);
  assert.equal(mixed.length, 21);
  assert.equal(mixed.filter((j) => j.location_bucket === "seattle").length, 1);
});

test("unknown-location rows sort after the mix, never inside it", () => {
  const jobs = [
    ...makeJobs("calgary", 3),
    { id: "u1", location_bucket: "unknown", match_score: 0.99 },
  ];
  const mixed = weightedMix(jobs, prefs);
  assert.equal(mixed[mixed.length - 1].id, "u1");
});

// --- US detection, and the words that are not countries ---------------------

test("the word \"or\" is not Oregon and \"CA\" is not California", () => {
  // Both used to fire: `\bor\b` made "Remote or Hybrid" a US posting and
  // `\bca\b` made the Canadian country code in "Vancouver, BC, CA" one too,
  // penalising the Canadian remote roles this search depends on.
  for (const location of ["Remote or Hybrid", "Vancouver, BC, CA", "Toronto, ON, CA", "Remote, Canada"]) {
    const job = { title: "Software Engineer", location, remote_status: "remote", description: "Build with us." };
    assert.equal(isUnsponsoredUS(job, "remote", prefs), false, location);
  }
});

test("a genuinely US-located remote role is still caught", () => {
  for (const location of ["Remote, Seattle, WA", "Remote (Colorado)", "Remote — United States"]) {
    const job = { title: "Software Engineer", location, remote_status: "remote", description: "Build things." };
    assert.equal(isUnsponsoredUS(job, "remote", prefs), true, location);
  }
});

// --- the remote bucket now means remote *he can take* -----------------------

test("a hybrid posting does not occupy the remote bucket", () => {
  const job = {
    title: "Software Engineer",
    location: "Remote",
    remote_status: "remote",
    description: "Hybrid role — 3 days per week in the office.",
  };
  assert.equal(locationBucket(job, prefs), null);
});

test("a hybrid posting in Calgary is still a Calgary job", () => {
  // Hybrid is only a problem when the office is one you cannot drive to.
  const job = {
    title: "Software Engineer",
    location: "Calgary, AB — Hybrid",
    description: "Hybrid role — 3 days per week in the office.",
  };
  assert.equal(locationBucket(job, prefs), "calgary");
});

test("US-only remote does not occupy the remote bucket", () => {
  const job = {
    title: "Software Engineer",
    location: "Remote",
    remote_status: "remote",
    description: "This role is US-based. Must reside in the United States.",
  };
  assert.equal(locationBucket(job, prefs), null);
});

test("remote across Canada does occupy the remote bucket", () => {
  const job = {
    title: "Software Engineer",
    location: "Remote - Canada",
    remote_status: "remote",
    description: "Work from anywhere in Canada.",
  };
  assert.equal(locationBucket(job, prefs), "remote");
});
