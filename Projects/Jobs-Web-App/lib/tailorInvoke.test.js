import test from "node:test";
import assert from "node:assert/strict";
import Database from "better-sqlite3";
import { mkdtempSync, writeFileSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { tailorJob } from "./tailorInvoke.js";
import { transition, canTransition, TransitionError } from "./statusMachine.js";

const BASE_RESUME = `# Jane Doe

## Experience
- Built a modular ingestion framework in Python that consolidated per-source
  pipelines into one configurable system.
- Deployed 5 production ingestion pipelines with pagination and incremental sync.
`;

function freshDb() {
  const db = new Database(":memory:");
  db.exec(`
    CREATE TABLE discovered_jobs (
      id             INTEGER PRIMARY KEY AUTOINCREMENT,
      job_id         TEXT NOT NULL,
      sources        TEXT NOT NULL,
      title          TEXT NOT NULL,
      company        TEXT NOT NULL,
      location       TEXT,
      salary         TEXT,
      description    TEXT,
      apply_url      TEXT NOT NULL,
      posted_date    TEXT,
      remote_status  TEXT,
      first_seen_at  TEXT NOT NULL DEFAULT (datetime('now')),
      status         TEXT NOT NULL DEFAULT 'new',
      resume_path    TEXT,
      match_score    REAL,
      applied_job_id INTEGER,
      tailor_error   TEXT
    )
  `);
  return db;
}

function seedJob(db, status = "queued") {
  const info = db
    .prepare(
      `INSERT INTO discovered_jobs (job_id, sources, title, company, description, apply_url, status)
       VALUES ('x1', '["ashby"]', 'Data Engineer', 'Northwind', 'Build ingestion pipelines in Python.', 'https://example.test/x1', ?)`
    )
    .run(status);
  return info.lastInsertRowid;
}

function sandbox() {
  const dir = mkdtempSync(path.join(tmpdir(), "tailor-test-"));
  const resumePath = path.join(dir, "base-resume.md");
  writeFileSync(resumePath, BASE_RESUME);
  return { dir, resumePath, draftsDir: path.join(dir, "drafts") };
}

// --- The gate itself (req. 20-21, PRD §8) -----------------------------------

test("a job that is not queued cannot be tailored — the gate is enforced, not assumed", async () => {
  const db = freshDb();
  const box = sandbox();
  for (const status of ["new", "rejected", "dismissed", "archived", "tailored"]) {
    const id = seedJob(db, status);
    await assert.rejects(
      () => tailorJob(db, id, { baseResumePath: box.resumePath, draftsDir: box.draftsDir }),
      (err) => err.statusCode === 409 && /only a queued job/.test(err.message),
      `status "${status}" should not be tailorable`
    );
    assert.equal(db.prepare("SELECT status FROM discovered_jobs WHERE id = ?").get(id).status, status);
  }
  rmSync(box.dir, { recursive: true, force: true });
});

test("no dashboard-reachable path transitions straight to tailored (PRD §8)", () => {
  // The only edge into `tailored` is from `generating`, which only
  // tailorInvoke.js enters — so discovery can never produce a tailored resume.
  for (const from of ["new", "queued", "rejected", "dismissed", "applied", "archived"]) {
    assert.equal(canTransition(from, "tailored"), false, `${from} -> tailored must be illegal`);
  }
  assert.equal(canTransition("generating", "tailored"), true);
});

// --- Success path (req. 26) --------------------------------------------------

test("a successful run writes the draft, sets resume_path, and moves to tailored (req. 26)", async () => {
  const db = freshDb();
  const box = sandbox();
  const id = seedJob(db);

  const result = await tailorJob(db, id, {
    baseResumePath: box.resumePath,
    draftsDir: box.draftsDir,
    // Stands in for Claude writing the file itself via the scoped Write tool.
    runner: async (prompt, { outputPath }) => {
      writeFileSync(
        outputPath,
        "# Jane Doe\n\n- Engineered a modular Python ingestion framework consolidating per-source pipelines into one configurable system.\n"
      );
      return { code: 0, stdout: "done", stderr: "", timedOut: false };
    },
  });

  assert.equal(result.ok, true);
  assert.equal(result.job.status, "tailored");
  assert.equal(result.job.resume_path, result.draftPath);
  assert.equal(result.job.tailor_error, null);
  assert.ok(existsSync(result.draftPath));
  // req. 26: the filename traces back to the posting.
  assert.match(path.basename(result.draftPath), /^northwind-data-engineer-\d+\.md$/);
  assert.equal(result.traceability.passed, true);
  rmSync(box.dir, { recursive: true, force: true });
});

test("stdout is persisted when Claude answers in text instead of writing the file", async () => {
  const db = freshDb();
  const box = sandbox();
  const id = seedJob(db);

  const result = await tailorJob(db, id, {
    baseResumePath: box.resumePath,
    draftsDir: box.draftsDir,
    runner: async () => ({
      code: 0,
      stdout: "Here you go:\n```markdown\n# Jane Doe\n\n- Deployed 5 production ingestion pipelines with pagination and incremental sync.\n```",
      stderr: "",
      timedOut: false,
    }),
  });

  assert.equal(result.ok, true);
  assert.equal(result.job.status, "tailored");
  const draft = (await import("node:fs")).readFileSync(result.draftPath, "utf8");
  assert.ok(draft.startsWith("# Jane Doe"), "the fence and preamble should be stripped");
  assert.ok(!draft.includes("```"));
  rmSync(box.dir, { recursive: true, force: true });
});

test("traceability flags are returned but do not block the transition (req. 23)", async () => {
  const db = freshDb();
  const box = sandbox();
  const id = seedJob(db);

  const result = await tailorJob(db, id, {
    baseResumePath: box.resumePath,
    draftsDir: box.draftsDir,
    runner: async (prompt, { outputPath }) => {
      writeFileSync(
        outputPath,
        "# Jane Doe\n\n- Led a team of twelve engineers migrating a Kafka streaming platform to Snowflake across three continents.\n"
      );
      return { code: 0, stdout: "", stderr: "", timedOut: false };
    },
  });

  assert.equal(result.ok, true);
  assert.equal(result.job.status, "tailored", "a flagged line must not silently block generation");
  assert.equal(result.traceability.passed, false);
  assert.equal(result.traceability.flagged.length, 1);
});

// --- Failure paths (req. 28) -------------------------------------------------

test("a non-zero exit falls back to queued with a visible error, never to new (req. 28)", async () => {
  const db = freshDb();
  const box = sandbox();
  const id = seedJob(db);

  const result = await tailorJob(db, id, {
    baseResumePath: box.resumePath,
    draftsDir: box.draftsDir,
    runner: async () => ({ code: 1, stdout: "", stderr: "usage limit reached", timedOut: false }),
  });

  assert.equal(result.ok, false);
  assert.equal(result.job.status, "queued");
  assert.match(result.job.tailor_error, /usage limit reached/);
  assert.equal(result.job.resume_path, null);
});

test("a timeout falls back to queued with a visible error (req. 28)", async () => {
  const db = freshDb();
  const box = sandbox();
  const id = seedJob(db);

  const result = await tailorJob(db, id, {
    baseResumePath: box.resumePath,
    draftsDir: box.draftsDir,
    runner: async () => ({ code: null, stdout: "", stderr: "", timedOut: true }),
  });

  assert.equal(result.job.status, "queued");
  assert.match(result.job.tailor_error, /timed out/i);
});

test("a run that produces nothing usable falls back to queued (req. 28)", async () => {
  const db = freshDb();
  const box = sandbox();
  const id = seedJob(db);

  const result = await tailorJob(db, id, {
    baseResumePath: box.resumePath,
    draftsDir: box.draftsDir,
    runner: async () => ({ code: 0, stdout: "   ", stderr: "", timedOut: false }),
  });

  assert.equal(result.job.status, "queued");
  assert.match(result.job.tailor_error, /no draft file and no usable Markdown/);
});

test("a spawn error leaves the row queued rather than stuck in generating (req. 28)", async () => {
  const db = freshDb();
  const box = sandbox();
  const id = seedJob(db);

  const result = await tailorJob(db, id, {
    baseResumePath: box.resumePath,
    draftsDir: box.draftsDir,
    runner: async () => {
      throw new Error("spawn ENOENT");
    },
  });

  assert.equal(result.job.status, "queued");
  assert.match(result.job.tailor_error, /ENOENT/);
});

test("a retry after a failure clears the previous error", async () => {
  const db = freshDb();
  const box = sandbox();
  const id = seedJob(db);

  await tailorJob(db, id, {
    baseResumePath: box.resumePath,
    draftsDir: box.draftsDir,
    runner: async () => ({ code: 1, stdout: "", stderr: "transient", timedOut: false }),
  });
  assert.match(db.prepare("SELECT tailor_error FROM discovered_jobs WHERE id = ?").get(id).tailor_error, /transient/);

  const retry = await tailorJob(db, id, {
    baseResumePath: box.resumePath,
    draftsDir: box.draftsDir,
    runner: async (prompt, { outputPath }) => {
      writeFileSync(outputPath, "# Jane Doe\n\n- Deployed 5 production ingestion pipelines with pagination and incremental sync.\n");
      return { code: 0, stdout: "", stderr: "", timedOut: false };
    },
  });

  assert.equal(retry.ok, true);
  assert.equal(retry.job.status, "tailored");
  assert.equal(retry.job.tailor_error, null);
  rmSync(box.dir, { recursive: true, force: true });
});

// --- Status machine guard rails ---------------------------------------------

test("an illegal transition throws rather than silently writing the status", () => {
  const db = freshDb();
  const id = seedJob(db, "applied");
  assert.throws(() => transition(db, id, "queued"), TransitionError);
  assert.equal(db.prepare("SELECT status FROM discovered_jobs WHERE id = ?").get(id).status, "applied");
});

test("rejected is terminal except for an explicit manual reset (req. 21)", () => {
  assert.equal(canTransition("rejected", "generating"), false);
  assert.equal(canTransition("rejected", "queued"), false);
  assert.equal(canTransition("rejected", "new"), true);
});

test("mark-applied is reachable without tailoring first (req. 32)", () => {
  // req. 32 lists mark-applied as a plain row action alongside reject and
  // dismiss — the user may apply to a posting without ever requesting a
  // tailored resume, and must not be forced through the tailoring flow to
  // log that.
  assert.equal(canTransition("new", "applied"), true);
  assert.equal(canTransition("queued", "applied"), true);
  assert.equal(canTransition("tailored", "applied"), true);
  // Still not reachable from a terminal or set-aside state without a reset.
  assert.equal(canTransition("rejected", "applied"), false);
  assert.equal(canTransition("dismissed", "applied"), false);
});
