// Shared UI helpers used by both app.js (applied log) and discovered.js
// (discovered postings): toasts and an in-theme confirm dialog, so neither
// ever falls back to the browser's native alert()/confirm().

const toastStack = document.getElementById("toastStack");

function showToast(message, { type = "info", duration = 3200 } = {}) {
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.textContent = message;
  el.title = "Dismiss";
  toastStack.appendChild(el);
  requestAnimationFrame(() => el.classList.add("is-visible"));

  let timer;
  const remove = () => {
    clearTimeout(timer);
    el.classList.remove("is-visible");
    el.addEventListener("transitionend", () => el.remove(), { once: true });
  };
  timer = setTimeout(remove, duration);
  el.addEventListener("click", remove);
}

const confirmModal = document.getElementById("confirmModal");
const confirmTitleEl = document.getElementById("confirmTitle");
const confirmMessageEl = document.getElementById("confirmMessage");
const confirmOkBtn = document.getElementById("confirmOk");
const confirmCancelBtn = document.getElementById("confirmCancel");

// Replaces window.confirm(): resolves true/false, matches the dashboard's
// theme, and doesn't block the JS thread while it waits.
function confirmDialog(message, { title = "Are you sure?", confirmLabel = "Confirm", danger = false } = {}) {
  return new Promise((resolve) => {
    confirmTitleEl.textContent = title;
    confirmMessageEl.textContent = message;
    confirmOkBtn.textContent = confirmLabel;
    confirmOkBtn.classList.toggle("btn-danger", danger);
    confirmModal.hidden = false;
    confirmOkBtn.focus();

    function cleanup(result) {
      confirmModal.hidden = true;
      confirmOkBtn.removeEventListener("click", onOk);
      confirmCancelBtn.removeEventListener("click", onCancel);
      confirmModal.removeEventListener("click", onBackdrop);
      resolve(result);
    }
    function onOk() { cleanup(true); }
    function onCancel() { cleanup(false); }
    function onBackdrop(e) { if (e.target === confirmModal) cleanup(false); }

    confirmOkBtn.addEventListener("click", onOk);
    confirmCancelBtn.addEventListener("click", onCancel);
    confirmModal.addEventListener("click", onBackdrop);
  });
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !confirmModal.hidden) confirmCancelBtn.click();
});

// Eases a number element's displayed value toward `to` instead of snapping,
// so the header stats read as live rather than static labels.
function animateNumber(el, to, { decimals = 0, duration = 500 } = {}) {
  const from = Number.parseFloat(el.dataset.raw ?? el.textContent) || 0;
  el.dataset.raw = to;
  if (from === to) {
    el.textContent = to.toFixed(decimals);
    return;
  }
  const start = performance.now();
  function tick(now) {
    const p = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = (from + (to - from) * eased).toFixed(decimals);
    if (p < 1) requestAnimationFrame(tick);
    else el.textContent = to.toFixed(decimals);
  }
  requestAnimationFrame(tick);
}

// Applies a short staggered entrance to the rows of a just-rebuilt <tbody>.
// Skipped on typing-driven re-renders (see callers) so search doesn't replay
// it on every keystroke.
function staggerRows(tbody, { maxDelayIndex = 20, stepMs = 16 } = {}) {
  [...tbody.children].forEach((row, i) => {
    row.style.animationDelay = `${Math.min(i, maxDelayIndex) * stepMs}ms`;
  });
}

window.showToast = showToast;
window.confirmDialog = confirmDialog;
window.animateNumber = animateNumber;
window.staggerRows = staggerRows;
