# Tasks: Job Board Discovery & Resume Tailoring Pipeline

Source: [PRD.md](./PRD.md) (post council round 2).

**Project split (revised 2026-08-31, superseding this file's original
"code lands in Job-Tracking-Dash" plan):** the discovery + tailoring
pipeline is its own Node project here in `Job-Board-Scraping`, with its
own `package.json`/`node_modules` — not code dropped into
`Job-Tracking-Dash`. The two share **only** `Job-Tracking-Dash/jobs.db`
(PRD req. 17: one SQLite file), read/written cross-project via a relative
path (`../Job-Tracking-Dash/jobs.db`, overridable with `JOBS_DB_PATH`).
`Job-Tracking-Dash` itself stays untouched by this pipeline except for the
task 7.0 dashboard UI work, which still lands there since that's the
actual dashboard app being extended with a "Discovered" tab.

## Relevant Files

- `scripts/spike-claude-invoke.js` - Task 1.0 throwaway spike script; not
  shipped, deleted or left as a documented manual check once its go/no-go
  answer is recorded here in Tasks.md.
- `db/migrations/002-discovered-jobs.sql` - New tables: `discovered_jobs`,
  `sources`, `overrides` (PRD req. 17-19, 23) — applied to the shared
  `Job-Tracking-Dash/jobs.db`, not a local database.
- `db/migrate.js` - Migration runner shared by `discover.js`; tracks
  applied files in a `schema_migrations` table.
- `config/sources.json` - Tier 1 watchlist, Tier 2 keywords, per-source
  `rateLimitMs` (PRD req. 5, 7-8).
- `scripts/bootstrap-sources.js` - One-time script that derives
  `config/sources.json`'s seed values from the existing `jobs` table in
  `Job-Tracking-Dash/jobs.db` (PRD req. 8).
- `connectors/greenhouse.js`, `connectors/lever.js`, `connectors/ashby.js`
  - Tier 1 API connectors (PRD req. 1).
- `connectors/remotive.js`, `connectors/remoteok.js`,
  `connectors/weworkremotely.js` - Tier 2 API/RSS connectors (PRD req. 2).
- `connectors/careerpage.js` - Tier 2 schema.org `JobPosting` career-page
  connector, driven via **Playwright + headless Chromium** (PRD req. 3-4;
  see task 4.0's Lightpanda-substitution note for why).
- `lib/normalize.js` - Unified posting schema mapping (PRD req. 10).
- `lib/dedup.js` (+ `.test.js`) - Fuse.js fuzzy-match dedup on
  `title + company + location` (PRD req. 11-12).
- `lib/rateLimiter.js` (+ `.test.js`) - Per-host request throttle + 429
  backoff, config-driven (PRD req. 5).
- `lib/sourceHealth.js` (+ `.test.js`) - retry_count/status tracking
  (`ok`/`render-failed`/`permanent-fail`) shared across both tiers (PRD
  req. 4, 19).
- `discover.js` - CLI entry point (`npm run discover`); orchestrates
  connectors, dedup, insert, run summary, 60-day archive sweep (PRD
  req. 13-16).
- `lib/promptSanitize.js` (+ `.test.js`) - Strips/wraps scraped text
  before prompt interpolation; unit test uses an injected-text fixture
  (PRD req. 24).
- `lib/promptBuild.js` - Constructs the tailoring prompt from base resume
  + posting + sanitizer output; used by both the preview (req. 22) and
  the actual invocation (req. 27).
- `lib/traceabilityCheck.js` (+ `.test.js`) - Post-generation
  similarity/traceability heuristic flagging tailored lines not present
  in the base resume (PRD req. 23).
- `lib/tailorInvoke.js` - The `queued → generating → tailored` transition;
  shells out to `claude -p` directly per the task 1.0 spike result (PRD
  req. 21, 27-28).
- `resume/base-resume.md` - User-maintained canonical base resume (PRD
  req. 25) — **now in place**, converted from the user's PDF resume.
- `resume/drafts/` - Output directory for tailored drafts (PRD req. 26);
  created by `tailorInvoke.js`, gitignored.
- `Job-Tracking-Dash/server.js` - Existing Express server (separate
  project, untouched so far); gains new `discovered_jobs`-related
  endpoints without touching existing `/api/jobs*` routes (PRD req. 30).
- `Job-Tracking-Dash/public/discovered.html` (or a new section in
  `index.html`) - "Discovered" tab markup (PRD req. 31).
- `Job-Tracking-Dash/public/discovered.js` - Discovered-view logic: list,
  sort by `match_score`/recency, select+confirm-tailor flow with prompt
  and traceability-flag preview, reject/dismiss/mark-applied actions,
  source-health banner (PRD req. 22, 31-32).
- `Job-Tracking-Dash/public/style.css` - Extended with status-badge and
  source-health-banner styles (PRD §6 Design Considerations).

### Notes

- No new database engine — `discovered_jobs`/`sources`/`overrides` live in
  the same `jobs.db` file `Job-Tracking-Dash` already uses, even though
  the code that manages them is a separate project (PRD §5 Non-Goals is
  about the database, not the codebase layout).
- `node --test` is this project's test runner (`npm test`); `package.json`
  here is independent of `Job-Tracking-Dash`'s.
- Task 1.0 is a hard blocking gate. Do not start task 6.0 (or write any
  code that assumes a specific invocation mechanism) until 1.0's go/no-go
  is recorded.

## Instructions for Completing Tasks

**IMPORTANT:** As you complete each task, check it off by changing `- [ ]`
to `- [x]`. Update this file after completing each sub-task, not just
after finishing an entire parent task.

## Tasks

- [x] 0.0 Create feature branch
  - [x] 0.1 Skipped as written: `Job-Tracking-Dash` is not its own git repo —
    it lives inside the `VShah-` monorepo, already checked out on
    `Project/Job-Board-Scraping`. That branch is this feature's branch; no
    nested `feature/job-discovery-pipeline` branch was created.

- [x] 1.0 Invocation-mechanism spike (blocking — must finish before 5.0/6.0)
  - [x] 1.1 Write `scripts/spike-claude-invoke.js`: shell out to
    `claude -p "..."` non-interactively against one throwaway fake job
    posting + a tiny fake base resume.
  - [x] 1.2 Run it and record whether it hangs on any filesystem-write
    permission prompt. **Result: does not hang.** Without `--allowedTools`
    the Write call is auto-denied and Claude replies in text explaining it
    lacks permission; exits cleanly (code 0).
  - [x] 1.3 Record whether it bills against the existing Claude Code
    subscription session or requires a separately-billed API key.
    **Result: subscription session.** No `ANTHROPIC_API_KEY` was set and
    the call still succeeded via the logged-in session's own auth.
  - [x] 1.4 Record whether it raises a *second*, tool-level confirmation
    beyond whatever the script itself shows (resolves whether PRD req. 22's
    approval gate is one control or two). **Result: no second gate.**
    Passing `--allowedTools "Write"` at invocation writes the file with no
    further prompt of any kind — permission is fully resolved by the CLI
    flag. req. 22's gate is a single control (the in-app confirm click).
  - [x] 1.5 Write the go/no-go outcome into PRD.md's Open Questions section
    (replacing the "not yet run" note) and into this file's task list
    comments, so 5.0/6.0 are scoped against a real answer, not an
    assumption. **Done — see PRD.md §9.**

  **Go/no-go: GO.** `tailorInvoke.js` (task 6.1) shells out to
  `claude -p` directly with `--allowedTools "Write"` scoped via `--add-dir`
  to `resume/drafts/`, and captures stdout as the generation result. Task
  5.5's second-confirmation UI is **not needed** — skip it per its own
  instructions.

- [x] 2.0 Schema & migrations
  - [x] 2.1 Write `db/migrations/002-discovered-jobs.sql`: `discovered_jobs`
    table with all fields from PRD req. 18 (unified schema fields, sources,
    first_seen_at, status enum incl. `generating`/`rejected`, resume_path,
    match_score nullable, applied_job_id FK `ON DELETE SET NULL`).
  - [x] 2.2 Add `sources` table (req. 19): source name, retry_count,
    status (`ok`/`render-failed`/`permanent-fail`), last_success_at.
  - [x] 2.3 Add `overrides` table (req. 23): discovered_job_id,
    flagged_text, reason, timestamp.
  - [x] 2.4 Run the migration against a copy of `jobs.db` and verify the
    existing `jobs` table and its data are untouched. **Verified: 49 rows
    before and after, no existing table altered.** Added a small
    `db/migrate.js` runner (tracks applied files in `schema_migrations`,
    idempotent) shared by `server.js` and `discover.js` — not in the
    original file list but needed so both entry points apply the same
    migration set.
  - [x] 2.5 Add indices needed for the Discovered view's default sort
    (`match_score`, `first_seen_at`) and for dedup lookups (`apply_url`,
    made UNIQUE since a discovered_jobs row's canonical apply_url is set
    once at insert and updated in place on re-match, never duplicated).

- [x] 3.0 Tier 1 discovery pipeline (Greenhouse / Lever / Ashby)
  - [x] 3.1 Write `scripts/bootstrap-sources.js`: query the existing `jobs`
    table for distinct companies/titles, check which companies have a
    public Greenhouse/Lever/Ashby board, and write the seed
    `config/sources.json` (req. 8), including the <5-distinct-titles
    placeholder fallback. **Ran against real jobs.db: 48 distinct
    companies / 38 distinct titles found (well above the 5-title
    fallback threshold), 6 companies matched to a real public board**
    (StackAdapt/greenhouse, Canonical/greenhouse, Xsolla/lever,
    Turing/greenhouse, Top Hat/ashby, SpaceX/greenhouse).
  - [x] 3.2 Implement `connectors/greenhouse.js`, `connectors/lever.js`,
    `connectors/ashby.js` against their public JSON board APIs (req. 1).
  - [x] 3.3 Implement `lib/normalize.js` mapping each connector's raw
    output to the unified schema (req. 10).
  - [x] 3.4 Implement `lib/dedup.js` with Fuse.js fuzzy-match on
    `title + company + location`, plus a same-`apply_url` shortcut (req.
    11-12); write unit tests covering a true cross-posted duplicate and a
    similar-but-distinct near-miss. **3/3 tests passing
    (`lib/dedup.test.js`).**
  - [x] 3.5 Implement `discover.js` CLI: run Tier 1 connectors, normalize,
    dedup, insert new rows as `status='new'` (uncapped, req. 14), print the
    run summary (req. 15). **End-to-end verified against live APIs: first
    run fetched 2848 real postings across the 6 matched companies, 0
    duplicates (empty DB), 2848 inserted; immediate re-run fetched the
    same 2848, correctly matched all 2848 as duplicates via apply_url, 0
    newly inserted — confirms req. 12 (no re-surfacing).** Also added
    generic per-source failure tracking (retry_count / render-failed /
    permanent-fail in the `sources` table) reused across both tiers,
    beyond what task 4.4 scopes just for the career-page connector — kept
    it in `discover.js` rather than duplicating the logic later.
  - [x] 3.6 Add the 60-day auto-archive sweep for stale `status='new'` rows
    (req. 16) and wire it into `discover.js`'s run.
  - [x] 3.7 Add `npm run discover` script to `package.json` (plus
    `npm run bootstrap-sources` and a `test` script wired to
    `node --test`, needed since no test runner existed yet — Tasks.md
    Notes flagged checking for one first).

  **Known v1 rough edge surfaced by the live run:** 6 companies alone
  produced 2848 postings. This is uncapped discovery working exactly as
  PRD Goal 1 / req. 14 specify, but it makes the "reviewable queue" goal
  (req. 20 Goals, §5) real rather than theoretical — worth the user's
  attention when task 7.0's Discovered view ships, since `match_score`
  ranking (the intended mitigation) is explicitly deferred (Open
  Questions).

- [x] 4.0 Tier 2 discovery pipeline (Remotive / RemoteOK / WeWorkRemotely / career pages)

  **Lightpanda substitution (user-approved):** Lightpanda has no Windows
  build path (Linux/macOS/Nix only, requires building V8 from source) and
  this machine has neither a supported OS nor WSL installed. Per the PRD's
  own named v1.5 fallback (§7) and the user's explicit choice, `careerpage.js`
  uses **Playwright + headless Chromium** instead — same scope (plain
  page-load-and-read, no interaction scripting), same fail-loud contract.

  - [x] 4.1 Implement `connectors/remotive.js`, `connectors/remoteok.js`,
    `connectors/weworkremotely.js` against their public APIs/RSS (req. 2).
    Remotive is searched once per configured keyword (its API only supports
    single-term search); RemoteOK is fetched once per run and filtered
    locally against all keywords (its API has no reliable keyword search);
    WeWorkRemotely pulls configured category RSS feeds (parsed with
    `fast-xml-parser`, added as a new dependency — no hand-rolled XML
    regex parsing).
  - [x] 4.2 Implement `lib/rateLimiter.js`: per-host throttle from
    `config/sources.json`'s `rateLimitMs`, exponential backoff on HTTP 429
    (req. 5); unit test the backoff curve. **3/3 tests passing** (throttle
    delay, exponential backoff curve, give-up-after-max-retries).
  - [x] 4.3 Implement `connectors/careerpage.js` via Playwright + Chromium
    (see substitution note above), extract `schema.org` `JobPosting`
    JSON-LD (req. 3). **Verified against two real live pages:** a
    JS-rendered Greenhouse job page with no JobPosting markup correctly
    threw the fail-loud error; a real Ashby-hosted Top Hat job page
    correctly extracted valid JobPosting JSON-LD end-to-end through
    normalization.
  - [x] 4.4 Implement the fail-loud path: on empty/missing markup,
    increment `sources.retry_count`; after 3 consecutive failures set
    `status='permanent-fail'` (req. 4); write a fixture test that forces 3
    consecutive failures and asserts the status transition. Extracted the
    retry/permanent-fail logic into `lib/sourceHealth.js` (shared by both
    tiers, not just the career-page connector) so it's independently
    testable — **3/3 tests passing** in `lib/sourceHealth.test.js`
    (single failure stays render-failed, 3rd consecutive failure trips
    permanent-fail, a success resets the counter).
  - [x] 4.5 Wire Tier 2 connectors into `discover.js`'s run and run summary
    (including `permanent-fail` sources, req. 15).

  **Two real bugs found and fixed during live end-to-end testing (not
  caught by unit tests alone):**
  1. The in-run dedup index was a frozen snapshot — newly-inserted rows
     within the same `discover.js` run weren't added back into it, so the
     same job matched by two different Remotive keyword searches (e.g.
     "software engineer" and "software developer") hit a UNIQUE constraint
     violation on `apply_url` and got misrecorded as a Remotive *source*
     failure. Fixed by adding `lib/dedup.js`'s `addToIndex()` and calling
     it after every insert in `discover.js`.
  2. WeWorkRemotely returned 403 (Cloudflare bot challenge) without a
     browser-like `User-Agent` header. Fixed by adding one, matching what
     `remoteok.js` already did.

  **Live end-to-end result after fixes:** a clean `npm run discover` run
  fetched 3,174 postings across all 9 active sources (6 Tier 1 companies +
  Remotive + RemoteOK + WeWorkRemotely + 1 test career page) with **zero
  source failures** — every source shows `status='ok'` in the `sources`
  table. Also confirmed cross-source dedup works for real: Top Hat's
  "Senior Backend Software Engineer" was discovered independently via
  Ashby's API and via its direct career-page URL, and both correctly
  collapsed into one `discovered_jobs` row listing `["ashby","careerpage"]`
  — validating req. 11 end-to-end, not just in the unit tests.

- [ ] 5.0 Approval gate + prompt construction + injection sanitization
  - [ ] 5.1 Implement `lib/promptSanitize.js`: strip/neutralize
    instruction-like patterns in scraped text, wrap in explicit
    data-delimiters (req. 24); write the injected-text fixture test
    required by the PRD before this task is considered done.
  - [ ] 5.2 Implement `lib/promptBuild.js`: assemble the tailoring prompt
    from base resume + sanitized posting content, reusable by both the
    preview and the real invocation.
  - [ ] 5.3 Add the `discovered_jobs` status-machine transitions
    (`new → queued`, `queued → rejected`, `queued`-edit-`→ queued`) as
    server endpoints (req. 21, 30).
  - [ ] 5.4 Build the "Confirm & Generate" preview: show the constructed
    prompt/posting content before any `queued → generating` transition
    (req. 22); no file write path exists yet at this point in the build —
    that's task 6.0.
  - [x] 5.5 Once task 1.0's result is known: if a second tool-level
    permission prompt exists, add the UI/flow for surfacing it as a
    distinct second confirmation (req. 22); if not, note that only one
    gate is needed and skip this sub-task. **Skipped — no second gate
    exists (task 1.0 result).**

- [ ] 6.0 Tailoring invocation + fabrication guardrail + audit log
  - [ ] 6.1 Implement `lib/tailorInvoke.js`'s `queued → generating`
    transition per the task 1.0 outcome: either shell out to Claude Code
    directly and capture output, or write the prompt+posting to a
    manual-paste file (req. 21, 27).
  - [ ] 6.2 On success, write the tailored draft to
    `resume/drafts/{company}-{title}-{job_id}.md`, set `resume_path`,
    transition to `tailored` (req. 26).
  - [ ] 6.3 On failure, transition back to `queued` with a visible error,
    never silently to `new` (req. 28).
  - [ ] 6.4 Implement `lib/traceabilityCheck.js`: a token-overlap heuristic
    comparing each tailored line against `resume/base-resume.md`, flagging
    lines below a threshold (req. 23, §7 — start with the cheap heuristic,
    not a second LLM call).
  - [ ] 6.5 Surface flagged lines in the approval/result view, highlighted
    against the base resume (§6 Design Considerations).
  - [ ] 6.6 Implement the override flow: approving a flagged line requires
    a short reason, written to the `overrides` table (req. 23).
  - [ ] 6.7 Write tests for 6.4 using at least one drafted resume with a
    deliberately fabricated line and one fully-traceable draft, asserting
    the flag fires only on the fabricated one.

- [ ] 7.0 Dashboard: Discovered view, actions, source health, reconciliation
  - [ ] 7.1 Add new read/write endpoints to `server.js` (list discovered
    jobs, request-tailoring/confirm, reject, dismiss, mark-applied) without
    touching existing `/api/jobs*` routes (req. 30).
  - [ ] 7.2 Build the "Discovered" tab in `public/` (new section or file),
    sorted by `match_score` then recency, archived hidden by default (req.
    31), reusing the existing dashboard's visual style.
  - [ ] 7.3 Add status badges for every state in req. 18, and a persistent
    source-health banner when any source is `permanent-fail` (req. 31, §6).
  - [ ] 7.4 Wire up row actions: select + request tailoring, reject,
    dismiss, mark applied (req. 32).
  - [ ] 7.5 Implement mark-applied → create the corresponding row in the
    existing `jobs` table, pre-filled from the discovered job, and set
    `discovered_jobs.applied_job_id` (req. 32); verify the `ON DELETE SET
    NULL` behavior by deleting an applied `jobs` row in a test and
    confirming the discovered-job record survives, unlinked.
  - [ ] 7.6 Manual end-to-end pass: run `npm run discover`, confirm rows
    appear, tailor one real posting through to a written draft, mark it
    applied, and confirm it shows up correctly in the existing Applied log.
