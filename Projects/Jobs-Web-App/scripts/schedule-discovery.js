#!/usr/bin/env node
// Installs the Windows scheduled task that runs discovery once a day, whether
// or not the dashboard is open.
//
//   npm run schedule                                 daily at 18:00 (local time)
//   npm run schedule:status                          when it last ran, and how it went
//   npm run unschedule                               remove it
//   node scripts/schedule-discovery.js --at 07:30    a different time (24-hour)
//   node scripts/schedule-discovery.js --run         install, then start one run now
//
// The flags are shown on `node` rather than as `npm run schedule -- --at`
// because Windows PowerShell eats the `--` before npm sees it, and npm then
// swallows the flag.
//
// Re-running it replaces the task, so it is also how to change the time — and
// how to repoint it after moving the project or upgrading Node, since the task
// stores absolute paths to both. Run it from an administrator terminal to get
// the run-while-logged-out mode; otherwise it falls back to run-while-logged-in.
//
// Each run's output lands in logs/ (see scripts/scheduled-run.js).

import { execFileSync } from "node:child_process";
import { writeFileSync, unlinkSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { TASK_NAME, buildTaskXml, parseTime } from "../lib/scheduledTask.js";

const APP_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const RUNNER = path.join(APP_DIR, "scripts", "scheduled-run.js");

const argv = process.argv.slice(2);
const flag = (name) => argv.includes(name);
const option = (name) => {
  const i = argv.indexOf(name);
  return i >= 0 ? argv[i + 1] : undefined;
};

function schtasks(args) {
  return execFileSync("schtasks.exe", args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
}

const errorText = (err) => String(err.stderr || err.message).trim();

function status() {
  let out;
  try {
    out = schtasks(["/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST"]);
  } catch {
    console.log(`No "${TASK_NAME}" task is installed. Install it with: npm run schedule`);
    process.exitCode = 1;
    return;
  }
  const wanted = ["Status", "Next Run Time", "Last Run Time", "Last Result", "Logon Mode", "Run As User"];
  for (const line of out.split(/\r?\n/)) {
    if (wanted.some((w) => line.startsWith(`${w}:`))) console.log(`  ${line.trim()}`);
  }
  console.log(`  Logs: ${path.join(APP_DIR, "logs")}`);
}

function register(logonType, time) {
  // S4U runs with no window at all. InteractiveToken would open a console for
  // the length of the run, so it goes through conhost's headless mode instead.
  const quoted = `"${process.execPath}" "${RUNNER}"`;
  const action =
    logonType === "S4U"
      ? { command: process.execPath, args: `"${RUNNER}"` }
      : { command: path.join(process.env.SystemRoot || "C:\\Windows", "System32", "conhost.exe"), args: `--headless ${quoted}` };

  const xml = buildTaskXml({
    ...action,
    workingDir: APP_DIR,
    time,
    userId: `${process.env.USERDOMAIN}\\${process.env.USERNAME}`,
    logonType,
  });

  // schtasks only reliably accepts task XML as UTF-16 with a byte-order mark.
  const file = path.join(os.tmpdir(), `jobs-web-app-task-${process.pid}.xml`);
  writeFileSync(file, Buffer.from(`\ufeff${xml}`, "utf16le"));
  try {
    schtasks(["/Create", "/TN", TASK_NAME, "/XML", file, "/F"]);
  } finally {
    unlinkSync(file);
  }
}

function install() {
  // Evening rather than morning: by 18:00 Calgary time the day's postings are
  // up across every North American time zone, so one run catches all of them
  // and they're waiting when you sit down, still under 24 hours old.
  const time = option("--at") || "18:00";
  parseTime(time); // fail on a bad --at before touching anything

  let mode = "S4U";
  try {
    register("S4U", time);
  } catch (s4uErr) {
    // Registering a run-while-logged-out task needs the "log on as a batch job"
    // right, which a non-admin session may not be able to grant. Fall back to
    // running whenever you're logged in — for a personal machine, that's nearly
    // always — rather than failing outright.
    try {
      register("InteractiveToken", time);
      mode = "InteractiveToken";
      console.log(`(Could not register a run-while-logged-out task: ${errorText(s4uErr)})`);
    } catch (err) {
      console.error(`Could not register the scheduled task:\n  ${errorText(err)}`);
      process.exit(1);
    }
  }

  console.log(`Installed "${TASK_NAME}": daily at ${time}.`);
  console.log(
    mode === "S4U"
      ? "  Runs whether or not you're logged in; the dashboard doesn't need to be open."
      : "  Runs while you're logged in (a locked screen counts); the dashboard doesn't need to be open."
  );
  console.log("  Missed because the PC was off or asleep? It runs as soon as the PC is back.");

  if (flag("--run")) {
    schtasks(["/Run", "/TN", TASK_NAME]);
    console.log("  Started a run now. Its output goes to logs/.");
  }
  status();
}

function remove() {
  try {
    schtasks(["/Delete", "/TN", TASK_NAME, "/F"]);
    console.log(`Removed "${TASK_NAME}".`);
  } catch {
    console.log(`No "${TASK_NAME}" task was installed.`);
  }
}

if (process.platform !== "win32") {
  console.error("This installs a Windows scheduled task. On macOS/Linux, add a daily cron entry instead:");
  console.error(`  0 6 * * *  cd "${APP_DIR}" && "${process.execPath}" scripts/scheduled-run.js`);
  process.exit(1);
}

if (flag("--remove")) remove();
else if (flag("--status")) status();
else install();
