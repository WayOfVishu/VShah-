/** Every section's markup, built from the bundled content JSON.
 *
 *  Copy here is trusted (it is my own data files), so template literals are
 *  used directly. The one place untrusted text appears is the demo, which
 *  escapes it — see demos/remoteClassifier.js. */

import { fill, delay, fmtRange, esc } from '../lib/dom.js';

const ICONS = {
  github:
    '<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z"/></svg>',
  linkedin:
    '<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M3.6 5.3H.9V16h2.7V5.3ZM2.25 0a1.6 1.6 0 1 0 0 3.2 1.6 1.6 0 0 0 0-3.2ZM16 9.9c0-2.9-1.55-4.25-3.62-4.25-1.67 0-2.42.92-2.84 1.56V5.3H6.85c.04.79 0 10.7 0 10.7h2.69v-5.98c0-.24.02-.48.09-.65.19-.48.63-.98 1.37-.98.97 0 1.35.74 1.35 1.81V16H16V9.9Z"/></svg>',
  mail:
    '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><rect x="1" y="3" width="14" height="10" rx="1.5"/><path d="m1.6 4 6.4 4.6L14.4 4"/></svg>',
};

const arrow = '<span class="arrow" aria-hidden="true">→</span>';

/* -------------------------------------------------------------------- nav */

export function renderNav(el, profile) {
  const links = [
    ['work', 'Work'],
    ['demo', 'Live demo'],
    ['experience', 'Experience'],
    ['stack', 'Stack'],
    ['contact', 'Contact'],
  ];

  fill(el, `
    <a class="nav-brand" href="#top">
      <span class="status-dot" aria-hidden="true"></span>
      ${esc(profile.callsign)}
    </a>
    <nav class="nav-links" aria-label="Sections">
      ${links.map(([id, label]) => `<a href="#${id}">${label}</a>`).join('')}
    </nav>
    <div class="nav-clock" id="clock" aria-label="Local time in Calgary"></div>
  `);
}

/* ------------------------------------------------------------------- hero */

export function renderHero(el, profile) {
  const [first, ...rest] = profile.name.split(' ');

  fill(el, `
    <!-- The canvas is rendered here rather than sitting in index.html,
         because this call owns the hero's innerHTML and would otherwise
         delete it. -->
    <canvas id="field" aria-hidden="true"></canvas>

    <div class="shell hero-inner">
      <div class="hero-status" data-reveal>
        <span class="live">● AVAILABLE</span>
        <span class="sep">/</span>
        <span>${esc(profile.location)}</span>
        <span class="sep">/</span>
        <span>${esc(profile.subtitle)}</span>
      </div>

      <h1>
        <span class="line"><span>${esc(first)}</span></span>
        <span class="line"><span class="dim">${esc(rest.join(' '))}</span></span>
      </h1>

      <p class="hero-role" data-reveal style="${delay(2)}">${esc(profile.title)}</p>

      <p class="hero-summary" data-reveal style="${delay(3)}">${esc(profile.summary)}</p>

      <div class="hero-actions" data-reveal style="${delay(4)}">
        <a class="btn btn-primary" href="#work">See the work ${arrow}</a>
        <a class="btn" href="#demo">Try a live demo ${arrow}</a>
      </div>

      <div class="metrics" data-reveal style="${delay(5)}">
        ${profile.metrics
          .map(
            (m) => `
          <div class="metric">
            <span class="metric-value"
                  data-count-to="${m.value}"
                  data-count-format="${m.format}"
                  data-count-display="${esc(m.display)}">${esc(m.display)}</span>
            <span class="metric-label">${esc(m.label)}</span>
            <span class="metric-caption">${esc(m.caption)}</span>
          </div>`
          )
          .join('')}
      </div>
    </div>

    <div class="scroll-cue" aria-hidden="true">
      <span class="rail"></span>
      Scroll
    </div>
  `);
}

/* --------------------------------------------------------------- projects */

function caseStudyHtml(p) {
  const cs = p.caseStudy;
  if (!cs || !cs.approach?.length) return '';

  const block = (title, body) => `
    <div class="case-block">
      <h4>${title}</h4>
      ${body}
    </div>`;

  return `
    <div class="case">
      <div class="case-inner">
        <div class="case-body">
          ${block('The problem', `<p>${esc(cs.problem)}</p>`)}
          ${block(
            'Approach',
            cs.approach
              .map(
                (s) => `
              <div class="step">
                <h5>${esc(s.head)}</h5>
                <p>${esc(s.body)}</p>
              </div>`
              )
              .join('')
          )}
          ${
            cs.deepDive
              ? block(
                  'Worth a closer look',
                  `<div class="deep-dive">
                     <h5>${esc(cs.deepDive.head)}</h5>
                     <p>${esc(cs.deepDive.body)}</p>
                     <div class="result">${esc(cs.deepDive.result)}</div>
                   </div>`
                )
              : ''
          }
          ${
            cs.results?.length
              ? block(
                  'Result',
                  `<ul class="case-list">${cs.results.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>`
                )
              : ''
          }
          ${
            cs.learned?.length
              ? block(
                  'What it taught me',
                  `<ul class="case-list">${cs.learned.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>`
                )
              : ''
          }
        </div>
      </div>
    </div>`;
}

export function renderProjects(el, projects) {
  fill(el, projects
    .map((p, i) => {
      const hasCase = Boolean(p.caseStudy?.approach?.length);
      const repo = p.links?.find((l) => l.kind === 'repo');

      return `
      <article class="card ${p.status === 'planned' ? 'is-planned' : ''}"
               data-reveal style="${delay(i)}" id="project-${p.slug}">
        <div class="card-top">
          <span class="card-codename">${esc(p.codename)}</span>
          <span class="status" data-status="${esc(p.status)}">${esc(p.statusLabel)}</span>
        </div>

        <h3>${esc(p.name)}</h3>
        <p class="card-tagline">${esc(p.tagline)}</p>
        <p class="card-summary">${esc(p.summary)}</p>

        ${
          p.metrics?.length
            ? `<div class="card-metrics">
                 ${p.metrics
                   .map(
                     (m) => `<div class="card-metric">
                                <strong>${esc(m.display)}</strong>
                                <span>${esc(m.label)}</span>
                              </div>`
                   )
                   .join('')}
               </div>`
            : ''
        }

        <div class="chips">
          ${p.stack.map((s) => `<span class="chip">${esc(s)}</span>`).join('')}
        </div>

        <div class="card-actions">
          ${
            hasCase
              ? `<button class="link-btn case-toggle" aria-expanded="false"
                         aria-controls="case-${p.slug}">Read the case study ${arrow}</button>`
              : `<button class="link-btn" disabled>Case study pending</button>`
          }
          ${repo ? `<a class="link-btn" href="${esc(repo.url)}" target="_blank" rel="noopener noreferrer">${esc(repo.label)} ${arrow}</a>` : ''}
          ${p.demo ? `<a class="link-btn" href="#demo">Live demo ${arrow}</a>` : ''}
        </div>

        <div id="case-${p.slug}">${caseStudyHtml(p)}</div>
      </article>`;
    }));

  // Expand/collapse. The grid-template-rows 0fr -> 1fr trick animates to
  // content height without measuring anything in JS.
  el.addEventListener('click', (e) => {
    const btn = e.target.closest('.case-toggle');
    if (!btn) return;
    const card = btn.closest('.card');
    const open = card.classList.toggle('is-open');
    btn.setAttribute('aria-expanded', String(open));
    btn.innerHTML = open ? `Collapse ${arrow}` : `Read the case study ${arrow}`;
  });
}

/* ------------------------------------------------------------- experience */

export function renderExperience(el, roles) {
  fill(el, roles
    .map((r, i) => `
      <article class="role ${r.current ? 'is-current' : ''}" data-reveal style="${delay(i)}">
        <div class="role-head">
          <h3>${esc(r.role)}</h3>
          <span class="role-dates">${fmtRange(r.start, r.end)}</span>
        </div>
        <p class="role-org">${esc(r.org)} · ${esc(r.location)}</p>
        ${r.note ? `<p class="role-note">↑ ${esc(r.note)}</p>` : ''}
        <p class="role-blurb">${esc(r.blurb)}</p>

        <div class="highlights">
          ${r.highlights
            .map(
              (h) => `<div class="hl">
                        <span class="hl-tag">${esc(h.tag)}</span>
                        <span class="hl-text">${esc(h.text)}</span>
                      </div>`
            )
            .join('')}
        </div>

        <div class="chips">
          ${r.stack.map((s) => `<span class="chip">${esc(s)}</span>`).join('')}
          ${r.proprietary ? `<span class="nda">🔒 Employer-owned — outcomes only, no internals</span>` : ''}
        </div>
      </article>`));
}

/* ----------------------------------------------------------------- skills */

export function renderSkills(el, groups) {
  fill(el, groups
    .map((g, i) => `
      <div class="skill-group" data-key="${esc(g.key)}" data-reveal style="${delay(i)}">
        <h3>${esc(g.group)}</h3>
        ${g.items
          .map(
            (s) => `
          <div class="skill">
            <div class="skill-row">
              <span class="skill-name">${esc(s.name)}</span>
              <span class="skill-dots" role="img" aria-label="${s.level} out of 5">
                ${Array.from({ length: 5 }, (_, k) =>
                  `<span class="skill-dot ${k < s.level ? 'on' : ''}" style="transition-delay:${k * 55}ms"></span>`
                ).join('')}
              </span>
            </div>
          </div>`
          )
          .join('')}
      </div>`));
}

/* -------------------------------------------------------------- education */

export function renderEducation(el, { education, notable }) {
  fill(el, `
    <div class="panel" data-reveal>
      <h3>Education</h3>
      ${education
        .map(
          (e) => `
        <div class="edu">
          <h4>${esc(e.credential)}</h4>
          <p class="where">${esc(e.school)} · ${esc(e.location)}</p>
          <p class="when">Completed ${esc(e.end)}</p>
          ${e.notes?.length ? `<ul>${e.notes.map((n) => `<li>${esc(n)}</li>`).join('')}</ul>` : ''}
        </div>`
        )
        .join('')}
    </div>

    <div class="panel" data-reveal style="${delay(1)}">
      <h3>Notable</h3>
      ${notable
        .map(
          (n) => `
        <div class="edu">
          <h4>${esc(n.title)}</h4>
          <p class="where">${esc(n.detail)}</p>
          ${
            n.url
              ? `<a class="link-btn" style="margin-top:.7rem" href="${esc(n.url)}"
                    target="_blank" rel="noopener noreferrer">${esc(n.linkLabel)} ${arrow}</a>`
              : ''
          }
        </div>`
        )
        .join('')}
    </div>
  `);
}

/* ---------------------------------------------------------------- contact */

export function renderContact(el, profile) {
  fill(el, `
    <div class="shell">
      <span class="eyebrow" data-reveal>Open to ${profile.seeking.length} kinds of role</span>
      <h2 data-reveal style="${delay(1)}">Let's build something<br>worth measuring.</h2>
      <p data-reveal style="${delay(2)}">
        Graduating December 2026 and looking for ${profile.seeking.slice(0, -1).join(', ')},
        or ${profile.seeking.at(-1)} roles. The fastest way to reach me is email.
      </p>
      <div class="contact-links" data-reveal style="${delay(3)}">
        ${profile.links
          .map(
            (l, i) => `
          <a class="btn ${i === 0 ? '' : ''}" href="${esc(l.url)}"
             ${l.icon === 'mail' ? '' : 'target="_blank" rel="noopener noreferrer"'}>
            ${ICONS[l.icon] || ''} ${esc(l.handle)}
          </a>`
          )
          .join('')}
      </div>
    </div>
  `);
}

/* ----------------------------------------------------------------- footer */

export function renderFooter(el, profile) {
  fill(el, `
    <span>© ${new Date().getFullYear()} ${esc(profile.name)} · Built with FastAPI, Vite, and hand-written WebGL</span>
    <span><a href="#top">Back to top ↑</a></span>
  `);
}
