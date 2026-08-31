# Tasks: Job Board Discovery & Resume Tailoring Pipeline

Source: [PRD.md](./PRD.md) (post council round 2). Implementation extends the
existing dashboard at `C:\VShah-\Projects\Job-Tracking-Dash` in place — no
new Node project, no duplicated server/UI. Planning docs (this file, the
PRD) live here in `Job-Board-Scrapping`; code changes land in
`Job-Tracking-Dash`.

## Relevant Files

- `Job-Tracking-Dash/scripts/spike-claude-invoke.js` - Task 1.0 throwaway
  spike script; not shipped, deleted or left as a documented manual check
  once its go/no-go answer is recorded here in Tasks.md.
- `Job-Tracking-Dash/server.js` - Existing Express server; gains new
  `discovered_jobs`-related endpoints without touching existing
  `/api/jobs*` routes (PRD req. 30).
- `Job-Tracking-Dash/db/migrations/002-discovered-jobs.sql` - New tables:
  `discovered_jobs`, `sources`, `overrides` (PRD req. 17-19, 23).
- `Job-Tracking-Dash/config/sources.json` - Tier 1 watchlist, Tier 2
  keywords, per-source `rateLimitMs` (PRD req. 5, 7-8).
- `Job-Tracking-Dash/scripts/bootstrap-sources.js` - One-time script that
  derives `config/sources.json`'s seed values from the existing `jobs`
  table (PRD req. 8).
- `Job-Tracking-Dash/connectors/greenhouse.js`,
  `Job-Tracking-Dash/connectors/lever.js`,
  `Job-Tracking-Dash/connectors/ashby.js` - Tier 1 API connectors (PRD
  req. 1).
- `Job-Tracking-Dash/connectors/remotive.js`,
  `Job-Tracking-Dash/connectors/remoteok.js`,
  `Job-Tracking-Dash/connectors/weworkremotely.js` - Tier 2 API/RSS
  connectors (PRD req. 2).
- `Job-Tracking-Dash/connectors/careerpage.js` - Tier 2 schema.org
  `JobPosting` career-page connector driven via Lightpanda's CDP server
  (PRD req. 3-4).
- `Job-Tracking-Dash/connectors/*.test.js` - Unit tests per connector,
  including a render-failure/retry/permanent-fail fixture test for
  `careerpage.js`.
- `Job-Tracking-Dash/lib/normalize.js` - Unified posting schema mapping
  (PRD req. 10).
- `Job-Tracking-Dash/lib/dedup.js` (+ `.test.js`) - Fuse.js fuzzy-match
  dedup on `title + company + location` (PRD req. 11-12).
- `Job-Tracking-Dash/lib/rateLimiter.js` (+ `.test.js`) - Per-host request
  throttle + 429 backoff, config-driven (PRD req. 5).
- `Job-Tracking-Dash/discover.js` - CLI entry point (`npm run discover`);
  orchestrates connectors, dedup, insert, run summary, 60-day archive
  sweep (PRD req. 13-16).
- `Job-Tracking-Dash/lib/promptSanitize.js` (+ `.test.js`) - Strips/wraps
  scraped text before prompt interpolation; unit test uses an
  injected-text fixture (PRD req. 24).
- `Job-Tracking-Dash/lib/promptBuild.js` - Constructs the tailoring prompt
  from base resume + posting + sanitizer output; used by both the preview
  (req. 22) and the actual invocation (req. 27).
- `Job-Tracking-Dash/lib/traceabilityCheck.js` (+ `.test.js`) -
  Post-generation similarity/traceability heuristic flagging tailored
  lines not present in the base resume (PRD req. 23).
- `Job-Tracking-Dash/lib/tailorInvoke.js` - The `queued → generating →
  tailored` transition; branches on the task 1.0 spike result to either
  shell out to Claude Code directly or emit a manual-paste file (PRD
  req. 21, 27-28).
- `Job-Tracking-Dash/resume/base-resume.md` - User-maintained canonical
  base resume (PRD req. 25) — not code, but must exist before tailoring
  can be tested end-to-end.
- `Job-Tracking-Dash/resume/drafts/` - Output directory for tailored
  drafts (PRD req. 26); created by `tailorInvoke.js`, gitignored.
- `Job-Tracking-Dash/public/discovered.html` (or a new section in
  `index.html`) - "Discovered" tab markup (PRD req. 31).
- `Job-Tracking-Dash/public/discovered.js` - Discovered-view logic: list,
  sort by `match_score`/recency, select+confirm-tailor flow with prompt
  and traceability-flag preview, reject/dismiss/mark-applied actions,
  source-health banner (PRD req. 22, 31-32).
- `Job-Tracking-Dash/public/style.css` - Extended with status-badge and
  source-health-banner styles (PRD §6 Design Considerations).

### Notes

- No new database engine or Node project — everything above extends the
  existing `Job-Tracking-Dash` app in place, per PRD §5 Non-Goals.
- Use `node --test` (already implied by the existing `npm run dev`
  `--watch` convention) or add a lightweight test runner if none exists
  yet in `Job-Tracking-Dash`; check `package.json` before introducing one.
- Task 1.0 is a hard blocking gate. Do not start task 6.0 (or write any
  code that assumes a specific invocation mechanism) until 1.0's go/no-go
  is recorded.

## Instructions for Completing Tasks

**IMPORTANT:** As you complete each task, check it off by changing `- [ ]`
to `- [x]`. Update this file after completing each sub-task, not just
after finishing an entire parent task.

## Tasks

- [ ] 0.0 Create feature branch
  - [ ] 0.1 From `Job-Tracking-Dash`, create and check out
    `feature/job-discovery-pipeline`.

- [ ] 1.0 Invocation-mechanism spike (blocking — must finish before 5.0/6.0)
  - [ ] 1.1 Write `scripts/spike-claude-invoke.js`: shell out to
    `claude -p "..."` non-interactively against one throwaway fake job
    posting + a tiny fake base resume.
  - [ ] 1.2 Run it and record whether it hangs on any filesystem-write
    permission prompt.
  - [ ] 1.3 Record whether it bills against the existing Claude Code
    subscription session or requires a separately-billed API key.
  - [ ] 1.4 Record whether it raises a *second*, tool-level confirmation
    beyond whatever the script itself shows (resolves whether PRD req. 22's
    approval gate is one control or two).
  - [ ] 1.5 Write the go/no-go outcome into PRD.md's Open Questions section
    (replacing the "not yet run" note) and into this file's task list
    comments, so 5.0/6.0 are scoped against a real answer, not an
    assumption.

- [ ] 2.0 Schema & migrations
  - [ ] 2.1 Write `db/migrations/002-discovered-jobs.sql`: `discovered_jobs`
    table with all fields from PRD req. 18 (unified schema fields, sources,
    first_seen_at, status enum incl. `generating`/`rejected`, resume_path,
    match_score nullable, applied_job_id FK `ON DELETE SET NULL`).
  - [ ] 2.2 Add `sources` table (req. 19): source name, retry_count,
    status (`ok`/`render-failed`/`permanent-fail`), last_success_at.
  - [ ] 2.3 Add `overrides` table (req. 23): discovered_job_id,
    flagged_text, reason, timestamp.
  - [ ] 2.4 Run the migration against a copy of `jobs.db` and verify the
    existing `jobs` table and its data are untouched.
  - [ ] 2.5 Add indices needed for the Discovered view's default sort
    (`match_score`, `first_seen_at`) and for dedup lookups (`apply_url`).

- [ ] 3.0 Tier 1 discovery pipeline (Greenhouse / Lever / Ashby)
  - [ ] 3.1 Write `scripts/bootstrap-sources.js`: query the existing `jobs`
    table for distinct companies/titles, check which companies have a
    public Greenhouse/Lever/Ashby board, and write the seed
    `config/sources.json` (req. 8), including the <5-distinct-titles
    placeholder fallback.
  - [ ] 3.2 Implement `connectors/greenhouse.js`, `connectors/lever.js`,
    `connectors/ashby.js` against their public JSON board APIs (req. 1).
  - [ ] 3.3 Implement `lib/normalize.js` mapping each connector's raw
    output to the unified schema (req. 10).
  - [ ] 3.4 Implement `lib/dedup.js` with Fuse.js fuzzy-match on
    `title + company + location`, plus a same-`apply_url` shortcut (req.
    11-12); write unit tests covering a true cross-posted duplicate and a
    similar-but-distinct near-miss.
  - [ ] 3.5 Implement `discover.js` CLI: run Tier 1 connectors, normalize,
    dedup, insert new rows as `status='new'` (uncapped, req. 14), print the
    run summary (req. 15).
  - [ ] 3.6 Add the 60-day auto-archive sweep for stale `status='new'` rows
    (req. 16) and wire it into `discover.js`'s run.
  - [ ] 3.7 Add `npm run discover` script to `package.json`.

- [ ] 4.0 Tier 2 discovery pipeline (Remotive / RemoteOK / WeWorkRemotely / Lightpanda career pages)
  - [ ] 4.1 Implement `connectors/remotive.js`, `connectors/remoteok.js`,
    `connectors/weworkremotely.js` against their public APIs/RSS (req. 2).
  - [ ] 4.2 Implement `lib/rateLimiter.js`: per-host throttle from
    `config/sources.json`'s `rateLimitMs`, exponential backoff on HTTP 429
    (req. 5); unit test the backoff curve.
  - [ ] 4.3 Implement `connectors/careerpage.js`: drive Lightpanda's CDP
    server (`lightpanda serve`) via a Playwright/Puppeteer CDP client,
    plain page-load-and-read, extract `schema.org` `JobPosting` markup
    (req. 3).
  - [ ] 4.4 Implement the fail-loud path: on empty/missing markup,
    increment `sources.retry_count`; after 3 consecutive failures set
    `status='permanent-fail'` (req. 4); write a fixture test that forces 3
    consecutive failures and asserts the status transition.
  - [ ] 4.5 Wire Tier 2 connectors into `discover.js`'s run and run summary
    (including `permanent-fail` sources, req. 15).

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
  - [ ] 5.5 Once task 1.0's result is known: if a second tool-level
    permission prompt exists, add the UI/flow for surfacing it as a
    distinct second confirmation (req. 22); if not, note that only one
    gate is needed and skip this sub-task.

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
