# Portfolio

My professional portfolio. A FastAPI backend, a Vite + vanilla-JS frontend, and
a hand-written WebGL field behind the hero.

```
cd backend  && py -m venv .venv && ./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
cd frontend && npm install
```

Two processes in development, one in production:

```
# dev — API on :8000 with autoreload, site on :5173 with HMR
cd backend  && ./.venv/Scripts/python.exe run.py
cd frontend && npm run dev

# production — build the site, then serve everything from one process
cd frontend && npm run build
cd backend  && ./.venv/Scripts/python.exe run.py --serve-static
```

---

## The one architectural decision worth knowing

**Page content is bundled at build time. Only the demos call the API.**

`vite.config.js` aliases `@data` to `backend/app/data/`, so `main.js` imports
the content JSON directly and Vite inlines it into the bundle. Three things
follow from that:

- the page paints complete on the first script evaluation — no loading state,
  no layout shift, no spinner
- the site is fully functional with the backend switched **off**
- `frontend/dist/` is a plain static site, so it can live on a free CDN while
  only the Python process needs paid hosting

The API serves the same JSON at `/api/summary`, so there is still exactly one
source of truth. The frontend just reads it earlier than a fetch would.

The backend therefore exists for one reason: **the live demos**. That is also
why it is Python rather than a second Node process — the stocks forecaster and
the LoL build suggestor both need `pandas`/`scikit-learn` inference endpoints,
and this is where they will land.

---

## Layout

```
Portfolio/
├── backend/
│   ├── app/
│   │   ├── main.py          FastAPI app; mounts frontend/dist in --serve-static
│   │   ├── content.py       loads + caches app/data/*.json
│   │   ├── data/            ALL site copy lives here — edit content, not markup
│   │   │   ├── profile.json      name, summary, hero metrics, contact links
│   │   │   ├── projects.json     projects + full case studies
│   │   │   ├── experience.json   roles, highlights, proprietary flags
│   │   │   ├── skills.json       skills matrix, 1-5 levels
│   │   │   └── education.json    degrees + notable
│   │   ├── demos/remote.py  the remote classifier (real logic, see below)
│   │   └── routers/         content.py, demos.py
│   ├── requirements.txt     runtime deps
│   ├── requirements-dev.txt adds pytest + httpx
│   └── run.py               entry point
└── frontend/
    ├── index.html           structural shell only; sections are filled by JS
    └── src/
        ├── main.js          imports content, paints, then wires behaviour
        ├── gl/field.js      the WebGL2 hero field
        ├── lib/             dom, api, motion (reveals/counters/nav/clock)
        ├── sections/render.js   all section markup
        └── demos/           remoteClassifier.js, telemetry.js
```

### Editing the site

Almost everything is a content edit, not a code edit. Change a file in
`backend/app/data/`, then `npm run build`. Set `PORTFOLIO_RELOAD=1` to make the
API re-read the files on every request while you are writing.

---

## The live demo is real

`backend/app/demos/remote.py` is a direct port of the Jobs Web App's
`lib/remote.js` — the classifier that decides whether a job posting is
genuinely remote, secretly hybrid, or US-fenced. It was verified against the
original by running both over the same six cases and diffing `scope`,
`isHybrid`, and `qualifies`. All six matched.

Every verdict returns its **evidence**: the phrase that decided it, which field
it came from, and its offset, so the UI can highlight it in the input. A
classifier you cannot interrogate is just an opinion.

The six samples are each chosen because they break a naive implementation —
the boilerplate trap, the pronoun trap ("build things with us" is not the
United States), Canada-or-US, and so on.

**If the classifier changes in the Jobs Web App, change it here too.** The
patterns are the contract between the two.

The second panel (telemetry readout) is openly labelled *simulated* — the real
diagnostics engine reads `/proc`, which a browser does not have.

---

## What is deliberately not here

Work done for Pembina and for the CPKC capstone is employer-owned. The
experience section carries outcomes and scope — the same level of detail as a
résumé — and is marked "employer-owned, outcomes only, no internals". There is
no source, no architecture detail, and no client data for those roles, and
there should never be. Case studies exist only for projects I own outright.

---

## Accessibility and performance notes

- No runtime JS dependencies. The whole bundle is ~44 KB (17 KB gzipped).
- The WebGL field degrades three ways: no WebGL2 falls back to the CSS
  gradient, `prefers-reduced-motion` draws one static frame, and scrolling the
  hero offscreen stops the render loop entirely.
- All motion is `IntersectionObserver` + `rAF`. No scroll handlers doing layout
  reads.
- `prefers-reduced-motion` collapses every transition to ~0s and resolves
  reveals to their final state rather than leaving content invisible.
- Demo input is escaped before it reaches `innerHTML`; site copy is trusted.

---

## Tests

```
cd backend && ./.venv/Scripts/python.exe -m pytest
```
