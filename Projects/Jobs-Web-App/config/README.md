# config/

Two files, one question each.

| File | Question |
|---|---|
| `preferences.json` | **What do you want?** |
| `sources.json` | **Where do we look?** |

The prose that used to live inside these files as `_`-prefixed keys is here
instead, so the JSON reads as configuration rather than as a document with
settings buried in it. Pre-refactor copies of both are in `backup/`, and both
still load if you restore them.

---

## sources.json

### The model: companies, not boards

The file names **companies**. Which board each one posts to is worked out at
discovery time by `lib/boardResolver.js`, which looks for the company on every
enabled platform.

This is the important change from the old `tier1Watchlist`. That file paired a
company with one platform by hand, which made every entry a standing guess, and
a wrong guess failed silently: a role posted only to Ashby by a company filed
under Greenhouse was never fetched, and nothing in the run said so. Now a
company that dual-posts is picked up on both boards, and one that migrates
platforms is picked up after the cache expires without anyone editing anything.

Duplicates are not a problem. `lib/dedup.js` already collapses the same role
arriving from two platforms and merges the `sources` list on the surviving row —
that is what the dashboard's "Sources" column shows.

### Adding a company

One line:

```json
"companies": {
  "Anthropic": {}
}
```

`{}` means "look for this company on every enabled platform". Then:

```
node scripts/resolve-boards.js      # or: node discover.js --resolve
```

Slugs are guessed from the name in two spellings — `nospace` and `hyphenated` —
which covers `Neo Financial` → `neofinancial`, `Top Hat` → `top-hat`,
`1Password` → `1password`.

### When the guess doesn't work

Two cases need an explicit `boards` override:

**Workday**, always. A Workday board is addressed by tenant + cell + site
(`bmo`, `wd3`, `External`), none of which follows from the company name, so its
platform entry sets `autoResolve: false` and it is never probed. Find the three
parts with `node scripts/probe-workday.js <company>` and paste what it prints:

```json
"Enbridge": { "boards": { "workday": { "tenant": "enbridge", "host": "wd3", "site": "ENBRIDGE_Careers" } } }
```

**A company whose slug isn't its name.** Same shape, e.g.
`{ "boards": { "greenhouse": "some-other-slug" } }`.

An override is used verbatim, never probed, and never expires. A company can
have an override for one platform and still be auto-resolved on the others —
BMO is pinned on Workday and still searched on Greenhouse, Ashby and the rest.

To stop a company being searched somewhere (a slug that collides with an
unrelated company's board), narrow it:

```json
"Acme": { "platforms": ["greenhouse", "lever"] }
```

### Keys

- **`platforms`** — `enabled` turns a platform off everywhere; `autoResolve:
  false` means "overrides only, never probe" (Workday); `rateLimitMs` throttles
  it.
- **`companies`** — the list above. An optional `note` records why a company is
  on the list when that isn't obvious.
- **`aggregators`** — keyword-search job boards, as opposed to a named
  employer's board. `enabled` is an explicit flag, not mere presence: a disabled
  entry stays in the file so it documents *why* it is off.
  WeWorkRemotely is off because it charges the applicant to apply.
- **`careerPages`** — one-off URLs scraped for schema.org `JobPosting`.
- **`searchKeywords.workday`** — Workday boards are *searched*, not listed
  (BMO's board is 927 postings), so each term costs one paginated round-trip per
  Workday board. Overlapping terms are expensive for nothing: `developer` was
  dropped because `software developer` covers the case that matters.
- **`searchKeywords.aggregators`** — the terms sent to Remotive/RemoteOK.
  `scripts/bootstrap-sources.js` derives these from your `jobs` table history.
- **`resolution.cacheDays`** — how long a probe result is trusted. Both hits and
  misses are cached in the `board_cache` table (`db/migrations/004`); caching the
  misses is what keeps the cross-product affordable, since most cells in it are
  misses. A probe that *errors* is not cached, so a timeout retries next run.

---

## preferences.json

### roles

- **`primary`** — the roles you actually want. A title match scores 1.0.
- **`similar`** — adjacent roles worth seeing. These clear the ingest gate too,
  but score at `scoring.similarTitleFactor` of a primary hit, so widening the
  net doesn't push near-misses above direct hits.
- **`exclude`** — seniority markers. Matched on word boundaries, so `lead`
  excludes "Team Lead" but not "Leadership".

A posting must match `primary` or `similar` in its **title** to be ingested at
all. Without that gate you get welders and accountants, because pulling a
company's board pulls all of it — a recent run brought back ~2900 postings.

### synonyms

Expanded on both sides of every comparison, so the config stays written in plain
English while still matching the shorthand boards actually use. `ml` →
`machine learning` is why `ML Systems` matches, and why
`Machine Learning Infrastructure Engineer` is reachable at all.

Expansion is word-by-word, so `ml` doesn't fire inside `html`.

### level

- **`signals`** — new-grad markers. Not required; they raise the score.
- **`programs`** — early-career program names that clear the role gate *on their
  own*, since such a posting may name no engineering discipline ("New Graduate
  Rotational Program", "Anthropic Fellows Program"). Deliberately narrower than
  `signals`: letting `associate` or `entry level` through the gate pulled in
  support and production-technician roles from the real corpus.

### timing

Your Jan 2027 start window. **Scored, never required** — most postings never
state a start date, and requiring one would empty the feed. This is also why the
aggregator keywords don't search for "Jan 2027": boards index titles and
descriptions, not start dates.

### locations

- **`weights`** — used twice. Normalized against the largest, they are the
  location half of `match_score`; taken at face value they set the proportions of
  the balanced feed, so a Vancouver role still surfaces instead of being buried
  under Calgary.

  Order matters on a tie: Calgary and remote are both 0.35, and a posting
  matching several buckets takes the first of the highest-weighted, so
  "Calgary, AB / Remote" files as Calgary — right, because it's a job you could
  do from an office you can drive to.

  A location deleted from this object is genuinely gone. The defaults are **not**
  merged back over it.

- **`offList`** — `drop` means a posting whose location resolves to none of the
  buckets is never ingested. A posting with no location string at all is kept,
  bucketed `unknown`, and sorted after the balanced feed.

- **`requireSponsorshipForUS` / `usNoSponsorshipPenalty`** — you don't hold US
  work authorization, so a US-restricted posting that never mentions sponsorship
  has its location score multiplied by the penalty and is flagged 🛂. Visible,
  but not competing with the roles you could actually take.

**What "remote" means here** is not just the word in a location field. A posting
counts as remote only if it is not US-fenced (that would need a TN visa) and not
actually hybrid — which only the description reveals. See `lib/remote.js`. A
hybrid role in Calgary still buckets as Calgary; hybrid is fine when the office
is one you can drive to.

`lib/remote.js` also ignores boilerplate the posting has disowned. Employers
append company-wide policy to every listing and then say it doesn't apply —
Anthropic's fellowships carry a 25%-in-office "hybrid policy" directly under the
line "These do NOT apply to the Fellows Program." Text from such a disclaimer
onward is not evidence about the role.

### scoring

The preference score is `location * location_score + keyword * keyword_score`.
Location leads because it's the constraint you were most specific about.

**`resumeWeight`** lays resume fit over that, as a minority share:

```
match_score = (1 - resumeWeight) * preference score + resumeWeight * resume fit
```

At `0.25`, three quarters of every score is still exactly the preference score,
so resume fit reorders postings your preferences already rate about the same;
it can't lift a Vancouver role past a Calgary one on skills alone. `0` (the
default when unset) turns it off.

Resume fit (`lib/resumeFit.js`) compares the skills a posting names against the
skills `resume/base-resume.md` names, using one vocabulary for both sides. It is
half *coverage* — the share of the posting's asks you have — and half *depth* —
how many you have, saturating around eight — so a 25-technology wish list where
you have 12 still reads as a good match. A posting that names no skill in the
vocabulary gets no resume share at all rather than a zero. The dashboard's score
tooltip lists what you have and what the posting also asks for. A skill missing
from the vocabulary is invisible on both sides, so add new ones there as well as
to your resume.

### feed

- **`maxAgeDays`** — how far back to look. **Not edited by hand:** it is written
  here the moment you change the dashboard's "Posted within" control, and
  everything that cares reads it from here — the ingest gate, the on-screen
  feed, and `scripts/rescore.js`. `null` is "Any age" (no limit).
- **`archiveAfterDays`** — how long a posting you never acted on stays in the
  feed before a run sweeps it to `archived`. A different question from
  `maxAgeDays`: that is how old a posting was when found, this is how long we
  keep showing it. Reversible from the dashboard's Restore button.
- **`experienceCapYears`** — postings demanding more stated years of experience
  than this are rejected at ingest.
