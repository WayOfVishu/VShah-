import { test } from "node:test";
import assert from "node:assert/strict";
import { buildTaskXml, nextStartBoundary, parseTime } from "./scheduledTask.js";

test("parseTime accepts 24-hour HH:MM and rejects anything else", () => {
  assert.deepEqual(parseTime("06:00"), { hours: 6, minutes: 0 });
  assert.deepEqual(parseTime("7:30"), { hours: 7, minutes: 30 });
  assert.throws(() => parseTime("24:00"));
  assert.throws(() => parseTime("6am"));
});

test("the first run is always in the future", () => {
  const morning = new Date(2026, 8, 10, 5, 0);
  const afternoon = new Date(2026, 8, 10, 14, 0);
  assert.equal(nextStartBoundary("06:00", morning), "2026-09-10T06:00:00");
  // Installing after today's slot must not count this morning as missed.
  assert.equal(nextStartBoundary("06:00", afternoon), "2026-09-11T06:00:00");
  // Month rollover.
  assert.equal(nextStartBoundary("06:00", new Date(2026, 8, 30, 9, 0)), "2026-10-01T06:00:00");
});

const xml = buildTaskXml({
  command: "C:\\Program Files\\nodejs\\node.exe",
  args: '"C:\\apps\\Jobs & Things\\scripts\\scheduled-run.js"',
  workingDir: "C:\\apps\\Jobs & Things",
  time: "06:00",
  userId: "PC\\me",
  now: new Date(2026, 8, 10, 5, 0),
});

test("the settings that make a daily run actually happen daily", () => {
  assert.match(xml, /<DaysInterval>1<\/DaysInterval>/);
  assert.match(xml, /<StartWhenAvailable>true<\/StartWhenAvailable>/);
  assert.match(xml, /<DisallowStartIfOnBatteries>false<\/DisallowStartIfOnBatteries>/);
  assert.match(xml, /<StopIfGoingOnBatteries>false<\/StopIfGoingOnBatteries>/);
  assert.match(xml, /<RunOnlyIfNetworkAvailable>true<\/RunOnlyIfNetworkAvailable>/);
  assert.match(xml, /<MultipleInstancesPolicy>IgnoreNew<\/MultipleInstancesPolicy>/);
  assert.match(xml, /<LogonType>S4U<\/LogonType>/);
});

test("paths are XML-escaped", () => {
  assert.match(xml, /<WorkingDirectory>C:\\apps\\Jobs &amp; Things<\/WorkingDirectory>/);
  assert.match(xml, /<Arguments>&quot;C:\\apps\\Jobs &amp; Things\\scripts\\scheduled-run.js&quot;<\/Arguments>/);
});
