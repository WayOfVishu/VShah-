# League-ML

Ranked League of Legends matches from the Riot API, turned into a
participant-level table of champions, matchups, items and gold, and fed to
**neural networks** that predict who wins — then used to rank item options
for a matchup, the way u.gg/op.gg do, at a scale one person can understand
every line of.

Two halves, split the same way as Stocks. The **plumbing and the honesty**
are built: config, storage, synthetic data, the training loop, the evaluation
harness, the CLI and API skeletons. The **ingestion, the features and the
networks** are scaffolded and left open on purpose — that is the part worth
doing yourself.

```
cd "../../Virtual Environments"
py -m venv league && ./league/Scripts/python.exe -m pip install -r Requirements/league.txt
cd ../Projects/League-ML
"../../Virtual Environments/league/Scripts/python.exe" run.py demo
```

`demo` runs offline on synthetic matches — no key, no network, under a
minute. If it prints two tables, the plumbing works.

This is the deep-learning edition of the 2026-08-25 draft. What moved and why
is charter Section 0; the short version is that PyTorch went from stretch goal
to the point, XGBoost left, and logistic regression stayed as the floor.

---

## The one design decision worth knowing

**Every model trains on synthetic data first, and every split moves whole
matches.**

Real data arrives only after ingestion (`#ING-1..4`) and features
(`#FEAT-1..4`) are done — months in, at 3-4 hours a week. So
`leagueml/synthetic.py` generates matches with a **planted, known answer**:
champion strength (which logistic regression can find), same-team synergy
pairs (which it can't), items that suit each champion (what the recommender
should rediscover), and — on purpose — item counts that follow the gold lead,
the confounder real data will have. `to_participant_rows()` emits exactly the
columns the real pipeline will, so every network built against it re-runs on
real matches with `--data` and no code changes.

Set `signal=0` and the outcomes become coin flips, independent of everything.
That is the **canary**: any model scoring meaningfully above AUC 0.5 on it has
found a leak, not a pattern. The demo runs it first.

The leak it is most likely to find is the split. A match contributes ten
participant rows; teammates share a label and opponents have the opposite one.
Split rows at random and every test row's near-twin is in training.
`evaluate.py` splits by match — Stocks' purged split, in a different costume —
and `#EVAL-2` measures what skipping it would have cost.

---

## What the first run already shows

From `py run.py demo` on a fresh clone (seed 0, 3,000 matches):

| | canary AUC | planted AUC |
|---|---|---|
| majority class | 0.500 | 0.500 |
| logistic regression | 0.482 | 0.886 |
| reference MLP | 0.502 | 0.865 |

Three things worth noticing before writing any code:

- **The canary is clean.** Both models land within the ±0.08 the test size allows.
- **The MLP memorises coin flips.** On the canary its `val_loss` climbs from
  0.69 to 0.78 while `train_loss` falls to 0.55, and its log-loss ends up
  clearly worse than a constant guess. That is overfitting, visible on the
  first run — `#DL-3`.
- **The MLP does not beat logistic regression.** On one-hot features that is
  expected (charter Section 10), and one seed could not show a gap this small
  anyway. Whether *any* network beats the floor is `#EVAL-3` — the most
  important question in the project.

These are synthetic numbers. They measure plumbing and capacity, not skill at League.

---

## Layout

```
run.py                  entry point — py run.py <command>
leagueml/
  config.py             paths, patch, Riot settings, seed, device
  synthetic.py          the planted answer and the canary. Read this first.
  ingestion/            rate limiter, Riot client, checkpoints       <-- #ING, yours
  features/             item timing, frames, table, encodings        <-- #FEAT, yours
  datasets.py           dict-of-tensors Dataset
  train.py              the training loop — the one worked example
  models/               the floor + reference MLP; the networks      <-- #DL, yours
  evaluate.py           match-grouped splits, metrics, canary
  recommend.py          item recommendations                         <-- #REC-1, yours
backend/app/            FastAPI: /api/health, /api/recommend
tests/                  real tests for the built parts; skipped "write me" tests for yours
docs/                   charter, working plan, TODO
```

## Commands

```
py run.py demo                           offline end-to-end. Start here.
py run.py train --model mlp              one network vs the floor, synthetic by default
py run.py train --model mlp --signal 0   ...on the canary
py run.py train --model mlp --strength 0 --synergy 2
                                         ...in a world made only of interactions (#EVAL-3)
py run.py static                         Data Dragon champions + items for the target patch
py run.py init-db                        create the SQLite schema
py run.py ingest --max-matches 50        pull matches                        (#ING-4)
py run.py build-dataset                  raw JSON -> participant table        (#FEAT-3)
py run.py train --model embedding --data data/processed/participants.parquet --save data/checkpoints/embedding.pt
py run.py recommend --champion Ahri --enemy Zed --role MIDDLE              (#REC-1)
py run.py serve                          API on :8000, docs at /docs
py run.py pipeline                       static -> init-db -> ingest -> build-dataset -> train
```

A command that reaches an unbuilt stub stops with `not built yet: ... see
docs/TODO.md #TAG` and exit code 2. That is the intended "not yet" signal.

---

## What is left for you

Twenty-seven tagged items in [`docs/TODO.md`](docs/TODO.md), in phases ordered
by what unblocks what. The three worth knowing up front:

- **`#EVAL-1`, the experiment log** — before anything else. Almost every item
  is a comparison, and today every result scrolls off the terminal.
- **`#DL-1`** — read the loop, break each line on purpose, then rebuild
  logistic regression as one `nn.Linear` and match sklearn. The best possible
  test that you understand the loop.
- **`#EVAL-3`** — does any network beat the floor? If not, that is the finding.

Work order at 3-4 hours a week: [`WEEKLY_PLAN.md`](WEEKLY_PLAN.md).

### Calibrate before you tune

In ranked solo queue, matchmaking works to make games even, so a draft decides
less than it feels like it does. Rough orders of magnitude, not targets — your
floor is the real reference:

| features | what to expect |
|---|---|
| none | AUC 0.5 by construction |
| champion select only | a modest lift over 0.5. Treat anything above ~0.70 as a leak until proven otherwise |
| + items and gold at 10 minutes | clearly more — mostly because a gold lead is a *symptom* of who is already winning, not because items cause wins (`#REC-1`) |
| synthetic, `signal=0` | 0.5 ± 3 standard errors, or something leaks |

---

## Configuration

Copy `.env.example` to `.env`. Only `RIOT_API_KEY` matters, and only from
`#ING-2` on — the demo, training on synthetic data and `static` need nothing.

| key | what |
|---|---|
| `RIOT_API_KEY` | a **Personal** key from [developer.riotgames.com](https://developer.riotgames.com/) — charter Section 6 for why not Production |
| `RIOT_REGION` / `RIOT_PLATFORM` | regional vs platform routing — `.env.example` explains |
| `LEAGUEML_SEED` | one seed for splits, initialisation and batch order |
| `LEAGUEML_DEVICE` | `auto` / `cpu` / `cuda`. CPU is fine at this scale |

**The patch has two names.** Patch notes say `26.18`; Data Dragon and
`info.gameVersion` say `16.18`. `config.py` holds both, and asking Data Dragon
for `26.18` returns a 403. Pick the live patch when ingestion starts (`#LML-3`).

---

## Results

<!-- TODO #LML-1: replace once real models are trained. Real numbers even if
     unimpressive, with an honest read of what they mean -- and every network
     next to the floor, over several seeds, on a match-grouped test set. -->

_Not yet available — see `docs/TODO.md` for current progress._

| Model | ROC-AUC | Log-loss | Seeds |
|---|---|---|---|
| Majority class | TBD | TBD | |
| Logistic regression (floor) | TBD | TBD | |
| Reference MLP | TBD | TBD | |
| Embeddings (`#DL-2`) | TBD | TBD | |
| Attention (`#DL-5`) | TBD | TBD | |

## Known limitations

<!-- TODO #LML-1 / #LML-2: fill in as you discover them -- seed-account
     sampling bias, single-patch scope, item-only recommendations, and the
     observational caveat on item recommendations (#REC-1). -->

## License / attribution

This project isn't endorsed by Riot Games and doesn't reflect the views or
opinions of Riot Games or anyone officially involved in producing or
managing League of Legends. League of Legends and Riot Games are
trademarks or registered trademarks of Riot Games, Inc.
