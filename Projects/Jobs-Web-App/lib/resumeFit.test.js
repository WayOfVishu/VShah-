import { test } from "node:test";
import assert from "node:assert/strict";
import { findSkills, profileFromText, resumeFit } from "./resumeFit.js";
import { scoreJob } from "./scoring.js";
import { DEFAULT_PREFERENCES } from "./preferences.js";

// A miniature stand-in for resume/base-resume.md — the real one is git-ignored.
const RESUME = `
## Skills
**Data:** ETL/ELT, Airflow, Databricks, Delta Lake, dbt
**ML:** OpenCV, YOLOv8, TensorFlow, scikit-learn
**Cloud:** Kubernetes, Docker, Azure DevOps (CI/CD)
**Languages:** Python, TypeScript, SQL, JavaScript
- Built REST/OData integrations and Unit/Service-Level Testing
`;
const profile = profileFromText(RESUME);

// --- skill matching --------------------------------------------------------

test("reads the resume's skills, including ones only mentioned in passing", () => {
  for (const skill of ["Python", "SQL", "Databricks", "Delta Lake", "YOLO", "scikit-learn", "Kubernetes", "CI/CD", "REST APIs", "Unit testing"]) {
    assert.ok(profile.skills.has(skill), `expected ${skill}`);
  }
});

test("token boundaries: Java is not JavaScript, and NoSQL is not SQL", () => {
  assert.deepEqual(findSkills("Strong JavaScript skills"), ["JavaScript"]);
  assert.deepEqual(findSkills("Experience with Java/Kotlin"), ["Java", "Kotlin"]);
  assert.deepEqual(findSkills("MongoDB or another NoSQL store"), ["MongoDB", "NoSQL"]);
});

test("punctuation-edged skills: C++, C#, .NET", () => {
  assert.deepEqual(findSkills("C++ and C#"), ["C++", "C# / .NET"]);
  assert.deepEqual(findSkills("services on .NET 8"), ["C# / .NET"]);
});

test("ambiguous words only count capitalized", () => {
  assert.deepEqual(findSkills("we go the extra mile, the rest of the team will spark ideas"), []);
  assert.deepEqual(findSkills("Services in Go, Spark jobs, REST endpoints"), ["Go", "Spark", "REST APIs"]);
  assert.deepEqual(findSkills("our go-to-market team"), []);
});

test("a space in a skill also matches a hyphen", () => {
  assert.deepEqual(findSkills("Delta-Lake tables and retrieval-augmented generation"), ["Delta Lake", "RAG"]);
});

// --- the fit score ---------------------------------------------------------

test("a posting that names no known skill has no fit, not a zero", () => {
  const fit = resumeFit({ title: "Engineer", description: "Join a great team." }, profile);
  assert.equal(fit.score, null);
});

test("no resume, no fit", () => {
  assert.equal(resumeFit({ title: "Python developer" }, null).score, null);
});

test("fit reports what you have and what the posting also wants", () => {
  const fit = resumeFit({ title: "Data Engineer", description: "Python, SQL, Airflow, Spark and AWS." }, profile);
  assert.deepEqual(fit.have, ["Python", "SQL", "Airflow"]);
  assert.deepEqual(fit.missing, ["Spark", "AWS"]);
});

test("a close match outscores a poor one", () => {
  const close = resumeFit({ description: "Python, SQL, Databricks, dbt, Airflow, Kubernetes" }, profile).score;
  const poor = resumeFit({ description: "Java, Scala, Spring Boot, AWS, Terraform, Kotlin" }, profile).score;
  assert.ok(close > 0.7, `close was ${close}`);
  assert.ok(poor < 0.2, `poor was ${poor}`);
});

test("a long kitchen-sink posting where you have many of the asks still scores well", () => {
  const description =
    "Python SQL Databricks dbt Airflow Kubernetes Docker TensorFlow OpenCV TypeScript JavaScript " +
    "Java Scala Go AWS GCP Terraform Kafka Snowflake Redis GraphQL Rust";
  const fit = resumeFit({ description: description.replace("Go", "golang") }, profile);
  assert.ok(fit.have.length >= 11);
  assert.ok(fit.score > 0.6, `kitchen sink was ${fit.score}`);
});

test("one missing skill on a thin posting doesn't sink it to zero", () => {
  const fit = resumeFit({ description: "Some Java." }, profile);
  assert.ok(fit.score > 0.1 && fit.score < 0.3, `thin miss was ${fit.score}`);
});

// --- blended into match_score ----------------------------------------------

const job = { title: "Data Engineer", location: "Calgary, AB", description: "Python, SQL, Airflow, Databricks." };

test("resume fit is off unless resumeWeight is set", () => {
  const scored = scoreJob(job, { ...DEFAULT_PREFERENCES }, profile);
  assert.equal(scored.resumeScore, null);
  assert.equal(scored.matchScore, Number((0.65 * scored.locationScore + 0.35 * scored.keywordScore).toFixed(4)));
});

test("with a weight, match_score is (1 - w) preference + w fit", () => {
  const prefs = { ...DEFAULT_PREFERENCES, resumeWeight: 0.25 };
  const scored = scoreJob(job, prefs, profile);
  const preference = 0.65 * scored.locationScore + 0.35 * scored.keywordScore;
  assert.ok(scored.resumeScore > 0);
  assert.equal(scored.matchScore, Number((0.75 * preference + 0.25 * scored.resumeScore).toFixed(4)));
  assert.deepEqual(scored.resumeSkills.have, ["Python", "SQL", "Airflow", "Databricks"]);
});

test("preferences stay primary: a perfect fit can't lift an off-preference posting past an on-preference one", () => {
  const prefs = { ...DEFAULT_PREFERENCES, resumeWeight: 0.25 };
  const wanted = scoreJob({ title: "Software Engineer", location: "Calgary, AB", description: "Java and AWS." }, prefs, profile);
  const unwanted = scoreJob(
    { title: "Software Engineer", location: "Vancouver, BC", description: "Python, SQL, Databricks, dbt, Airflow, Kubernetes, Docker." },
    prefs,
    profile
  );
  assert.ok(wanted.matchScore > unwanted.matchScore);
});

test("a posting with no recognizable skills keeps its preference score", () => {
  const prefs = { ...DEFAULT_PREFERENCES, resumeWeight: 0.25 };
  const scored = scoreJob({ title: "Software Engineer", location: "Calgary, AB", description: "Great team." }, prefs, profile);
  assert.equal(scored.resumeScore, null);
  assert.equal(scored.matchScore, Number((0.65 * scored.locationScore + 0.35 * scored.keywordScore).toFixed(4)));
});
