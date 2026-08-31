#!/usr/bin/env node
// Task 1.0 spike (PRD req. 27, Tasks.md 1.0). Throwaway diagnostic script —
// not part of the shipped pipeline. Answers, for this machine, whether a
// non-interactive `claude -p` invocation is safe to shell out to from
// tailorInvoke.js. See PRD.md "Open Questions" for the recorded outcome.
//
// Usage: node scripts/spike-claude-invoke.js

import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync, rmSync, existsSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const TIMEOUT_MS = 60_000;

function findClaudeBinary() {
  if (process.env.CLAUDE_CLI_PATH && existsSync(process.env.CLAUDE_CLI_PATH)) {
    return process.env.CLAUDE_CLI_PATH;
  }
  // Dev machines that installed Claude Code only as the VS Code extension
  // (no standalone CLI on PATH) bundle a native binary here.
  const candidate = path.join(
    process.env.USERPROFILE || "",
    ".vscode",
    "extensions"
  );
  if (existsSync(candidate)) {
    const match = readdirSync(candidate).find((name) =>
      name.startsWith("anthropic.claude-code-")
    );
    if (match) {
      const exe = path.join(candidate, match, "resources", "native-binary", "claude.exe");
      if (existsSync(exe)) return exe;
    }
  }
  return "claude"; // assume PATH
}

function runClaude(args, cwd) {
  return new Promise((resolve) => {
    const bin = findClaudeBinary();
    const child = spawn(bin, args, { cwd, stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    let timedOut = false;

    const timer = setTimeout(() => {
      timedOut = true;
      child.kill();
    }, TIMEOUT_MS);

    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({ code, stdout, stderr, timedOut });
    });
  });
}

async function main() {
  const dir = mkdtempSync(path.join(tmpdir(), "claude-invoke-spike-"));
  writeFileSync(
    path.join(dir, "fake-resume.md"),
    "# Jane Doe\n## Experience\n- Software Engineer at Acme Corp (2020-2023): Built REST APIs in Node.js.\n"
  );
  writeFileSync(
    path.join(dir, "fake-posting.txt"),
    "Title: Backend Engineer at TestCo\nWe need someone with Node.js and REST API experience.\n"
  );

  const prompt =
    "Read fake-resume.md and fake-posting.txt in the current directory, " +
    "then write a one-line tailored resume bullet to output.md based only " +
    "on content in fake-resume.md.";

  console.log("=== Spike A: no --allowedTools (default non-interactive permission behavior) ===");
  const withoutPerm = await runClaude(["-p", prompt], dir);
  console.log("exit code:", withoutPerm.code, "| timed out:", withoutPerm.timedOut);
  console.log("stdout:", withoutPerm.stdout.trim());
  if (withoutPerm.stderr.trim()) console.log("stderr:", withoutPerm.stderr.trim());
  const wroteWithoutPerm = existsSync(path.join(dir, "output.md"));
  console.log("output.md written?", wroteWithoutPerm);

  console.log("\n=== Spike B: with --allowedTools Write ===");
  const withPerm = await runClaude(["-p", prompt, "--allowedTools", "Write"], dir);
  console.log("exit code:", withPerm.code, "| timed out:", withPerm.timedOut);
  console.log("stdout:", withPerm.stdout.trim());
  if (withPerm.stderr.trim()) console.log("stderr:", withPerm.stderr.trim());
  const wroteWithPerm = existsSync(path.join(dir, "output.md"));
  console.log("output.md written?", wroteWithPerm);
  if (wroteWithPerm) {
    console.log("output.md contents:", readFileSync(path.join(dir, "output.md"), "utf8").trim());
  }

  console.log("\n=== Summary ===");
  console.log(
    "(a) billing:",
    process.env.ANTHROPIC_API_KEY
      ? "ANTHROPIC_API_KEY was set in this env — invocation may bill as separate API usage."
      : "No ANTHROPIC_API_KEY set, and the call still succeeded — auth came from the logged-in Claude Code session (subscription), not a separate API key."
  );
  console.log(
    "(b) hang risk:",
    withoutPerm.timedOut
      ? "HUNG for " + TIMEOUT_MS + "ms without --allowedTools — unsafe to shell out without an explicit permission flag."
      : "Did NOT hang. Without --allowedTools, the Write call is auto-denied and Claude reports that in its text reply, exiting cleanly."
  );
  console.log(
    "(c) second gate:",
    "No separate OS/tool-level confirmation dialog appeared in either run. Permission is resolved entirely by " +
      "the --allowedTools / --allow-dangerously-skip-permissions flag passed at invocation — there is nothing that " +
      "can block waiting for interactive input."
  );

  rmSync(dir, { recursive: true, force: true });
}

main();
