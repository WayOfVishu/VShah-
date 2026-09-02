import test from "node:test";
import assert from "node:assert/strict";
import { classifyRemote, isTrulyRemote } from "./remote.js";

const job = (location, description = "", remote_status = null) => ({ location, description, remote_status });

// --- the three things "Remote" can mean ------------------------------------

test("remote across Canada qualifies", () => {
  const r = classifyRemote(job("Remote - Canada", "Work from anywhere in Canada."));
  assert.equal(r.scope, "canada");
  assert.equal(r.isHybrid, false);
  assert.equal(r.qualifies, true);
});

test("US-only remote does not qualify — it needs a TN visa", () => {
  const r = classifyRemote(job("Remote (US)", "This role is US-based. Must reside in the United States."));
  assert.equal(r.scope, "us");
  assert.equal(r.qualifies, false);
});

test("remote in Canada or the US still qualifies", () => {
  // Naming the US alongside Canada does not disqualify a job that can be done
  // from Calgary; only a posting that names the US and never Canada is fenced.
  assert.equal(isTrulyRemote(job("Remote", "Open to candidates anywhere in Canada or the US.")), true);
});

test('"remote" that is really hybrid does not qualify', () => {
  const r = classifyRemote(job("Remote", "This is a hybrid role: three days per week in the office."));
  assert.equal(r.isHybrid, true);
  assert.equal(r.qualifies, false);
});

// --- hybrid detection, and its limits --------------------------------------

test("catches the common ways a posting admits to an office", () => {
  const hybridish = [
    "This is a hybrid position.",
    "You will be in office 3 days per week.",
    "Expected to be on-site at least part of the time — 2 days a week in the office.",
    "Must commute to the office weekly.",
    "Our return-to-office policy applies to this role.",
    "Relocation is required for this position.",
  ];
  for (const description of hybridish) {
    assert.equal(classifyRemote(job("Remote", description)).isHybrid, true, description);
  }
});

test('an incidental "onsite" does not make a remote job hybrid', () => {
  // The false positive that would quietly delete real remote jobs: "onsite"
  // appears constantly in unrelated senses.
  const r = classifyRemote(
    job("Remote - Canada", "You will support onsite customer deployments and onsite data centre migrations.")
  );
  assert.equal(r.isHybrid, false);
  assert.equal(r.qualifies, true);
});

test('an explicit "100% remote" outranks a stray mention of hybrid', () => {
  // A company describing its general hybrid policy in boilerplate should not
  // flip a role the posting calls fully remote.
  const r = classifyRemote(
    job("Remote", "This role is 100% remote. (Most of our other teams work hybrid from our Toronto office.)")
  );
  assert.equal(r.isHybrid, false);
  assert.equal(r.qualifies, true);
});

// --- what does not claim remote at all -------------------------------------

test("a plain office job is not remote", () => {
  assert.equal(isTrulyRemote(job("Calgary, AB", "Join our downtown team.")), false);
});

test("the connector's remote flag is enough to claim remote", () => {
  assert.equal(isTrulyRemote(job("Anywhere", "", "remote")), true);
});

test("a bilingual REMOTE/TELETRAVAIL location claims remote", () => {
  assert.equal(classifyRemote(job("REMOTE/TELETRAVAIL, ON, CAN")).claimsRemote, true);
});

// --- scope resolution ------------------------------------------------------

test("scope falls back to unknown, and unknown still qualifies", () => {
  // Excluding ambiguous postings would cost more real Canadian jobs than the
  // US noise it removes; the unsponsored-US penalty in scoring.js demotes the
  // ones that smell American instead.
  const r = classifyRemote(job("Remote", "Build things with us."));
  assert.equal(r.scope, "unknown");
  assert.equal(r.qualifies, true);
});

test("reasons explain a disqualification rather than leaving it a mystery", () => {
  const r = classifyRemote(job("Remote", "Hybrid, 3 days per week in the office."));
  assert.ok(r.reasons.some((x) => x.startsWith("hybrid signal:")));
});

// --- boilerplate is not a working arrangement ------------------------------

test("company boilerplate about being a hybrid team does not disqualify a remote role", () => {
  // Wealthsimple ends every posting with this sentence. On a bare \bhybrid\b
  // match it disqualified all 37 of their genuinely remote-in-Canada roles.
  const r = classifyRemote(
    job(
      "Remote (Canada)",
      "🌎 We are a hybrid team with over 1,500 employees across North America. " +
        "The people are one of the best parts of working here."
    )
  );
  assert.equal(r.isHybrid, false);
  assert.equal(r.qualifies, true);
});

test("hybrid still counts when it describes the role itself", () => {
  for (const description of [
    "This is a hybrid role.",
    "We offer a hybrid working model for this position.",
    "The position is hybrid.",
    "Hybrid (3 days in office).",
  ]) {
    assert.equal(classifyRemote(job("Remote", description)).isHybrid, true, description);
  }
});

test("hybrid in the location field always counts", () => {
  // That field is the employer's structured statement of where the job is, so
  // the word there is never incidental.
  assert.equal(classifyRemote(job("Calgary, AB (Hybrid)", "A great opportunity.")).isHybrid, true);
});
