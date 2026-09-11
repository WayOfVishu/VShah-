// The Windows Task Scheduler definition behind `npm run schedule` — kept apart
// from the script that registers it so the settings that matter can be tested
// without touching the machine's task list.
//
// Written as task XML rather than `schtasks /Create /SC DAILY` flags because the
// flags can't express the three settings that make a once-a-day run actually
// happen once a day on a laptop:
//   * StartWhenAvailable — if the PC was off or asleep at the scheduled time,
//     run as soon as it's back instead of silently skipping the day;
//   * DisallowStartIfOnBatteries=false — the default refuses to start on
//     battery, which would skip every day spent unplugged;
//   * RunOnlyIfNetworkAvailable — a run with no network would just record a
//     failure against every source.

export const TASK_NAME = "Jobs-Web-App daily discovery";

const TIME = /^([01]?\d|2[0-3]):([0-5]\d)$/;

export function parseTime(text) {
  const m = TIME.exec(String(text || "").trim());
  if (!m) throw new Error(`"${text}" is not a time — use 24-hour HH:MM, e.g. 06:00 or 18:30.`);
  return { hours: Number(m[1]), minutes: Number(m[2]) };
}

const pad = (n) => String(n).padStart(2, "0");

// The next time the clock reads HH:MM, as local wall-clock time without an
// offset — the form Task Scheduler reads as "local time, whatever the DST".
// Always in the future, so installing at 09:00 for 06:00 doesn't count this
// morning as a missed run and fire straight away.
export function nextStartBoundary(time, now = new Date()) {
  const { hours, minutes } = parseTime(time);
  const next = new Date(now.getFullYear(), now.getMonth(), now.getDate(), hours, minutes, 0);
  if (next <= now) next.setDate(next.getDate() + 1);
  return (
    `${next.getFullYear()}-${pad(next.getMonth() + 1)}-${pad(next.getDate())}` +
    `T${pad(next.getHours())}:${pad(next.getMinutes())}:00`
  );
}

const xmlEscape = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" }[c]));

// logonType:
//   "S4U"              runs whether or not you're logged in, with no window
//                      and no stored password; registering it may need admin.
//   "InteractiveToken" runs only while you're logged in (a locked screen still
//                      counts); `command` should then hide its own window.
export function buildTaskXml({ command, args, workingDir, time = "18:00", userId, logonType = "S4U", now = new Date() }) {
  const start = nextStartBoundary(time, now);
  return `<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Runs Jobs-Web-App discovery (discover.js) once a day, whether or not the dashboard is open. Installed by scripts/schedule-discovery.js; output goes to logs/.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>${start}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>${xmlEscape(userId)}</UserId>
      <LogonType>${xmlEscape(logonType)}</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure>
      <Interval>PT30M</Interval>
      <Count>2</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>${xmlEscape(command)}</Command>
      <Arguments>${xmlEscape(args)}</Arguments>
      <WorkingDirectory>${xmlEscape(workingDir)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
`;
}
