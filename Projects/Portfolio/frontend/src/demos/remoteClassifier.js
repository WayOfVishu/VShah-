/** The remote classifier, wired to the FastAPI backend.
 *
 *  This is the reason the site has a Python process at all: the rules running
 *  behind it are a direct port of the Jobs Web App's lib/remote.js, verified
 *  case-for-case against the original, so what a visitor types is judged by the
 *  real thing.
 *
 *  Every verdict comes back with its evidence — the phrase that decided it and
 *  where it was found — because a classifier you cannot interrogate is just an
 *  opinion. */

import { api, ApiError } from '../lib/api.js';
import { esc, $ } from '../lib/dom.js';

const DEBOUNCE_MS = 350;

const MARKS = {
  qualifies: '✓',
  hybrid: '◑',
  'us-fenced': '✕',
  'not-remote': '—',
};

const KIND_LABEL = {
  claims: 'claims remote',
  fully_remote: 'explicit full remote',
  hybrid: 'hybrid signal',
  scope_canada: 'scope · canada',
  scope_us: 'scope · united states',
  scope_global: 'scope · global',
};

/** Show the matched phrase with a little context on either side. */
function snippet(text, start, end, pad = 44) {
  if (!text || start >= end || end > text.length) return '';
  const from = Math.max(0, start - pad);
  const to = Math.min(text.length, end + pad);
  const pre = (from > 0 ? '…' : '') + text.slice(from, start);
  const hit = text.slice(start, end);
  const post = text.slice(end, to) + (to < text.length ? '…' : '');
  return `${esc(pre)}<mark>${esc(hit)}</mark>${esc(post)}`;
}

export function mountRemoteClassifier(root) {
  root.innerHTML = `
    <div class="demo">
      <div class="demo-head">
        <div class="demo-title">
          <span>JOBS.WORKBENCH</span>
          <span style="color:var(--faint)">/</span>
          <span>remote classifier</span>
        </div>
        <span class="demo-badge live" data-role="badge">checking…</span>
      </div>

      <div class="demo-grid">
        <div class="demo-input">
          <div class="samples" data-role="samples"></div>
          <p class="sample-note" data-role="note"></p>

          <div class="field">
            <label for="rc-location">Location field</label>
            <input id="rc-location" type="text" spellcheck="false"
                   placeholder="Remote - Canada" data-role="location">
          </div>

          <div class="field">
            <label for="rc-desc">Posting description</label>
            <textarea id="rc-desc" spellcheck="false"
                      placeholder="Paste the body of a job posting…"
                      data-role="description"></textarea>
          </div>
        </div>

        <div class="demo-output" data-role="output">
          <p class="mono muted">Pick a sample, or paste a posting.</p>
        </div>
      </div>

      <div class="demo-foot" data-role="foot">
        Runs the same three gates as the real pipeline — claims remote, not
        secretly hybrid, not US-fenced — ported to Python and checked
        case-for-case against the original JavaScript.
      </div>
    </div>`;

  const els = {
    badge: $('[data-role="badge"]', root),
    samples: $('[data-role="samples"]', root),
    note: $('[data-role="note"]', root),
    location: $('[data-role="location"]', root),
    description: $('[data-role="description"]', root),
    output: $('[data-role="output"]', root),
  };

  let timer = null;
  let seq = 0; // guards against a slow response overwriting a newer one

  /* ---------------------------------------------------------- rendering */

  function renderResult(data) {
    const location = els.location.value;
    const description = els.description.value;

    const gates = data.gates
      .map(
        (g, i) => `
        <div class="gate ${g.passed ? 'pass' : 'fail'}" style="animation-delay:${i * 90}ms">
          <span class="gate-mark">${g.passed ? '✓' : '✕'}</span>
          <span class="gate-body">
            <strong>${esc(g.label)}</strong>
            <span>${esc(g.detail)}</span>
          </span>
        </div>`
      )
      .join('');

    const evidence = data.evidence.length
      ? `<div class="evidence-title">Evidence</div>
         <div class="evidence">
           ${data.evidence
             .map((e) => {
               const source = e.where === 'header' ? location : description;
               const body = snippet(source, e.start, e.end) || esc(e.match);
               return `<div class="ev">
                         <span class="ev-kind">${esc(KIND_LABEL[e.kind] || e.kind)}
                           <span class="where">· ${esc(e.where)}</span></span>
                         ${body}
                       </div>`;
             })
             .join('')}
         </div>`
      : '';

    els.output.innerHTML = `
      <div class="verdict" data-verdict="${esc(data.verdict)}">
        <span class="verdict-mark">${MARKS[data.verdict] || '?'}</span>
        <span class="verdict-text">
          <strong>${esc(data.headline)}</strong>
          <span>scope: ${esc(data.scope)} · qualifies: ${data.qualifies}</span>
        </span>
      </div>
      <div class="gates">${gates}</div>
      ${evidence}`;
  }

  function renderError(message) {
    els.output.innerHTML = `
      <div class="demo-error">
        <strong>API unreachable.</strong><br>${esc(message)}<br><br>
        The rest of the site is static and unaffected — only this panel needs
        the Python backend.
      </div>`;
  }

  /* ------------------------------------------------------------ requests */

  async function classify() {
    const location = els.location.value.trim();
    const description = els.description.value.trim();

    if (!location && !description) {
      els.output.innerHTML = '<p class="mono muted">Pick a sample, or paste a posting.</p>';
      return;
    }

    const mine = ++seq;
    try {
      const data = await api.classifyRemote({
        location,
        remote_status: location.toLowerCase().includes('remote') ? 'remote' : '',
        description,
      });
      if (mine !== seq) return; // a newer keystroke already won
      renderResult(data);
    } catch (err) {
      if (mine !== seq) return;
      renderError(err instanceof ApiError ? err.message : String(err));
    }
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(classify, DEBOUNCE_MS);
  }

  /* ------------------------------------------------------------- samples */

  function loadSample(sample, btn) {
    els.samples.querySelectorAll('.sample-btn').forEach((b) => b.classList.remove('is-active'));
    btn.classList.add('is-active');
    els.note.textContent = sample.note;
    els.location.value = sample.location;
    els.description.value = sample.description;
    classify();
  }

  async function boot() {
    try {
      const samples = await api.remoteSamples();
      els.badge.textContent = 'live';
      els.badge.className = 'demo-badge live';

      els.samples.innerHTML = samples
        .map((s, i) => `<button class="sample-btn" type="button" data-i="${i}">${esc(s.label)}</button>`)
        .join('');

      els.samples.addEventListener('click', (e) => {
        const btn = e.target.closest('.sample-btn');
        if (!btn) return;
        loadSample(samples[Number(btn.dataset.i)], btn);
      });

      // Open on the case that makes the point: the boilerplate trap.
      const first = els.samples.querySelector('.sample-btn');
      if (first) loadSample(samples[0], first);
    } catch (err) {
      els.badge.textContent = 'offline';
      els.badge.className = 'demo-badge offline';
      els.samples.innerHTML = '';
      els.note.textContent = 'Samples load from the backend, which is not answering right now.';
      renderError(err instanceof ApiError ? err.message : String(err));
    }
  }

  els.location.addEventListener('input', schedule);
  els.description.addEventListener('input', schedule);

  boot();
}
