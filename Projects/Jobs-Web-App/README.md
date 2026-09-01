# Jobs Web App

A local job-search workbench: it discovers postings, ranks them against your
stated preferences, tailors a resume against the ones you approve, and tracks
every application you send. One Express server, one SQLite file, no cloud
services and no scheduler — you run it when you want it.

Formed by merging the two halves that used to live apart, `Job-Board-Scraping`
and `Job-Tracking-Dash`. They already shared a database and the dashboard was
reaching across a directory boundary to `import()` the scraper's modules
through a hand-built `file://` URL; folding them together removed that seam.

```
npm install
npm start              # dashboard at http://localhost:3001
npm run discover       # pull new postings from every configured source
```

---

## The two views

**Applied log** — every application you have sent, with status, platform,
referral flag, notes, and the charts over the top of it. This is the record of
the search.

**Discovered** — postings the scraper found that you have not acted on yet, in
your preferred mix. Each row can be queued, tailored, dismissed, or marked
applied, which writes it into the applied log and links the two.

---

## What gets through the filters

Discovery is uncapped at the source: Tier 1 connectors pull a company's
*entire* public board. A single run over six companies returned 2,908 postings,
topped by *TIG Welder (Starship), Starbase TX*. The filters are what make that
number useful.

A posting is ingested only if **all** of these hold:

| Gate | Rule |
|---|---|
| Fresh | `posted_date` within `maxAgeDays` (3). Falls back to `first_seen_at` when a board gives no date. |
| Role | Title matches a `roleKeywords` entry, or names a graduate program. |
| Level | Title carries no `excludeTitleKeywords` marker — senior, staff, principal, lead, manager, intern. |
| Location | Resolves to one of your five locations. Off-list postings are dropped; postings with *no* stated location are kept and bucketed `unknown`. |
| Not yours already | Not already in the applied log, by apply URL or by normalized title + company. |

`npm run discover` reports each gate's toll separately, so a keyword list that
is too narrow stays distinguishable from a location list that is too narrow —
and from a connector that has quietly broken.

Freshness is enforced **twice**: at ingest, so stale postings never enter, and
again on every read, because a row ingested three days ago is stale today. The
database is a log; the feed is a view over it.

---

## How a posting is scored

`match_score` runs 0–1 and is 65% location, 35% keywords.

**Location** is your stated preference mix, normalized so your top choice
scores a flat 1.0 rather than its raw 0.5:

| | Weight | Score |
|---|---|---|
| Calgary | 50% | 1.00 |
| Edmonton | 20% | 0.40 |
| Remote | 15% | 0.30 |
| Vancouver | 10% | 0.20 |
| Seattle | 5% | 0.10 |

A posting listing several locations takes its **highest-weighted** one:
`Calgary, AB / Remote` is a Calgary job you may work remotely, not a remote job
that mentions Calgary. `Vancouver, WA` is a Portland suburb and buckets as
Seattle, not British Columbia.

**Keywords** are three independent signals — the role (50%), the new-grad level
(30%), and the Jan 2027 start window (20%). A title hit counts fully; a
description-only hit counts partially, because a posting that merely name-drops
"machine learning" is not an ML role.

**Work authorization.** You do not hold US authorization, so a US-fenced
posting — Seattle, or a remote role restricted to the US — that never mentions
sponsorship has its location score cut to 35%. It stays visible, flagged 🛂 in
the table, but it stops consuming your 5% Seattle share. Postings that do
mention visas or sponsorship keep their full weight.

---

## The balanced mix

Score alone would bury Seattle and Vancouver under Calgary forever. So the
default ordering is a **mix**, not a ranking: the feed is composed to your
stated proportions — about half Calgary, a fifth Edmonton, and so on — with
each location's own rows ordered best-first inside it.

It uses stride scheduling. The *k*-th best posting in a bucket of weight *w* is
handed the virtual position `(k + 0.5) / w`, and everything sorts by that.
Calgary at 0.5 emits a row every 2 positions, Seattle at 0.05 every 20 — the
50/20/15/10/5 split falls out by construction, with no need to know how long
the list is, and a bucket that runs dry simply stops appearing instead of
stalling the feed.

The header reports the mix actually on screen, so the configured percentages
can be checked against reality rather than taken on faith.

Three orderings are available: **Balanced mix** (default), **Best match first**
(flat `match_score`), and **Newest first**.

---

## Tuning it

Everything above is data, not code. Two config files, deliberately separate:

- **`config/preferences.json`** — what you want. Freshness window, role and
  level and timing keywords, seniority exclusions, location weights, work-auth
  handling, score weights. Every key is documented inline.
- **`config/sources.json`** — where to look. Company watchlist, Tier 2 search
  keywords, career pages.

They are separate because `npm run bootstrap-sources` **rewrites
`sources.json` wholesale**. It never touches `preferences.json`, so your
preferences survive a re-bootstrap.

After changing preferences, apply them to rows already in the database:

```
node scripts/rescore.js --dry-run   # report what would change
node scripts/rescore.js             # apply
```

Rescore **archives** rather than deletes, and leaves rows you have already
acted on alone — a config change should never quietly destroy a posting you
might want back, or undo your own decisions. Archived rows are one "Restore"
click away, or visible via the Archived status filter.

### A note on "Jan 2027"

It is not a Tier 2 search keyword. Job boards index titles and descriptions,
not start dates, so querying an API for `Jan 2027` returns almost nothing. It
is handled as a scoring signal instead (`timingKeywords`), which boosts a
posting that does mention the window without hiding the ones that don't.

---

## Layout

```
server.js                Express app + REST API (both views)
discover.js              CLI: npm run discover
config/
  preferences.json       what you want — filters, weights, keywords
  sources.json           where to look — watchlist, search terms
connectors/              one module per board (greenhouse, lever, ashby,
                         remotive, remoteok, weworkremotely, careerpage)
lib/
  normalize.js           each board's shape -> one unified posting schema
  dedup.js               fuzzy title+company+location matching across boards
  preferences.js         config loader with defaults
  scoring.js             location buckets, match_score, the balanced mix
  jobFilter.js           the ingest gate + already-applied matching
  statusMachine.js       the only authority on legal status transitions
  promptBuild.js         builds the tailoring prompt
  promptSanitize.js      strips injection attempts out of posting text
  tailorInvoke.js        runs the tailoring, handles failure fallback
  traceabilityCheck.js   flags resume claims not grounded in the base resume
  sourceHealth.js        per-source failure tracking for the banner
  rateLimiter.js         shared throttle across Tier 2 sources
db/
  migrate.js             applies migrations/*.sql once, in order
  migrations/            001 jobs · 002 discovered_jobs · 003 preferences
public/                  the dashboard (app.js = applied log, discovered.js =
                         discovered view)
scripts/
  bootstrap-sources.js   derive sources.json from your applied history
  rescore.js             re-apply preferences to existing rows
resume/                  your base resume + generated drafts (git-ignored)
jobs.db                  the single SQLite file both entry points share
```

`npm test` runs the suite — 94 tests, no network, no database of its own.

---

## Resume tailoring

Every generated draft passes a traceability check: claims that are not
grounded in `resume/base-resume.md` are flagged. A flagged line can only be
accepted by writing a short reason, which is recorded in the `overrides` table.
Nothing is rubber-stamped past a fabrication flag, and "Confirm & Generate" is
the single approval gate — there is no second prompt behind it.

---

## Known gaps

**The watchlist does not match your locations.** `tier1Watchlist` is SpaceX,
Canonical, Xsolla, StackAdapt, Turing, and Top Hat — none headquartered in
Alberta. Across all 2,908 postings ever discovered, exactly **five** mention
Calgary, all of them StackAdapt. A 50% Calgary preference cannot be satisfied
by sources that do not post Calgary jobs. Adding Calgary and Edmonton employers
to `config/sources.json` is the highest-value change available to this project.

**`match_score` has no feedback loop.** It reflects your stated preferences, not
which applications actually got replies. The applied log holds the data to
close that loop; nothing does it yet.

**Location parsing is pattern-based.** It handles the formats these boards
actually emit, including multi-city strings and the Vancouver WA/BC trap, but
it is regex over free text, not a geocoder. A novel format buckets as `unknown`
rather than guessing.
