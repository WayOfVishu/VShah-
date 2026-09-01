import test from "node:test";
import assert from "node:assert/strict";
import { checkTraceability, tokenize } from "./traceabilityCheck.js";

// A miniature stand-in for resume/base-resume.md. Using a fixture rather than
// the user's real resume keeps the test runnable on a fresh checkout (the
// `resume/` directory is gitignored) — traceabilityCheck.threshold.test.js is
// the one that exercises the real file when it's present.
const BASE_RESUME = `# Jane Doe

## Experience

### Northwind Data — Toronto, ON
**Data Engineering Intern** | 05/2024 - 08/2024

- Built a modular ingestion framework in Python that consolidated per-source
  pipelines into one configurable system.
- Deployed 5 production ingestion pipelines with pagination, authentication,
  and incremental sync.
- Added retry handling for transient HTTP 500 errors and state management for
  sync resumption.

### Contoso Rail — Capstone
**Computer Vision Lead** | 09/2023 - 04/2024

- Engineered an edge inference solution using YOLOv8 to classify signals in
  real time on a Raspberry Pi 4.
- Reduced inference invocations by roughly 60% using frame-difference change
  detection as the trigger.

## Skills
- Languages: Python, SQL, JavaScript
- Cloud: Kubernetes, Docker, PostgreSQL
`;

// Every line here reorders/rephrases something above — the legitimate output
// the prompt in lib/promptBuild.js asks for.
const TRACEABLE_DRAFT = `# Jane Doe

## Experience

### Northwind Data — Toronto, ON
**Data Engineering Intern** | 05/2024 - 08/2024

- Engineered a modular Python ingestion framework, consolidating per-source
  pipelines into a single configurable system.
- Deployed 5 production ingestion pipelines covering pagination, authentication,
  and incremental sync.
- Built retry handling for transient HTTP 500 errors plus state management for
  sync resumption.

### Contoso Rail — Capstone
**Computer Vision Lead** | 09/2023 - 04/2024

- Deployed a YOLOv8 edge inference solution classifying signals in real time on
  a Raspberry Pi 4.
- Cut inference invocations roughly 60% with frame-difference change detection
  as the trigger.

## Skills
- Languages: Python, SQL, JavaScript
- Cloud: Kubernetes, Docker, PostgreSQL
`;

// Identical to the traceable draft except for one inserted line claiming
// experience that appears nowhere in the base resume — exactly the failure
// mode req. 23 exists to catch.
const FABRICATED_LINE =
  "- Led a team of twelve engineers migrating a Kafka streaming platform to Snowflake, cutting warehouse spend 45% annually.";

const FABRICATED_DRAFT = TRACEABLE_DRAFT.replace(
  "### Contoso Rail — Capstone",
  `${FABRICATED_LINE}\n\n### Contoso Rail — Capstone`
);

test("a fully traceable draft raises no flags (req. 23: no false alarms on legitimate rephrasing)", () => {
  const result = checkTraceability(TRACEABLE_DRAFT, BASE_RESUME);
  assert.ok(result.checked > 0, "expected some substantive lines to be scored");
  assert.deepEqual(
    result.flagged.map((f) => f.text),
    [],
    `unexpected flags: ${JSON.stringify(result.flagged, null, 2)}`
  );
  assert.equal(result.passed, true);
});

test("a deliberately fabricated line is flagged (req. 23)", () => {
  const result = checkTraceability(FABRICATED_DRAFT, BASE_RESUME);
  assert.equal(result.passed, false);
  assert.equal(result.flagged.length, 1, `expected exactly one flag, got ${JSON.stringify(result.flagged)}`);
  assert.ok(result.flagged[0].text.includes("Kafka streaming platform"));
});

test("the flag fires only on the fabricated line, not its neighbours (task 6.7)", () => {
  const clean = checkTraceability(TRACEABLE_DRAFT, BASE_RESUME);
  const dirty = checkTraceability(FABRICATED_DRAFT, BASE_RESUME);
  // The one extra flag is the only difference between the two drafts.
  assert.equal(dirty.flagged.length - clean.flagged.length, 1);
});

test("flagged lines carry a line number and score for the highlight view (§6)", () => {
  const { flagged, threshold } = checkTraceability(FABRICATED_DRAFT, BASE_RESUME);
  const f = flagged[0];
  assert.equal(typeof f.line, "number");
  assert.ok(f.line > 0);
  assert.ok(f.score < threshold, `score ${f.score} should be under threshold ${threshold}`);
  // `line` points at the physical line the claim's block starts on, so the
  // dashboard can scroll to it. The claim text itself is the unwrapped
  // sentence with its list marker stripped, not that raw line verbatim.
  const sourceLine = FABRICATED_DRAFT.split(/\r?\n/)[f.line - 1];
  assert.ok(sourceLine.includes("Kafka streaming platform"), `line ${f.line} was: ${sourceLine}`);
});

test("markdown scaffolding and short headings are not scored as claims", () => {
  const result = checkTraceability("# Jane Doe\n\n## Skills\n\n---\n", BASE_RESUME);
  assert.equal(result.checked, 0);
  assert.equal(result.passed, true);
});

test("tokenize keeps technical tokens intact and stems only ordinary words", () => {
  const tokens = tokenize("Deployed Node.js and CI/CD on K8s with 100K+ records");
  // Technical tokens must survive verbatim — they carry the strongest
  // traceability signal, and stemming "node.js" to "node.j" is junk.
  for (const expected of ["node.js", "ci/cd", "k8s", "100k+"]) {
    assert.ok(tokens.includes(expected), `expected token "${expected}" in ${JSON.stringify(tokens)}`);
  }
  // Ordinary words are stemmed so "deployed"/"deploy" are the same evidence.
  assert.ok(tokens.includes("deploy"));
  assert.ok(tokens.includes("record"));
  // Stopwords carry no signal and must not inflate a fabricated line's score.
  assert.ok(!tokens.includes("and"));
  assert.ok(!tokens.includes("with"));
});

test("stemming matches inflected forms across draft and base resume", () => {
  // The pair that caused a false flag before stemming was added.
  assert.deepEqual(tokenize("triggering"), tokenize("triggered"));
  assert.deepEqual(tokenize("pipelines"), tokenize("pipeline"));
});

test("an empty draft passes rather than throwing", () => {
  const result = checkTraceability("", BASE_RESUME);
  assert.equal(result.checked, 0);
  assert.equal(result.passed, true);
});

// --- The numeric-support rule (req. 23 names dates and metrics explicitly) ---
// Token overlap alone is blind to this: a line built entirely from the base
// resume's own vocabulary with one number changed scores ~1.0.

test("an inflated metric is flagged even though the wording is fully traceable", () => {
  const line = "- Deployed 47 production ingestion pipelines with pagination, authentication, and incremental sync.";
  const { lines } = checkTraceability(line, BASE_RESUME);
  assert.equal(lines.length, 1);
  assert.ok(lines[0].score > 0.8, `overlap alone would have passed this line (score ${lines[0].score})`);
  assert.equal(lines[0].flagged, true);
  assert.deepEqual(lines[0].reasons, ["unsupported-number"]);
  assert.ok(lines[0].unsupportedNumbers.includes("47"));
});

test("a metric that matches the base resume is not flagged", () => {
  const line = "- Deployed 5 production ingestion pipelines with pagination, authentication, and incremental sync.";
  const { lines } = checkTraceability(line, BASE_RESUME);
  assert.equal(lines[0].flagged, false, JSON.stringify(lines[0]));
});

test("a percentage is matched regardless of formatting", () => {
  // Base resume says "roughly 60%"; the draft writing it as "60 %" is the same claim.
  const { lines } = checkTraceability(
    "- Cut inference invocations by 60 % using frame-difference change detection as the trigger.",
    BASE_RESUME
  );
  assert.deepEqual(lines[0].unsupportedNumbers, []);
  assert.equal(lines[0].flagged, false);
});

test("both rules can fire on the same line and both are reported", () => {
  const line = "- Directed a 30-person Kafka platform migration to Snowflake across three continents.";
  const { lines } = checkTraceability(line, BASE_RESUME);
  assert.deepEqual(lines[0].reasons.sort(), ["low-overlap", "unsupported-number"]);
});

test("morphology differences do not cause a false flag (trigger vs triggering)", () => {
  const { lines } = checkTraceability(
    "- Reduced inference invocations by triggering on frame-difference change detection instead of every frame.",
    BASE_RESUME
  );
  assert.equal(lines[0].flagged, false, `false positive: ${JSON.stringify(lines[0])}`);
});

// --- Claim-level segmentation --------------------------------------------
// Found by running the checker against a real generated draft: Markdown
// hard-wraps a paragraph across physical lines, so scoring raw lines flags
// fragments ("deployed on Kubernetes. Comfortable taking an...") while
// letting a fabricated clause hide inside an otherwise-traceable line.

test("a hard-wrapped but traceable paragraph is not flagged as fragments", () => {
  const wrapped = [
    "Built a modular ingestion framework in Python that consolidated",
    "per-source pipelines into one configurable system, and deployed 5",
    "production ingestion pipelines with pagination and incremental sync.",
  ].join("\n");
  const { flagged } = checkTraceability(wrapped, BASE_RESUME);
  assert.deepEqual(flagged, [], `wrap fragments were flagged: ${JSON.stringify(flagged, null, 2)}`);
});

test("a fabricated sentence is isolated rather than diluted by a true one beside it", () => {
  const draft =
    "- Deployed 5 production ingestion pipelines with pagination and incremental sync.\n" +
    "  Also served as CTO of a Series B fintech startup for six years.\n";
  const { flagged } = checkTraceability(draft, BASE_RESUME);
  assert.equal(flagged.length, 1, JSON.stringify(flagged, null, 2));
  assert.match(flagged[0].text, /^Also served as CTO/);
  // The true half of the same bullet must not be dragged down with it.
  assert.ok(flagged[0].score < 0.3, `expected a decisive score, got ${flagged[0].score}`);
});

test("a flagged claim reports the line its block starts on", () => {
  const draft = "# Resume\n\n## Summary\n\nBuilt Python pipelines.\nAlso won an Olympic gold medal in the decathlon.\n";
  const { flagged } = checkTraceability(draft, BASE_RESUME);
  assert.equal(flagged.length, 1);
  // Both sentences belong to the paragraph block starting on line 5.
  assert.equal(flagged[0].line, 5);
});

test("sentence splitting does not break on technical periods", () => {
  const draft = "- Shipped Node.js services and 5.5% faster queries using e.g. indexing on Python pipelines.\n";
  const { lines } = checkTraceability(draft, BASE_RESUME);
  assert.equal(lines.length, 1, `split into fragments: ${JSON.stringify(lines.map((l) => l.text))}`);
});
