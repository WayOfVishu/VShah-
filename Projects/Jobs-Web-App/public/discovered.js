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
  hideApplied: document.getElementById("hideApplied"),
  mixSummary: document.getElementById("mixSummary"),
  summary: document.getElementById("discoveredSummary"),
  empty: document.getElementById("discoveredEmpty"),
  loadMore: document.getElementById("loadMore"),

  tailorModal: document.getElementById("tailorModal"),
  tailorJobLine: document.getElementById("tailorJobLine"),
  injectionNotice: document.getElementById("injectionNotice"),
  injectionRules: document.getElementById("injectionRules"),
  htmlNotice: document.getElementById("htmlNotice"),
  outputPathText: document.getElementById("outputPathText"),
  promptPreview: document.getElementById("promptPreview"),
  tailorStatus: document.getElementById("tailorStatus"),
  confirmGenerate: document.getElementById("confirmGenerate"),

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
// Data loading
// ---------------------------------------------------------------------------
async function loadDiscovered() {
  try {
    // Archived rows are hidden by default (req. 31); only fetched when asked for.
    const params = new URLSearchParams({
      includeArchived: dEls.statusFilter.value === "archived" ? "1" : "0",
      sort: dEls.sortMode.value,
      maxAgeDays: dEls.freshness.value,
      hideApplied: dEls.hideApplied.checked ? "1" : "0",
    });
    // Looking specifically at applied or archived rows means the "hide applied"
    // default would empty the table out from under you.
    if (["applied", "archived"].includes(dEls.statusFilter.value)) params.set("hideApplied", "0");
    if (dEls.bucketFilter.value) params.set("bucket", dEls.bucketFilter.value);

    const payload = await api(`/api/discovered?${params}`);
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

// Sorting, freshness, bucket and hide-applied are all applied server-side, so
// each needs a refetch rather than a re-render.
[dEls.sortMode, dEls.freshness, dEls.bucketFilter, dEls.hideApplied].forEach((el) =>
  el.addEventListener("change", loadDiscovered)
);

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
function filtered() {
  const q = dEls.search.value.trim().toLowerCase();
  const status = dEls.statusFilter.value;

  return discovered.filter((job) => {
    if (status === "active") {
      // The default: rows that still need a decision from the user.
      if (!["new", "queued", "generating", "tailored"].includes(job.status)) return false;
    } else if (status !== "all" && job.status !== status) {
      return false;
    }
    if (!q) return true;
    return [job.title, job.company, job.location, (job.sources || []).join(" ")]
      .join(" ")
      .toLowerCase()
      .includes(q);
  });
}

function actionsFor(job) {
  const btn = (action, label, cls = "") =>
    `<button type="button" class="row-action ${cls}" data-action="${action}" data-id="${job.id}">${label}</button>`;

  switch (job.status) {
    case "new":
      return btn("tailor", "Tailor", "primary") + btn("dismiss", "Dismiss") + btn("apply", "Applied");
    case "queued":
      return btn("tailor", "Review &amp; generate", "primary") + btn("reject", "Reject") + btn("apply", "Applied");
    case "generating":
      return '<span class="hint">working…</span>';
    case "tailored":
      return btn("draft", "View draft", "primary") + btn("apply", "Applied") + btn("dismiss", "Dismiss");
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
  const freshnessLabel = dEls.freshness.options[dEls.freshness.selectedIndex].textContent;
  let msg = `No discovered postings match these filters. Hit <strong>Refresh job searches</strong> to pull new ones`;
  if (dEls.freshness.value !== "0") msg += `, widen &ldquo;${esc(freshnessLabel)}&rdquo;`;
  msg += `, or edit <code>config/preferences.json</code>.`;
  return msg;
}

function renderDiscovered(animate = true) {
  const rows = filtered();
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

dEls.search.addEventListener("input", () => {
  visibleCount = PAGE_SIZE;
  renderDiscovered(false);
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
        await openTailorModal(job);
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
// The approval gate (req. 21-22)
// ---------------------------------------------------------------------------
async function openTailorModal(job) {
  activeJob = job;
  dEls.tailorStatus.textContent = "";
  dEls.confirmGenerate.disabled = false;
  dEls.tailorJobLine.textContent = `${job.title} — ${job.company}${job.location ? ` (${job.location})` : ""}`;
  dEls.promptPreview.textContent = "Building preview…";
  dEls.tailorModal.hidden = false;

  try {
    const preview = await api(`/api/discovered/${job.id}/preview`);
    dEls.promptPreview.textContent = preview.prompt;
    dEls.outputPathText.textContent = preview.outputPath;

    // req. 24: tell the user their posting was scrubbed rather than silently
    // changing what they're approving.
    const s = preview.sanitization || {};
    dEls.injectionNotice.hidden = !s.injectionDetected;
    dEls.injectionRules.textContent = s.injectionDetected ? ` Rules fired: ${s.triggered.join(", ")}.` : "";
    dEls.htmlNotice.hidden = !s.htmlStripped;
  } catch (err) {
    dEls.promptPreview.textContent = `Could not build the prompt: ${err.message}`;
    dEls.confirmGenerate.disabled = true;
  }
}

dEls.confirmGenerate.addEventListener("click", async () => {
  if (!activeJob) return;
  const job = activeJob;
  dEls.confirmGenerate.disabled = true;

  try {
    // The row must be `queued` before it can be tailored — that's the state
    // machine's gate, so a `new` row is queued by this same confirming click.
    if (job.status === "new") await api(`/api/discovered/${job.id}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "queued" }),
    });

    dEls.tailorStatus.textContent = "Generating — this can take a couple of minutes…";
    const result = await api(`/api/discovered/${job.id}/tailor`, { method: "POST" });

    dEls.tailorModal.hidden = true;
    await loadDiscovered();
    const updated = discovered.find((j) => j.id === job.id);
    if (updated) await openDraftModal(updated);
  } catch (err) {
    // req. 28: the row is already back to `queued` server-side; surface why.
    dEls.tailorStatus.textContent = `Failed: ${err.message}`;
    dEls.confirmGenerate.disabled = false;
    await loadDiscovered();
  }
});

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
