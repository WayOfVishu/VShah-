# Working Plan — 14 Weeks

This maps the phases in `docs/TODO.md` onto a calendar with explicit
checkpoints. `docs/TODO.md` is the detailed task list; this document is the
pacing. It replaces the draft's 12-week plan: the deep-learning scope added
in v3 (charter Section 0) costs about two more weeks at this pace.

**This arc assumes something like 10-15 hours/week.** At a real 3-4
hours/week, use `../WEEKLY_PLAN.md` instead — it cuts the same phases into
session-sized steps and is honest that the calendar comes out closer to eight
months. Treat this file as the map of *what* happens in each phase, and
`WEEKLY_PLAN.md` as *when*, given the time you actually have.

| Weeks | Stage | Goal | What's already built vs. yours to build |
|---|---|---|---|
| 1-2 | **Practice** | Get comfortable before touching the real pipeline. Small throwaway scripts: hit a public API with `requests`, parse the JSON, write it to a file, read it back. Register your Riot Personal API key. Run `py run.py demo` and `py run.py static`, and read `leagueml/static/data_dragon.py` end to end — it is a small, complete example of the kind of client you'll write in Phase 1. Set up the experiment log (`#EVAL-1`) now, while it is cheap. | Plumbing, the schema, synthetic data, the training loop, the evaluation harness, the CLI and API skeletons are done. Nothing to build yet but the log — deliberately a ramp-up window, per the charter's skill-gap risk. |
| 3-4 | **Early POC — Ingestion** | A rate-limited client that can pull and store a *small* batch of real matches (dozens, not thousands) end to end without crashing on a 429. Then start the long pull and let it run in the background. | `#ING-1..4`. The hardest phase for Python — budget real debugging time. |
| 5-6 | **Keep working — Networks on synthetic data** | While the pull runs: break the reference loop on purpose, build the encoder against synthetic participant rows, measure the leak, build the embedding model, add early stopping and regularisation, and find out whether any network beats the floor. | `#DL-1`, `#FEAT-2`, `#EVAL-2`, `#DL-2`, `#DL-3`, `#DL-4`, `#EVAL-3`. None of it needs real data — `synthetic.to_participant_rows()` produces the same columns `#FEAT-3` will. |
| 7-8 | **Keep working — Real features** | Raw timelines turned into one participant table with a `win` column. Everything from weeks 5-6 then re-runs on real matches with `--data` and no code changes. | `#FEAT-1`, `#FEAT-4`, `#FEAT-3`. The part that leans hardest on your SQL. |
| 9-10 | **Beta — Networks on real data** | The learning curve that decides how many matches you need, attention over the ten champions, calibration. | `#EVAL-4`, `#DL-5`, `#DL-6`. If `#EVAL-4`'s curve is still climbing, more ingestion is the right next move, not more tuning. |
| 11 | **Beta — Recommendations** | Working `py run.py recommend` and `POST /api/recommend`. **This is your MVP** — Section 15's success criteria should hold by the end of week 11. | `#REC-1`, `#REC-2`. Build `#REC-1` on synthetic data first, where you know the right answer. |
| 12-13 | **Improve with feedback** | Show the MVP to someone (classmate, mentor — anyone who'll read it like an admissions committee) and act on what's confusing or unconvincing. Typical targets: whether the README's comparison against the floor actually supports its claims, whether the confounding caveat on recommendations is stated plainly, whether the CLI output is legible. | Mostly revision. `#DL-7`, `#REC-3`, `#DL-8` only if there is real time left. |
| 14 | **Finish** | Freeze scope. Polish `README.md` — no inflated claims, real numbers even if unimpressive (`#LML-1`). Make sure `py run.py pipeline` works on a clean clone. Final commit; tag a release if you want one for application materials. | Housekeeping items in `docs/TODO.md`. |

## Ground rules (from the charter, worth restating)

- **Section 4:** every deliverable should be something you can explain in a
  grad-school interview without notes. If something got built faster than
  you understand it, stop and rebuild it by hand before moving forward.
- **Section 10:** every network is reported next to logistic regression, on
  the same match-grouped test set, over several seeds. A network that loses
  to the floor is a result, not something to hide.
- **Section 13:** lock the dataset to a single patch, picked when ingestion
  starts (`#LML-3`). Don't let ingestion straddle a patch boundary.
- **Section 9:** no fabricated or inflated claims about scale or
  performance in the README. Honest numbers, even unimpressive ones, are the
  actual deliverable.
- If weeks 3-4 or 7-8 slip, that's normal (Section 13 already expects it) —
  don't compress ingestion/ETL time to protect the modelling weeks. Networks
  trained on bad features are wasted time either way; and the synthetic track
  means the modelling weeks can absorb a slipping ingestion rather than stall
  behind it.
