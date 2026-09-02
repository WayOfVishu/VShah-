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
```

That is the whole surface. Discovery is not a second command any more: the
**Refresh job searches** button at the top of the Discovered view starts a run,
streams its output into the panel below the button, and reloads the feed when it
finishes. The server runs it as a child process, so the dashboard stays
responsive while Playwright works and a connector that crashes hard cannot take
the server down with it.

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
| Fresh | `posted_date` within `maxAgeDays`, whatever the dashboard's "Posted within" control is set to. Falls back to `first_seen_at` when a board gives no date. |
| Role | Title matches a `roleKeywords` entry, or names a graduate program. |
| Level | Title carries no `excludeTitleKeywords` marker — senior, staff, principal, lead, manager, intern. |
| Location | Resolves to one of your five locations. Off-list postings are dropped; postings with *no* stated location are kept and bucketed `unknown`. |
| Not yours already | Not already in the applied log, by apply URL or by normalized title + company. |

A run reports each gate's toll separately, so a keyword list that
is too narrow stays distinguishable from a location list that is too narrow —
and from a connector that has quietly broken.

Freshness is enforced **twice**: at ingest, so stale postings never enter, and
again on every read, because a row ingested three days ago is stale today. The
database is a log; the feed is a view over it.

---

## How a posting is scored

`match_score` runs 0–1 and is 65% location, 35% keywords.

**Location** is your stated preference mix, normalized so your top choice
scores a flat 1.0 rather than its raw 0.35:

| | Weight | Score |
|---|---|---|
| Calgary | 35% | 1.00 |
| Remote | 35% | 1.00 |
| Edmonton | 15% | 0.43 |
| Vancouver | 10% | 0.29 |
| Seattle | 5% | 0.14 |

Calgary and remote are level, because you are not relocating: those are the two
kinds of job you can actually take. A posting listing several locations takes
its **highest-weighted** one, and on a tie the first one listed in
`locationWeights` wins — so `Calgary, AB / Remote` files as Calgary, which is
right: it is a job you could do from an office you can drive to. `Vancouver, WA`
is a Portland suburb and buckets as Seattle, not British Columbia.

### What counts as remote

Not the word "remote". A posting only occupies the remote bucket if it clears
both of these, which is `lib/remote.js`:

**It is not US-fenced.** A remote role restricted to the United States needs a
TN visa, so it is closed to you in practice. Naming the US *alongside* Canada is
fine — "Remote — Canada or US" is a job you can do from Calgary. Only a posting
that names the US and never Canada is excluded.

**It is not secretly hybrid.** Plenty of postings say "Remote" in the location
field and "three days a week in the office" in the description. Only the
description can tell you, so it gets the deciding vote.

The hybrid check is deliberately narrow, because the obvious version of it is
wrong. A bare match on the word *hybrid* disqualified all 37 of Wealthsimple's
genuinely-remote-in-Canada postings, on the strength of a boilerplate sentence
— "We are a hybrid team with over 1,500 employees across North America" — that
describes the company, not the job. So the word only counts when it is attached
to the role (`hybrid role`, `position is hybrid`, `hybrid (3 days in office)`)
or when it appears in the location field, which is the employer's structured
statement about *this* posting. For the same reason a bare "onsite" is not a
signal at all: it appears constantly in unrelated senses, like onsite customer
visits.

Measured against 441 real postings from six Canadian employers: 325 claimed
remote, 317 were genuinely remote-in-Canada, 6 were hybrid roles in Toronto,
and 2 were US-fenced.

**A hybrid job in Calgary is still a Calgary job.** Hybrid is only a problem
when the office is one you cannot drive to, and that falls out on its own: with
no remote bucket to land in, a hybrid Toronto posting has only its city to
match, and that is off-list.

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
stated proportions — roughly a third Calgary, a third remote, and so on — with
each location's own rows ordered best-first inside it.

It uses stride scheduling. The *k*-th best posting in a bucket of weight *w* is
handed the virtual position `(k + 0.5) / w`, and everything sorts by that.
Calgary at 0.35 emits a row roughly every 3 positions, Seattle at 0.05 every 20
— the 35/35/15/10/5 split falls out by construction, with no need to know how
long the list is, and a bucket that runs dry simply stops appearing instead of
stalling the feed.

The header reports the mix actually on screen, so the configured percentages
can be checked against reality rather than taken on faith.

Three orderings are available: **Balanced mix** (default), **Best match first**
(flat `match_score`), and **Newest first**.

---

## Where it looks

Seven ATS platforms, all of them public JSON that the employer's own careers
page calls to render itself. No authentication, no bot defense, nothing that
violates anyone's terms.

| Platform | Addressed by | Descriptions | Notes |
|---|---|---|---|
| Greenhouse | slug | inline | `?content=true` |
| Lever | slug | inline | |
| Ashby | slug | inline | |
| Workable | slug | inline | `?details=true` |
| Recruitee | slug | inline | reports remote as a boolean, not a guess |
| BambooHR | slug | second request | small boards, so the detail pass is cheap |
| Workday | tenant + host + site | second request | searched, not listed |

**Workday is the one that behaves differently**, and it matters because it is
where Calgary's large employers post — the energy majors, the banks, the
utilities. Two consequences:

*It is searched, not listed.* BMO's board is 927 postings. Asking it for
`software engineer` returns 54, server-side. Pulling all 927 to discard 873
would be slow and rude to a host that is not charging us, so the connector
issues one search per `tier1SearchKeywords` entry and unions the results.

*Its list endpoint has no descriptions,* and the ingest gate's experience cap
reads descriptions. Fetching every posting's body would be ~900 requests
against BMO to keep a handful. So the title-level gates — role match and
seniority exclusion, the same two `ingestGate` applies first — run before the
request is spent, and only survivors get a detail fetch. BambooHR works the
same way.

Workday also dates postings only in words (`Posted 3 Days Ago`), which
`parsePostedOn` converts back to a real date so `maxAgeDays` can be applied.
An unrecognized phrase becomes `null`, not a guess: undated is treated as
fresh-on-first-sight, and quietly turning an unparseable date into "today"
would defeat the freshness gate rather than fail it.

### Adding a board

Greenhouse, Lever and Ashby slugs are usually the company name. Workday's three
parts are not derivable, so probe for them:

```
node scripts/probe-workday.js westjet atco tcenergy
```

It prints a ready-to-paste `tier1Watchlist` entry for every tenant that
answers.

`npm run bootstrap-sources` **merges** into the watchlist rather than replacing
it. It can only discover Greenhouse/Lever/Ashby boards from a company name, so
overwriting would delete every Workday, Workable, Recruitee and BambooHR entry
on every run.

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

Changing a preference re-judges rows already in the database automatically —
it is the second phase of every **Refresh job searches** run. Change a filter,
hit Refresh, done. There is no separate command to remember.

That matters most when you *widen* something. The postings a wider window now
admits are mostly ones already sitting in the database as `archived`, so no
amount of fetching would surface them; only re-judging brings them back. The
run summary reports it:

```
  Re-checked existing: 1284
    - brought back into the feed: 36
    - archived (no longer match): 4
```

Re-judging **archives** rather than deletes, and leaves rows you have already
acted on alone — a config change should never quietly destroy a posting you
might want back, or undo your own decisions. Archived rows are one "Restore"
click away, or visible via the Archived status filter.

`scripts/rescore.js` still exists for one thing: `--dry-run`, which reports
what would change without touching anything.

### The freshness window

`maxAgeDays` is not edited by hand. The dashboard's **Posted within** control
is the only place it is set: choosing a window saves it immediately, and
everything that cares about dates reads that one value — the ingest gate, the
on-screen feed, and the re-judging pass.

The control builds itself from the saved value. It used to ship its own
`<option value="3" selected>` in the markup, which meant it booted to 3 days
regardless of what was saved and then *wrote that 3 back* on the next run, so a
window you chose could not survive. Nothing invents a window now, and with no
config file at all the app applies no age limit rather than a number you never
picked.

### A note on "Jan 2027"

It is not a Tier 2 search keyword. Job boards index titles and descriptions,
not start dates, so querying an API for `Jan 2027` returns almost nothing. It
is handled as a scoring signal instead (`timingKeywords`), which boosts a
posting that does mention the window without hiding the ones that don't.

---

## Layout

```
server.js                Express app + REST API (both views)
discover.js              one discovery run; spawned by the Refresh button
config/
  preferences.json       what you want — filters, weights, keywords
  sources.json           where to look — watchlist, search terms
connectors/              one module per board. Slug boards (greenhouse, lever,
                         ashby, workable, recruitee, bamboohr) are addressed by
                         one string; workday needs tenant + host + site. Plus
                         remotive, remoteok, careerpage. (weworkremotely
                         exists but is off — it charges you to apply.)
lib/
  rescore.js             re-apply preferences to rows already stored;
                         runs as phase two of every discovery run
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
  probe-workday.js       find a company's Workday tenant/host/site
  rescore.js             --dry-run report of what re-judging would change
resume/                  your base resume + generated drafts (git-ignored)
jobs.db                  the single SQLite file both entry points share
```

`node --test` runs the suite — 94 tests, no network, no database of its own.

---

## Resume tailoring

Every generated draft passes a traceability check: claims that are not
grounded in `resume/base-resume.md` are flagged. A flagged line can only be
accepted by writing a short reason, which is recorded in the `overrides` table.
Nothing is rubber-stamped past a fabrication flag, and "Confirm & Generate" is
the single approval gate — there is no second prompt behind it.

---

## Known gaps

**Alberta posts very few junior IC engineering roles.** The watchlist gap is
closed — it now carries 25 boards including Calgary-headquartered Neo
Financial, Benevity, Suncor, Cenovus, Enbridge and Ovintiv. But the scarcity
behind it was real, and expanding the sources measured it rather than fixed
it. Of the Alberta postings on the best five non-Workday boards, the number
surviving the role and seniority gates was:

| Board | Alberta postings | Survive the gate |
|---|---|---|
| Neo Financial | 14 | 0 |
| Jobber | 9 | 0 |
| Benevity | 8 | 0 |
| Hootsuite | 3 | 0 |
| StackAdapt | 6 | 4 |

What is actually open in Calgary is directors, sales, mortgage analysts, and
senior/staff engineers. The gate is behaving correctly; the market is thin.
**A 50% Calgary weight was not satisfiable by any amount of scraping**, which
is why Calgary now sits at 35% level with remote rather than dominating the
mix. Remote-across-Canada is the load-bearing bucket, not a 15% afterthought.

**Seattle is a lottery ticket, and that is intentional.** It sits at 5%
because you would relocate for a year for a genuinely exceptional big-name
role, and not otherwise. You hold no US work authorization, so anything there
needs sponsorship or a TN visa — which is what the 🛂 flag and the 65% score
cut are for. The bucket is meant to stay small and mostly ignored; the failure
mode to watch is Seattle postings *crowding out* the feed rather than sitting
quietly at the bottom of it.

**`match_score` has no feedback loop.** It reflects your stated preferences, not
which applications actually got replies. The applied log holds the data to
close that loop; nothing does it yet.

**Location parsing is pattern-based.** It handles the formats these boards
actually emit, including multi-city strings and the Vancouver WA/BC trap, but
it is regex over free text, not a geocoder. A novel format buckets as `unknown`
rather than guessing.
