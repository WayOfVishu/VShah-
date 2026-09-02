// PRD req. 21, 26-28: the `queued -> generating -> tailored` transition.
//
// Task 1.0's spike answered GO for the first branch of req. 27: shell out to
// `claude -p` directly. The recorded outcome (PRD §9) is that permission is
// resolved entirely by the `--allowedTools` flag at invocation time — there is
// no second, tool-level gate that could block a script — so req. 22's approval
// gate is the single in-app confirmation the caller must have already taken.
//
// This module never decides *whether* to generate. It refuses to run on a row
// that isn't already `queued`, which is what makes "no tailored resume without
// an explicit confirmation" (PRD §8) a property of the code and not a habit.

import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, readFileSync, existsSync, readdirSync } from "node:fs";
import path from "node:path";
import { buildTailoringPrompt } from "./promptBuild.js";
import { checkTraceability } from "./traceabilityCheck.js";
import { transition } from "./statusMachine.js";

const DEFAULT_TIMEOUT_MS = 300_000; // 5 min: a full resume is a slower call than the spike's one-liner

// Same resolution order as scripts/spike-claude-invoke.js — this machine has
// Claude Code as a VS Code extension rather than a standalone CLI on PATH.
export function findClaudeBinary() {
  if (process.env.CLAUDE_CLI_PATH && existsSync(process.env.CLAUDE_CLI_PATH)) {
    return process.env.CLAUDE_CLI_PATH;
  }
  const extensionsDir = path.join(process.env.USERPROFILE || "", ".vscode", "extensions");
  if (existsSync(extensionsDir)) {
    const match = readdirSync(extensionsDir).find((name) => name.startsWith("anthropic.claude-code-"));
    if (match) {
      const exe = path.join(extensionsDir, match, "resources", "native-binary", "claude.exe");
      if (existsSync(exe)) return exe;
    }
  }
  return "claude";
}

function runClaude(prompt, { cwd, draftsDir, timeoutMs }) {
  return new Promise((resolve) => {
    const args = [
      "-p",
      prompt,
      // Scoped exactly as PRD §9 records: write access, and only into the
      // drafts directory. Never --allow-dangerously-skip-permissions.
      "--allowedTools",
      "Write",
      "--add-dir",
      draftsDir,
    ];
    const child = spawn(findClaudeBinary(), args, { cwd, stdio: ["ignore", "pipe", "pipe"] });

    let stdout = "";
    let stderr = "";
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill();
    }, timeoutMs);

    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    child.on("error", (err) => {
      clearTimeout(timer);
      resolve({ code: -1, stdout, stderr: `${stderr}\n${err.message}`, timedOut });
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({ code, stdout, stderr, timedOut });
    });
  });
}

// Claude sometimes answers with the Markdown wrapped in a fence plus a line of
// preamble, despite the prompt asking for bare Markdown. Only used on the
// stdout fallback path (when the Write tool didn't produce the file).
function extractMarkdown(stdout) {
  const fenced = stdout.match(/```(?:markdown|md)?\n([\s\S]*?)```/);
  const text = (fenced ? fenced[1] : stdout).trim();
  return text;
}

/**
 * Runs the tailoring for one discovered_jobs row.
 *
 * Preconditions: the row is `queued` and the user has confirmed (req. 22).
 * On success the row is `tailored` with `resume_path` set (req. 26).
 * On any failure the row goes back to `queued` with a visible `tailor_error`
 * — never silently to `new` and never left stuck in `generating` (req. 28).
 *
 * Returns { ok, job, draftPath, traceability, stdout, error }.
 */
export async function tailorJob(db, id, opts = {}) {
  const job = db.prepare("SELECT * FROM discovered_jobs WHERE id = ?").get(id);
  if (!job) {
    const err = new Error(`Discovered job ${id} not found`);
    err.statusCode = 404;
    throw err;
  }
  // The gate, enforced rather than assumed: anything not already `queued`
  // cannot reach `generating`, so no discovery run or stray call can produce a
  // tailored resume (PRD §8's success metric).
  if (job.status !== "queued") {
    const err = new Error(
      `Job ${id} is "${job.status}"; only a queued job can be tailored (req. 20-21).`
    );
    err.statusCode = 409;
    throw err;
  }

  const built = buildTailoringPrompt(job, opts);
  const draftsDir = built.draftsDir;
  mkdirSync(draftsDir, { recursive: true });

  transition(db, id, "generating", { tailor_error: null });

  // `opts.runner` is the seam the tests use to exercise the req. 28 failure
  // paths without spending a real Claude Code call on each one.
  const runner = opts.runner || runClaude;

  let result;
  try {
    result = await runner(built.prompt, {
      cwd: opts.cwd || path.dirname(draftsDir),
      draftsDir,
      outputPath: built.outputPath,
      timeoutMs: opts.timeoutMs || DEFAULT_TIMEOUT_MS,
    });
  } catch (err) {
    // Spawn itself blew up (binary missing, EPERM). Same fallback as any
    // other failure — the row must not be left in `generating`.
    result = { code: -1, stdout: "", stderr: err.message, timedOut: false };
  }

  const fail = (message) => {
    transition(db, id, "queued", { tailor_error: message });
    return {
      ok: false,
      job: db.prepare("SELECT * FROM discovered_jobs WHERE id = ?").get(id),
      error: message,
      sanitization: built.sanitization,
      stdout: result.stdout,
    };
  };

  if (result.timedOut) {
    return fail(`Claude Code timed out after ${(opts.timeoutMs || DEFAULT_TIMEOUT_MS) / 1000}s.`);
  }
  if (result.code !== 0) {
    return fail(
      `Claude Code exited ${result.code}. ${(result.stderr || result.stdout || "").trim().slice(0, 500)}`
    );
  }

  // Preferred path: Claude wrote the file itself via the scoped Write tool.
  // Fallback: it answered in stdout instead, so persist that — either way the
  // draft ends up at the one path req. 26 specifies.
  if (!existsSync(built.outputPath)) {
    const markdown = extractMarkdown(result.stdout);
    if (!markdown) {
      return fail("Claude Code produced no draft file and no usable Markdown output.");
    }
    writeFileSync(built.outputPath, `${markdown}\n`, "utf8");
  }

  const draft = readFileSync(built.outputPath, "utf8");
  if (!draft.trim()) return fail("The generated draft was empty.");

  // req. 23: the check runs on every generation. Flags do NOT block the
  // transition — the PRD is explicit that a flagged line is "not silently
  // accepted, and not silently blocked either." The user resolves them in the
  // approval view, overriding with a logged reason if they disagree.
  const traceability = checkTraceability(draft, built.baseResume, {
    threshold: opts.threshold,
  });

  const updated = transition(db, id, "tailored", {
    resume_path: built.outputPath,
    tailor_error: null,
  });

  // `sanitization` rides along because the caller no longer sees it in a
  // preview step — req. 24's "the posting was scrubbed" signal has to reach the
  // user somewhere, and this is now the only place it can come from.
  return {
    ok: true,
    job: updated,
    draftPath: built.outputPath,
    traceability,
    sanitization: built.sanitization,
    stdout: result.stdout,
  };
}
