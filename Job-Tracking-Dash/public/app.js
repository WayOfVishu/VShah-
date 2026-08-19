const GOAL_TOTAL = 360;
const GOAL_PER_DAY = 6;
const SPRINT_DAYS = 60;

const els = {
  form: document.getElementById("jobForm"),
  submitBtn: document.getElementById("submitBtn"),
  cancelEdit: document.getElementById("cancelEdit"),
  search: document.getElementById("search"),
  logBody: document.getElementById("logBody"),
  emptyState: document.getElementById("emptyState"),
  heatmap: document.getElementById("heatmap"),
  dayNum: document.getElementById("dayNum"),
  totalNum: document.getElementById("totalNum"),
  paceNum: document.getElementById("paceNum"),
  streakNum: document.getElementById("streakNum"),
  runwayFill: document.getElementById("runwayFill"),
  runwayLabel: document.getElementById("runwayLabel"),
};

let jobs = [];
let editingId = null;
let charts = {};

const CHART_COLORS = {
  text: "#8b93a3",
  grid: "#2b303c",
  amber: "#e2a33b",
  teal: "#4fb0a5",
  green: "#5fb87e",
  danger: "#e1614c",
  palette: ["#e2a33b", "#4fb0a5", "#5fb87e", "#e1614c", "#8b7ee8", "#e88fc2", "#6ea8e0", "#c2b280"],
};

Chart.defaults.color = CHART_COLORS.text;
Chart.defaults.font.family = "'IBM Plex Mono', monospace";
Chart.defaults.font.size = 11;

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------
async function loadJobs() {
  const res = await fetch("/api/jobs");
  jobs = await res.json();
  renderAll();
}

async function submitForm(e) {
  e.preventDefault();
  const fd = new FormData(els.form);
  const payload = Object.fromEntries(fd.entries());
  payload.referral = fd.get("referral") ? 1 : 0;
  payload.timestamp = new Date(payload.timestamp).toISOString();

  const url = editingId ? `/api/jobs/${editingId}` : "/api/jobs";
  const method = editingId ? "PUT" : "POST";
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert(err.error || "Something went wrong saving that entry.");
    return;
  }
  resetForm();
  await loadJobs();
}

function resetForm() {
  els.form.reset();
  editingId = null;
  els.submitBtn.textContent = "Log application";
  els.cancelEdit.hidden = true;
}

function startEdit(job) {
  editingId = job.id;
  els.form.title.value = job.title;
  els.form.company.value = job.company;
  els.form.platform.value = job.platform;
  els.form.timestamp.value = toLocalInputValue(job.timestamp);
  els.form.status.value = job.status;
  els.form.location.value = job.location || "";
  els.form.url.value = job.url || "";
  els.form.referral.checked = !!job.referral;
  els.form.notes.value = job.notes || "";
  els.submitBtn.textContent = "Save changes";
  els.cancelEdit.hidden = false;
  els.form.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function deleteJob(id) {
  if (!confirm("Delete this application entry? This can't be undone.")) return;
  await fetch(`/api/jobs/${id}`, { method: "DELETE" });
  await loadJobs();
}

function toLocalInputValue(iso) {
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function dateKey(iso) {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------
function renderAll() {
  renderClock();
  renderRunway();
  renderHeatmap();
  renderTable();
  renderCharts();
}

function renderClock() {
  els.totalNum.textContent = jobs.length;

  if (jobs.length === 0) {
    els.dayNum.textContent = "1 / 60";
    els.paceNum.textContent = "0.0";
    els.streakNum.textContent = "0";
    return;
  }

  const firstDay = startOfDay(new Date(jobs[0].timestamp));
  const today = startOfDay(new Date());
  const dayNum = Math.min(SPRINT_DAYS, Math.floor((today - firstDay) / 86400000) + 1);
  els.dayNum.textContent = `${dayNum} / ${SPRINT_DAYS}`;
  els.paceNum.textContent = (jobs.length / dayNum).toFixed(1);
  els.streakNum.textContent = computeStreak();
}

function computeStreak() {
  const days = new Set(jobs.map((j) => dateKey(j.timestamp)));
  let streak = 0;
  let cursor = startOfDay(new Date());
  // if nothing logged today yet, still count back from yesterday
  if (!days.has(fmt(cursor))) cursor = addDays(cursor, -1);
  while (days.has(fmt(cursor))) {
    streak++;
    cursor = addDays(cursor, -1);
  }
  return streak;

  function fmt(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; }
}

function startOfDay(d) { const c = new Date(d); c.setHours(0, 0, 0, 0); return c; }
function addDays(d, n) { const c = new Date(d); c.setDate(c.getDate() + n); return c; }

function renderRunway() {
  const pct = Math.min(100, (jobs.length / GOAL_TOTAL) * 100);
  els.runwayFill.style.width = `calc(${pct}% - ${pct > 0 ? "0px" : "0px"})`;
  els.runwayFill.style.width = `${pct}%`;
  els.runwayLabel.textContent = `${jobs.length} / ${GOAL_TOTAL} applications`;
}

function renderHeatmap() {
  const counts = {};
  jobs.forEach((j) => { const k = dateKey(j.timestamp); counts[k] = (counts[k] || 0) + 1; });

  const start = jobs.length ? startOfDay(new Date(jobs[0].timestamp)) : startOfDay(new Date());
  els.heatmap.innerHTML = "";
  for (let i = 0; i < SPRINT_DAYS; i++) {
    const d = addDays(start, i);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const count = counts[key] || 0;
    const cell = document.createElement("div");
    cell.className = "cell " + levelClass(count);
    cell.title = `${key}: ${count} application${count === 1 ? "" : "s"}`;
    if (d > startOfDay(new Date())) cell.dataset.future = "1";
    const label = document.createElement("span");
    label.className = "day-num";
    label.textContent = i + 1;
    cell.appendChild(label);
    els.heatmap.appendChild(cell);
  }

  function levelClass(c) {
    if (c <= 0) return "l0";
    if (c === 1) return "l1";
    if (c <= 3) return "l2";
    if (c < GOAL_PER_DAY) return "l3";
    return "l4";
  }
}

function renderTable() {
  const q = els.search.value.trim().toLowerCase();
  const filtered = q
    ? jobs.filter((j) => [j.title, j.company, j.platform].join(" ").toLowerCase().includes(q))
    : jobs;

  els.emptyState.hidden = jobs.length !== 0;
  els.logBody.innerHTML = "";
  [...filtered].reverse().forEach((j) => {
    const tr = document.createElement("tr");
    const applied = new Date(j.timestamp);
    tr.innerHTML = `
      <td>${applied.toLocaleDateString()} ${applied.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</td>
      <td class="title-cell">${escapeHtml(j.title)}</td>
      <td class="company-cell">${escapeHtml(j.company)}</td>
      <td>${escapeHtml(j.platform)}</td>
      <td><span class="status-pill status-${j.status}">${j.status}</span></td>
      <td>${j.referral ? "Y" : "—"}</td>
      <td class="row-actions">
        <button data-action="edit" data-id="${j.id}">Edit</button>
        <button data-action="delete" data-id="${j.id}">Delete</button>
      </td>`;
    els.logBody.appendChild(tr);
  });
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------------------------------------------------------------------------
// Charts
// ---------------------------------------------------------------------------
function renderCharts() {
  const byDay = groupCount(jobs, (j) => dateKey(j.timestamp));
  const days = sortedDayRange(byDay);
  const dailyCounts = days.map((d) => byDay[d] || 0);

  upsertChart("dailyChart", "bar", {
    labels: days.map(shortDate),
    datasets: [{ label: "Applications", data: dailyCounts, backgroundColor: CHART_COLORS.amber, borderRadius: 3 }],
  }, { scales: baseScales() });

  const cumulative = [];
  dailyCounts.reduce((acc, c, i) => (cumulative[i] = acc + c), 0);
  let running = 0;
  const cumulativeData = dailyCounts.map((c) => (running += c));
  upsertChart("cumulativeChart", "line", {
    labels: days.map(shortDate),
    datasets: [
      { label: "Cumulative applications", data: cumulativeData, borderColor: CHART_COLORS.teal, backgroundColor: CHART_COLORS.teal + "22", fill: true, tension: 0.35, pointRadius: 2 },
      { label: "Goal pace", data: days.map((_, i) => Math.round((GOAL_TOTAL / SPRINT_DAYS) * (i + 1))), borderColor: CHART_COLORS.text, borderDash: [4, 4], pointRadius: 0 },
    ],
  }, { scales: baseScales() });

  const rolling = dailyCounts.map((_, i) => {
    const slice = dailyCounts.slice(Math.max(0, i - 6), i + 1);
    return +(slice.reduce((a, b) => a + b, 0) / slice.length).toFixed(2);
  });
  upsertChart("rollingChart", "line", {
    labels: days.map(shortDate),
    datasets: [{ label: "7-day rolling avg", data: rolling, borderColor: CHART_COLORS.amber, tension: 0.35, pointRadius: 0 }],
  }, { scales: baseScales() });

  const byPlatform = groupCount(jobs, (j) => j.platform || "Unspecified");
  upsertChart("platformChart", "doughnut", {
    labels: Object.keys(byPlatform),
    datasets: [{ data: Object.values(byPlatform), backgroundColor: CHART_COLORS.palette }],
  }, { plugins: { legend: { position: "bottom", labels: { boxWidth: 10 } } } });

  const byStatus = groupCount(jobs, (j) => j.status || "applied");
  upsertChart("statusChart", "doughnut", {
    labels: Object.keys(byStatus),
    datasets: [{ data: Object.values(byStatus), backgroundColor: CHART_COLORS.palette }],
  }, { plugins: { legend: { position: "bottom", labels: { boxWidth: 10 } } } });

  const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const byDow = DOW.map((_, i) => jobs.filter((j) => new Date(j.timestamp).getDay() === i).length);
  upsertChart("dowChart", "bar", {
    labels: DOW,
    datasets: [{ label: "Applications", data: byDow, backgroundColor: CHART_COLORS.teal, borderRadius: 3 }],
  }, { scales: baseScales() });

  const byCompany = groupCount(jobs, (j) => j.company);
  const topCompanies = Object.entries(byCompany).sort((a, b) => b[1] - a[1]).slice(0, 10);
  upsertChart("companyChart", "bar", {
    labels: topCompanies.map(([name]) => name),
    datasets: [{ label: "Applications", data: topCompanies.map(([, c]) => c), backgroundColor: CHART_COLORS.amber, borderRadius: 3 }],
  }, { indexAxis: "y", scales: baseScales() });
}

function groupCount(arr, keyFn) {
  return arr.reduce((acc, item) => {
    const k = keyFn(item);
    acc[k] = (acc[k] || 0) + 1;
    return acc;
  }, {});
}

function sortedDayRange(byDay) {
  const keys = Object.keys(byDay);
  if (keys.length === 0) return [];
  keys.sort();
  const start = new Date(keys[0]);
  const end = new Date(keys[keys.length - 1]);
  const out = [];
  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`);
  }
  return out;
}

function shortDate(iso) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function baseScales() {
  return {
    x: { grid: { color: CHART_COLORS.grid }, ticks: { maxRotation: 0, autoSkip: true } },
    y: { grid: { color: CHART_COLORS.grid }, beginAtZero: true },
  };
}

function upsertChart(canvasId, type, data, extraOptions = {}) {
  const ctx = document.getElementById(canvasId);
  if (charts[canvasId]) charts[canvasId].destroy();
  charts[canvasId] = new Chart(ctx, {
    type,
    data,
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: type === "doughnut", labels: { color: CHART_COLORS.text } } },
      ...extraOptions,
    },
  });
}

// ---------------------------------------------------------------------------
// Wire up
// ---------------------------------------------------------------------------
els.form.addEventListener("submit", submitForm);
els.cancelEdit.addEventListener("click", resetForm);
els.search.addEventListener("input", renderTable);
els.logBody.addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  const id = btn.dataset.id;
  if (btn.dataset.action === "edit") startEdit(jobs.find((j) => String(j.id) === id));
  if (btn.dataset.action === "delete") deleteJob(id);
});

// default the timestamp field to "now" for convenience
document.getElementById("jobForm").timestamp.value = toLocalInputValue(new Date().toISOString());

loadJobs();
