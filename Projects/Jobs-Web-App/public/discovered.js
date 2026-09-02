// Discovered view (PRD req. 22, 31-32). Kept in its own file so the existing
// app.js — which owns the applied log and its charts — is untouched.

const dEls = {
  tabs: document.querySelectorAll(".view-tab"),
  appliedView: document.getElementById("appliedView"),
  discoveredView: document.getElementById("discoveredView"),
  count: document.getElementById("discoveredCount"),

  refresh: document.getElementById("refreshDiscovery"),
  refreshLabel: document.getElementById("refreshLabel"),
  runPanel: document.getElementById("runPanel"),
  runStatus: document.getElementById("runStatus"),
  runLog: document.getElementById("runLog"),
  toggleRunLog: document.getElementById("toggleRunLog"),

  banner: document.getElementById("sourceBanner"),
  bannerText: document.getElementById("sourceBannerText"),
  dismissBanner: document.getElementById("dismissBanner"),

  body: document.getElementById("discoveredBody"),
  search: document.getElementById("discoveredSearch"),
  statusFilter: document.getElementById("statusFilter"),
  sortMode: document.getElementById("sortMode"),
  freshness: document.getElementById("freshness"),
  bucketFilter: document.getElementById("bucketFilter"),
  bucketToggle: document.getElementById("bucketToggle"),
  bucketPanel: document.getElementById("bucketPanel"),
  bucketLabel: document.getElementById("bucketLabel"),
  hideApplied: document.getElementById("hideApplied"),
  mixSummary: document.getElementById("mixSummary"),
  summary: document.getElementById("discoveredSummary"),
  empty: document.getElementById("discoveredEmpty"),
  loadMore: document.getElementById("loadMore"),

  draftModal: document.getElementById("draftModal"),
  draftPathLine: document.getElementById("draftPathLine"),
  traceOk: document.getElementById("traceOk"),
  traceWarn: document.getElementById("traceWarn"),
  flagCount: document.getElementById("flagCount"),
  flagList: document.getElementById("flagList"),
  draftText: document.getElementById("draftText"),
  baseResumeText: document.getElementById("baseResumeText"),
  draftStatus: document.getElementById("draftStatus"),
  markAppliedFromDraft: document.getElementById("markAppliedFromDraft"),
  downloadFromDraft: document.getElementById("downloadFromDraft"),
};

// PRD Goal 7: uncapped discovery must not become a wall of rows. The live run
// produced ~2900 postings from six companies, so the table renders a page at a
// time — the browser stays responsive and the queue stays readable — while the
// filters do the actual triage until match_score ranking exists.
const PAGE_SIZE = 60;

let discovered = [];
let feedMeta = null;
let visibleCount = PAGE_SIZE;
let activeJob = null;
let bannerDismissed = false;

const BUCKET_LABELS = {
  calgary: "Calgary",
  edmonton: "Edmonton",
  remote: "Remote",
  vancouver: "Vancouver",
  seattle: "Seattle",
  unknown: "unspecified",
  "off-list": "off-list",
};

const STATUS_LABELS = {
  new: "New",
  queued: "Queued",
  generating: "Generating…",
  tailored: "Tailored",
  rejected: "Rejected",
  dismissed: "Dismissed",
  applied: "Applied",
  archived: "Archived",
};

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

async function api(url, options) {
  const res = await fetch(url, options);
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) throw new Error(body?.error || `Request failed (${res.status})`);
  return body;
}

function shortDateTime(value) {
  if (!value) return "–";
  // SQLite datetime('now') gives "YYYY-MM-DD HH:MM:SS" in UTC.
  const iso = value.includes("T") ? value : `${value.replace(" ", "T")}Z`;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// ---------------------------------------------------------------------------
// View switching
// ---------------------------------------------------------------------------
dEls.tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    const view = tab.dataset.view;
    dEls.tabs.forEach((t) => {
      const active = t === tab;
      t.classList.toggle("is-active", active);
      if (active) t.setAttribute("aria-current", "page");
      else t.removeAttribute("aria-current");
    });
    dEls.appliedView.hidden = view !== "applied";
    dEls.discoveredView.hidden = view !== "discovered";
    if (view === "discovered") loadDiscovered();
  });
});

// ---------------------------------------------------------------------------
// The freshness control
// ---------------------------------------------------------------------------
// One number governs how far back the app looks, and this control is where it
// is chosen. It is used in three places — the on-screen filter, the ingest
// window of the next discovery run, and what gets saved to preferences.json —
// and all three now read the same value from here.
//
// The windows on offer. 0 means no limit; the saved value is added to this
// list if it is not already one of them, so a hand-edited preferences.json
// still shows up correctly rather than silently resetting.
const FRESHNESS_WINDOWS = [3, 7, 14];

function freshnessLabelFor(days) {
  return days === 0 ? "Any age" : `Posted ≤ ${days} days`;
}

// Builds the dropdown from the saved preference. Nothing here invents a
// default: whatever is stored is what gets selected, and if the server cannot
// be reached the control still renders so the page is usable.
// Which location buckets the feed is restricted to. Empty means all of them.
const selectedBuckets = new Set();

// Builds the location checkboxes from the buckets that actually exist in
// preferences.json, rather than a second hard-coded list in the markup — the
// same reason the freshness options are built rather than written out. Drop a
// location from your weights and it disappears from here too.
function buildBucketFilter(locationWeights = {}) {
  const names = Object.keys(locationWeights);
  dEls.bucketPanel.replaceChildren(
    ...names.map((bucket) => {
      const label = document.createElement("label");
      const box = document.createElement("input");
      box.type = "checkbox";
      box.value = bucket;
      box.addEventListener("change", () => {
        if (box.checked) selectedBuckets.add(bucket);
        else selectedBuckets.delete(bucket);
        renderBucketLabel();
        visibleCount = PAGE_SIZE;
        loadDiscovered();
      });
      label.append(box, document.createTextNode(BUCKET_LABELS[bucket] || bucket));
      return label;
    })
  );

  const clear = document.createElement("button");
  clear.type = "button";
  clear.className = "multi-select-clear";
  clear.textContent = "All locations";
  clear.addEventListener("click", () => {
    selectedBuckets.clear();
    dEls.bucketPanel.querySelectorAll("input").forEach((i) => (i.checked = false));
    renderBucketLabel();
    visibleCount = PAGE_SIZE;
    loadDiscovered();
  });
  dEls.bucketPanel.append(clear);
  renderBucketLabel();
}

function renderBucketLabel() {
  const chosen = [...selectedBuckets].map((b) => BUCKET_LABELS[b] || b);
  const text = chosen.length === 0 ? "All locations" : chosen.join(", ");
  dEls.bucketLabel.textContent = text;
  // The button truncates with an ellipsis, so the full selection lives in the
  // tooltip rather than being lost.
  dEls.bucketToggle.title = chosen.length ? `Locations: ${text}` : "All locations";
}

const setBucketPanelOpen = (open) => {
  dEls.bucketPanel.hidden = !open;
  dEls.bucketToggle.setAttribute("aria-expanded", String(open));
};

dEls.bucketToggle.addEventListener("click", (e) => {
  e.stopPropagation();
  setBucketPanelOpen(dEls.bucketPanel.hidden);
});
// Clicking inside the panel must not close it — every click in there is a
// checkbox the user is still working through.
dEls.bucketPanel.addEventListener("click", (e) => e.stopPropagation());
document.addEventListener("click", () => setBucketPanelOpen(false));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") setBucketPanelOpen(false);
});

// Whether the saved preferences were actually read. If they were not, the
// freshness control is showing a fallback rather than the user's choice, and
// must not be allowed to write that fallback back to disk — a momentarily
// unreachable server would otherwise turn into a silently changed setting the
// next time any control moved.
let prefsLoaded = false;

async function initControls() {
  let saved = null;
  let locationWeights = {};
  try {
    ({ maxAgeDays: saved, locationWeights = {} } = await api("/api/preferences"));
    prefsLoaded = true;
  } catch {
    // Leave `saved` null — "Any age" — rather than guessing a window and
    // hiding postings the user never asked to hide.
  }
  buildBucketFilter(locationWeights);
  const selected = saved === null ? 0 : Number(saved);
  const windows = FRESHNESS_WINDOWS.includes(selected) || selected === 0
    ? FRESHNESS_WINDOWS
    : [...FRESHNESS_WINDOWS, selected].sort((a, b) => a - b);

  dEls.freshness.replaceChildren(
    ...[...windows, 0].map((days) => {
      const opt = document.createElement("option");
      opt.value = String(days);
      opt.textContent = freshnessLabelFor(days);
      opt.selected = days === selected;
      return opt;
    })
  );
}

// Started at load rather than when the Discovered tab is first opened, so the
// controls are already showing the saved window and locations by the time
// anyone looks at them. loadDiscovered() awaits it, so no request can go out
// reading an unpopulated control — which would send an empty maxAgeDays and
// silently mean "any age".
const controlsReady = initControls();

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------
// Every control in the filter bar is a query parameter — status and the search
// box included. They used to be re-filtered in the browser over whatever the
// server had already sent, which meant the two could disagree about how many
// rows existed and the summary line counted the wrong thing.
function currentQuery() {
  const params = new URLSearchParams({
    status: dEls.statusFilter.value,
    sort: dEls.sortMode.value,
    maxAgeDays: dEls.freshness.value,
    hideApplied: dEls.hideApplied.checked ? "1" : "0",
  });
  // Comma-separated so several locations can be viewed at once; the server
  // turns it back into an IN (...) clause.
  if (selectedBuckets.size) params.set("bucket", [...selectedBuckets].join(","));
  const q = dEls.search.value.trim();
  if (q) params.set("q", q);
  return params;
}

async function loadDiscovered() {
  await controlsReady;
  try {
    const payload = await api(`/api/discovered?${currentQuery()}`);
    discovered = payload.jobs;
    feedMeta = payload.meta;
    visibleCount = PAGE_SIZE;
    renderDiscovered();
  } catch (err) {
    dEls.summary.textContent = `Could not load discovered postings: ${err.message}`;
  }
  loadSourceHealth();
}

// req. 31 / §6: a persistent banner while any source is permanent-fail, so a
// broken source can't masquerade as "nothing new today" (req. 4).
async function loadSourceHealth() {
  try {
    const sources = await api("/api/discovered/sources");
    const broken = sources.filter((s) => s.status === "permanent-fail");
    const degraded = sources.filter((s) => s.status === "render-failed");

    if (broken.length === 0 && degraded.length === 0) {
      dEls.banner.hidden = true;
      return;
    }
    const parts = [];
    if (broken.length) {
      parts.push(
        `${broken.length} source(s) have failed 3 runs in a row and need investigating: ` +
          `${broken.map((s) => s.name).join(", ")}.`
      );
    }
    if (degraded.length) {
      parts.push(`Recently failed (will retry): ${degraded.map((s) => s.name).join(", ")}.`);
    }
    dEls.bannerText.textContent = ` ${parts.join(" ")}`;
    dEls.banner.classList.toggle("is-critical", broken.length > 0);
    // A permanent-fail is persistent: dismissing it hides it for this page
    // load only, and it returns on reload until the source is fixed.
    dEls.banner.hidden = bannerDismissed;
  } catch {
    dEls.banner.hidden = true;
  }
}

dEls.dismissBanner.addEventListener("click", () => {
  bannerDismissed = true;
  dEls.banner.hidden = true;
});

// Sorting and hide-applied are applied server-side, so each needs a refetch
// rather than a re-render. (The location filter is not a <select> any more —
// its checkboxes refetch themselves; see buildBucketFilter.)
[dEls.sortMode, dEls.hideApplied].forEach((el) => el.addEventListener("change", loadDiscovered));

// Freshness is the one control that outlives the page. Saving it on change is
// what makes the window you picked the window the next discovery run ingests
// with, and the one still selected after a reload.
dEls.freshness.addEventListener("change", async () => {
  if (!prefsLoaded) {
    // Filter the view, but do not persist: this control never learned what the
    // saved window was, so writing its value would overwrite a real setting
    // with a fallback.
    showToast("Preferences could not be loaded — this filter applies to the view only.", { type: "error" });
    await loadDiscovered();
    return;
  }
  try {
    await api("/api/preferences", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ maxAgeDays: Number(dEls.freshness.value) }),
    });
  } catch (err) {
    // Saving failed, but the filter should still apply to what is on screen.
    showToast(`Could not save the freshness window: ${err.message}`, { type: "error" });
  }
  await loadDiscovered();
});

// ---------------------------------------------------------------------------
// Discovery runs
// ---------------------------------------------------------------------------
// The server runs discovery in a child process and holds the run state, so this
// is a poller, not an owner: on load it adopts whatever run is already in
// flight. A reload mid-run rejoins it instead of appearing to have lost it, and
// a second tab shows the same run rather than starting a competing one.
const POLL_MS = 1500;
let pollTimer = null;

function renderRun(state) {
  if (state.status === "idle") {
    dEls.runPanel.hidden = true;
    return;
  }
  dEls.runPanel.hidden = false;
  dEls.runPanel.classList.toggle("is-running", state.status === "running");
  dEls.runPanel.classList.toggle("is-failed", state.status === "failed");

  const running = state.status === "running";
  dEls.refresh.disabled = running;
  dEls.refresh.classList.toggle("is-busy", running);
  dEls.refreshLabel.textContent = running ? "Searching…" : "Refresh job searches";

  // The last line discover.js printed is the most useful one-line status there
  // is — it names the tier currently being fetched.
  const last = state.log.length ? state.log[state.log.length - 1] : "";
  if (running) {
    dEls.runStatus.textContent = last || "Starting discovery…";
  } else if (state.status === "done") {
    const saved = state.log.find((l) => l.includes("New postings saved:"));
    dEls.runStatus.textContent = saved ? saved.trim() : "Run finished.";
  } else {
    dEls.runStatus.textContent = `Run failed (exit ${state.exitCode}). ${last}`;
  }

  dEls.runLog.textContent = state.log.join("\n");
  // Only autoscroll while the log is growing; once the run is over the user may
  // be reading the gate tolls further up.
  if (running && !dEls.runLog.hidden) dEls.runLog.scrollTop = dEls.runLog.scrollHeight;
}

async function pollRun() {
  let state;
  try {
    state = await api("/api/discover/status");
  } catch {
    // A dropped poll is not a failed run — the server may just be busy under
    // the run’s own writes. Keep polling rather than declaring failure.
    return;
  }
  renderRun(state);

  if (state.status === "running") return;

  clearInterval(pollTimer);
  pollTimer = null;
  // The run wrote rows straight into jobs.db, so the feed on screen is stale
  // the moment it finishes.
  if (state.status === "done") await loadDiscovered();
  else loadSourceHealth();
}

function watchRun() {
  if (pollTimer) return;
  pollTimer = setInterval(pollRun, POLL_MS);
}

dEls.refresh.addEventListener("click", async () => {
  dEls.refresh.disabled = true;
  try {
    // No body: the freshness window was already saved when it was chosen, and
    // discover.js reads it from preferences.json itself. Widening the filter
    // and hitting Refresh still fetches the older postings it now admits.
    renderRun(await api("/api/discover", { method: "POST" }));
    watchRun();
  } catch (err) {
    dEls.runPanel.hidden = false;
    dEls.runPanel.classList.add("is-failed");
    dEls.runStatus.textContent = err.message;
    dEls.refresh.disabled = false;
    // A 409 means a run this tab did not start is already going; join it.
    watchRun();
  }
});

dEls.toggleRunLog.addEventListener("click", () => {
  const show = dEls.runLog.hidden;
  dEls.runLog.hidden = !show;
  dEls.toggleRunLog.textContent = show ? "Hide log" : "Show log";
  dEls.toggleRunLog.setAttribute("aria-expanded", String(show));
  if (show) dEls.runLog.scrollTop = dEls.runLog.scrollHeight;
});

// Adopt an in-flight run on first load.
api("/api/discover/status")
  .then((state) => {
    renderRun(state);
    if (state.status === "running") watchRun();
  })
  .catch(() => {});


// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------
function actionsFor(job) {
  const btn = (action, label, cls = "") =>
    `<button type="button" class="row-action ${cls}" data-action="${action}" data-id="${job.id}">${label}</button>`;

  switch (job.status) {
    case "new":
      return btn("tailor", "Tailor", "primary") + btn("dismiss", "Dismiss") + btn("apply", "Applied");
    case "queued":
      return btn("tailor", "Tailor", "primary") + btn("reject", "Reject") + btn("apply", "Applied");
    case "generating":
      return '<span class="row-working"><span class="row-spinner"></span>Tailoring…</span>';
    case "tailored":
      // Download first: the draft already exists, so re-downloading it should
      // not mean re-running a two-minute generation.
      return (
        btn("download", "Download", "primary") +
        btn("draft", "Review") +
        btn("apply", "Applied") +
        btn("dismiss", "Dismiss")
      );
    case "rejected":
    case "dismissed":
      return btn("reset", "Restore");
    case "archived":
      return btn("reset", "Restore") + btn("dismiss", "Dismiss");
    case "applied":
      return '<span class="hint">logged</span>';
    default:
      return "";
  }
}

// The empty state used to be a hardcoded line of HTML naming "Posted ≤ 3
// days" regardless of which freshness filter was actually active — so
// switching to "Any age" still told you to widen a filter you'd already
// widened. Build it from the live filter state instead.
function emptyStateMessage() {
  const q = dEls.search.value.trim();
  if (q) return `Nothing matches &ldquo;${esc(q)}&rdquo; under the current filters.`;

  const freshnessLabel = dEls.freshness.options[dEls.freshness.selectedIndex].textContent;
  let msg = `No discovered postings match these filters. Hit <strong>Refresh job searches</strong> to pull new ones`;
  if (dEls.freshness.value !== "0") {
    msg +=
      `, widen &ldquo;${esc(freshnessLabel)}&rdquo; and refresh again ` +
      `(the freshness filter sets how far back the next run looks)`;
  }
  msg += `, or edit <code>config/preferences.json</code>.`;
  return msg;
}

function renderDiscovered(animate = true) {
  // The server has already applied every filter in the bar, so this renders
  // what it returned rather than filtering a second time over the same rows.
  const rows = discovered;
  const shown = rows.slice(0, visibleCount);

  dEls.body.innerHTML = shown
    .map((job) => {
      const sources = (job.sources || []).join(", ");
      const error = job.tailor_error
        ? `<div class="row-error" title="${esc(job.tailor_error)}">⚠ ${esc(job.tailor_error.slice(0, 90))}</div>`
        : "";
      // A US role that never mentions sponsorship had its score cut; say so on
      // the row rather than letting it look like an inexplicably low ranking.
      const visaFlag = job.unsponsored_us
        ? ` <span class="hint" title="US-based and silent on visa sponsorship — score reduced">🛂</span>`
        : "";
      const bucket = job.location_bucket
        ? `<span class="bucket-pill bucket-${esc(job.location_bucket)}">${esc(
            BUCKET_LABELS[job.location_bucket] || job.location_bucket
          )}</span> `
        : "";

      return `
        <tr data-id="${job.id}">
          <td title="First seen ${esc(shortDateTime(job.first_seen_at))}">${esc(
        shortDateTime(job.posted_date || job.first_seen_at)
      )}</td>
          <td class="title-cell">
            <a href="${esc(job.apply_url)}" target="_blank" rel="noopener noreferrer">${esc(job.title)}</a>${visaFlag}
            ${error}
          </td>
          <td class="company-cell">${esc(job.company)}</td>
          <td>${bucket}${esc(job.location || "–")}</td>
          <td class="sources-cell">${esc(sources)}</td>
          <td>${job.match_score == null ? "–" : job.match_score.toFixed(2)}</td>
          <td><span class="status-pill status-${job.status}">${STATUS_LABELS[job.status] || job.status}</span></td>
          <td class="row-actions">${actionsFor(job)}</td>
        </tr>`;
    })
    .join("");
  if (animate) staggerRows(dEls.body);
  else [...dEls.body.children].forEach((row) => (row.style.animation = "none"));

  dEls.empty.hidden = rows.length > 0;
  if (rows.length === 0) dEls.empty.innerHTML = emptyStateMessage();
  dEls.loadMore.hidden = rows.length <= visibleCount;

  // The count the server filtered down from matters as much as what survived:
  // "12 of 2908" is the difference between a quiet day and a broken connector.
  const filteredOut = feedMeta ? feedMeta.total - feedMeta.shown : 0;
  dEls.summary.textContent = rows.length
    ? `Showing ${shown.length} of ${rows.length} matching` +
      (filteredOut > 0 ? ` · ${filteredOut} hidden by your filters` : "")
    : "";

  // What the balanced mix actually delivered, so the configured percentages
  // can be checked against reality rather than taken on faith.
  if (feedMeta && feedMeta.sort === "mix" && rows.length > 0) {
    const counts = shown.reduce((acc, j) => {
      const b = j.location_bucket || "off-list";
      acc[b] = (acc[b] || 0) + 1;
      return acc;
    }, {});
    const parts = Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([b, n]) => `${BUCKET_LABELS[b] || b} ${Math.round((n / shown.length) * 100)}%`);
    dEls.mixSummary.textContent = `Mix on screen: ${parts.join(" · ")}`;
    dEls.mixSummary.hidden = false;
  } else {
    dEls.mixSummary.hidden = true;
  }

  const needsDecision = discovered.filter((j) => ["new", "queued", "tailored"].includes(j.status)).length;
  dEls.count.textContent = needsDecision;
  dEls.count.hidden = needsDecision === 0;
}

// Search is a server query now, so it is debounced rather than fired on every
// keystroke — the request runs over the whole table, not just the loaded page.
let searchTimer = null;
dEls.search.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    visibleCount = PAGE_SIZE;
    loadDiscovered();
  }, 220);
});
dEls.statusFilter.addEventListener("change", () => {
  visibleCount = PAGE_SIZE;
  loadDiscovered();
});
dEls.loadMore.addEventListener("click", () => {
  visibleCount += PAGE_SIZE;
  renderDiscovered();
});

// ---------------------------------------------------------------------------
// Row actions (req. 32)
// ---------------------------------------------------------------------------
dEls.body.addEventListener("click", async (e) => {
  const button = e.target.closest("button[data-action]");
  if (!button) return;
  const id = Number(button.dataset.id);
  const job = discovered.find((j) => j.id === id);
  if (!job) return;

  try {
    switch (button.dataset.action) {
      case "tailor":
        await tailorAndDownload(job, button);
        break;
      case "download":
        downloadDraft(job.id);
        break;
      case "draft":
        await openDraftModal(job);
        break;
      case "reject": {
        const ok = await confirmDialog(
          "Reject this posting? It won't be offered for tailoring again unless you restore it.",
          { title: "Reject posting?", confirmLabel: "Reject", danger: true }
        );
        if (!ok) return;
        await setStatus(id, "rejected");
        showToast("Rejected — moved out of your feed.", { type: "success" });
        break;
      }
      case "dismiss":
        await setStatus(id, "dismissed");
        showToast("Dismissed.", { type: "info" });
        break;
      case "reset":
        await setStatus(id, "new");
        showToast("Restored to New.", { type: "success" });
        break;
      case "apply":
        await markApplied(job);
        break;
    }
  } catch (err) {
    showToast(err.message, { type: "error" });
  }
});

async function setStatus(id, status) {
  await api(`/api/discovered/${id}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  await loadDiscovered();
}

// req. 32: creates the row in the existing applied log, pre-filled, and links
// the two records. Refreshes the applied view so it shows up there immediately.
async function markApplied(job) {
  const ok = await confirmDialog(`Log an application to ${job.title} at ${job.company}?`, {
    title: "Mark as applied?",
    confirmLabel: "Log application",
  });
  if (!ok) return;
  await api(`/api/discovered/${job.id}/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  showToast(`Logged application to ${job.company}.`, { type: "success" });
  await loadDiscovered();
  // app.js owns the applied log; ask it to reload rather than duplicating it.
  if (typeof window.reloadJobs === "function") window.reloadJobs();
}

// ---------------------------------------------------------------------------
// Tailoring — generate and hand back the file (req. 21-22)
// ---------------------------------------------------------------------------
// Clicking "Tailor" is the approval. It names one posting and generates against
// that posting only; the state machine still refuses to reach `tailored` by any
// other route. What it no longer does is make the user read a prompt preview
// and click a second confirm button to get to the same place.
//
// The two things that preview *did* carry — the injection-sanitizer warning
// (req. 24) and the traceability flags (req. 23) — come back with the response
// and are surfaced as toasts, so removing the screen does not remove the
// signals. "Review" on a tailored row still opens the full flag view.
function downloadDraft(id) {
  // A real navigation to an endpoint that sets Content-Disposition, so the
  // browser names the file from the server rather than from a blob URL.
  const a = document.createElement("a");
  a.href = `/api/discovered/${id}/draft/download`;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

async function tailorAndDownload(job, button) {
  const cell = button.closest(".row-actions");
  const previous = cell.innerHTML;
  // The call is a live Claude Code invocation — minutes, not milliseconds. The
  // row has to show that it is working or the click reads as a no-op.
  cell.innerHTML = '<span class="row-working"><span class="row-spinner"></span>Tailoring…</span>';

  try {
    const result = await api(`/api/discovered/${job.id}/tailor`, { method: "POST" });
    if (!result.ok) throw new Error(result.error || "Tailoring failed.");

    downloadDraft(job.id);

    const sanitization = result.sanitization || {};
    const flagged = (result.traceability?.flagged || []).length;

    if (flagged > 0) {
      showToast(
        `Resume downloaded — but ${flagged} line(s) could not be traced to your base resume. ` +
          `Open “Review” on this row before you send it.`,
        { type: "warn", duration: 8000 }
      );
    } else {
      showToast(`Tailored resume downloaded for ${job.company}.`, { type: "success" });
    }
    // req. 24: never let a scrubbed posting pass silently.
    if (sanitization.injectionDetected) {
      showToast(
        `Heads up: injection patterns were neutralized in this posting before it reached Claude ` +
          `(${(sanitization.triggered || []).join(", ")}).`,
        { type: "warn", duration: 8000 }
      );
    }
  } catch (err) {
    // req. 28: the row is already back to `queued` server-side; surface why.
    cell.innerHTML = previous;
    showToast(`Tailoring failed: ${err.message}`, { type: "error", duration: 8000 });
  }
  await loadDiscovered();
}

// ---------------------------------------------------------------------------
// Draft review — traceability flags and the override audit trail (req. 23)
// ---------------------------------------------------------------------------
async function openDraftModal(job) {
  activeJob = job;
  dEls.draftStatus.textContent = "";
  dEls.flagList.innerHTML = "";
  dEls.draftModal.hidden = false;
  dEls.draftPathLine.textContent = "Loading draft…";

  try {
    const data = await api(`/api/discovered/${job.id}/draft`);
    dEls.draftPathLine.textContent = `${job.title} — ${job.company} · ${data.job.resume_path}`;
    dEls.draftText.textContent = data.draft;
    dEls.baseResumeText.textContent = data.baseResume;

    const outstanding = data.traceability.flagged.filter((f) => !f.overridden);
    dEls.traceOk.hidden = outstanding.length > 0;
    dEls.traceWarn.hidden = outstanding.length === 0;
    dEls.flagCount.textContent = outstanding.length;

    renderFlags(job.id, data.traceability.flagged, data.overrides);
  } catch (err) {
    dEls.draftPathLine.textContent = `Could not load the draft: ${err.message}`;
  }
}

function renderFlags(jobId, flags, overrides) {
  if (flags.length === 0) {
    dEls.flagList.innerHTML = "";
    return;
  }
  const reasonFor = (text) => overrides.find((o) => o.flagged_text === text)?.reason;

  dEls.flagList.innerHTML = flags
    .map((flag) => {
      const why = flag.reasons.includes("unsupported-number")
        ? `numbers not in your base resume: ${esc(flag.unsupportedNumbers.join(", "))}`
        : `only ${Math.round(flag.score * 100)}% of this line traces back to your base resume`;

      if (flag.overridden) {
        return `
          <div class="flag flag-resolved">
            <div class="flag-line">${esc(flag.text)}</div>
            <div class="flag-why">Approved — reason: ${esc(reasonFor(flag.text) || "")}</div>
          </div>`;
      }
      return `
        <div class="flag" data-flag="${esc(flag.text)}">
          <div class="flag-line">${esc(flag.text)}</div>
          <div class="flag-why">Line ${flag.line} · ${why}</div>
          <div class="flag-actions">
            <input type="text" class="flag-reason" placeholder="Why is this line accurate? (required to approve)" />
            <button type="button" class="row-action primary" data-approve="${esc(flag.text)}" data-id="${jobId}">Approve anyway</button>
          </div>
        </div>`;
    })
    .join("");
}

// req. 23: approving a flagged line requires a short reason, written to the
// overrides table. There is no path that clears a flag without one.
dEls.flagList.addEventListener("click", async (e) => {
  const button = e.target.closest("button[data-approve]");
  if (!button) return;

  const wrap = button.closest(".flag");
  const reason = wrap.querySelector(".flag-reason").value.trim();
  if (!reason) {
    dEls.draftStatus.textContent = "A reason is required to approve a flagged line.";
    wrap.querySelector(".flag-reason").focus();
    return;
  }

  try {
    await api(`/api/discovered/${button.dataset.id}/overrides`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ flagged_text: button.dataset.approve, reason }),
    });
    dEls.draftStatus.textContent = "Override recorded.";
    await openDraftModal(activeJob);
  } catch (err) {
    dEls.draftStatus.textContent = err.message;
  }
});

dEls.downloadFromDraft.addEventListener("click", () => {
  if (activeJob) downloadDraft(activeJob.id);
});

dEls.markAppliedFromDraft.addEventListener("click", async () => {
  if (!activeJob) return;
  try {
    await markApplied(activeJob);
    dEls.draftModal.hidden = true;
  } catch (err) {
    dEls.draftStatus.textContent = err.message;
  }
});

// ---------------------------------------------------------------------------
// Modal plumbing
// ---------------------------------------------------------------------------
document.querySelectorAll("[data-close-modal]").forEach((btn) => {
  btn.addEventListener("click", () => {
    btn.closest(".modal-backdrop").hidden = true;
  });
});

document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) backdrop.hidden = true;
  });
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  document.querySelectorAll(".modal-backdrop").forEach((m) => (m.hidden = true));
});
