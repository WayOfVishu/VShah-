"""The machine learning pipeline. **This is the file you own.**

Everything else in this project exists to put a clean DataFrame in front of
this module. The preprocessing is wired, three baseline models are in place,
and the grid search runs -- so you can execute it today and get a number. What
is deliberately left open is the modelling itself, marked with `#ML-n` tags
that match `docs/TODO.md`.

The structure follows your Group20 final-project notebook on purpose:
`ColumnTransformer` -> `Pipeline` -> `cross_validate` baseline -> `GridSearchCV`
over a multi-model `param_grid`. If that notebook made sense, this will.

**The one thing that is different, and why.** Every split in that notebook used
`train_test_split(..., random_state=0)` and `StratifiedKFold`. Both shuffle.
Shuffling is correct for the car-insurance data, where rows are independent
customers, and it is *catastrophic* here, where rows are dated and overlapping.

Two separate problems come from shuffling time series:

1. **Lookahead.** A shuffled fold trains on August and validates on May. The
   model learns from the future to predict the past, and the resulting score is
   unreachable in live use, often by a wide margin.
2. **Overlapping labels.** Weekly as-of dates with a 21-day horizon means
   consecutive rows share three of four weeks of forward return. Shuffled, the
   nearly-identical twin of every validation row sits in the training set, and
   the model gets credit for memorising rather than generalising.

So this module uses `TimeSeriesSplit` with a purge gap. `evaluate.py` explains
the gap in detail. The practical consequence is that your scores here will look
*worse* than the notebook's, and that is the point -- they will be real.

**What changed with the Gemini rewrite.** This module used to spend most of its
width on text. Three TF-IDF blocks went through `AdaptiveSVD` into 72 unnamed
components, against roughly 150 named numeric features, on a panel of maybe two
thousand rows. The `ColumnTransformer` below still has that machinery and it
still works -- run `build_row(include_raw_text=True)` and every text branch
comes back -- but the default panel now carries ~15 `gem_*` columns instead:
named, dense, and produced by a model that read the articles rather than
counted their words.

The practical consequence for tuning is that the text hyperparameters mostly
stop mattering and the numeric ones start to. #ML-2 (choosing SVD width) is
close to moot on the default panel; #ML-6 (the ablation) becomes *more*
important, because the question is no longer "does text help" but "does an LLM
read of the text beat VADER on the same documents" -- and both blocks are in
the panel side by side specifically so that comparison is one line of code.

**Calibrate your expectations before you start tuning.** A 30-day equity return
is close to unpredictable. Published research treats an out-of-sample R-squared
of 0.01 as a genuine result. If your first run shows R-squared 0.4, something
has leaked; check `_warn_on_leakage` output and re-read `windows.py`. Directional
accuracy in the 52-55% range is a good outcome. Anything above 60% sustained on
a proper time-series split would be remarkable, and should be treated as a bug
until proven otherwise.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .features.assemble import META_PREFIX, TEXT_PREFIX

log = logging.getLogger(__name__)

__all__ = [
    "split_columns",
    "build_preprocessor",
    "build_pipeline",
    "baseline_models",
    "param_grid",
    "AdaptiveSVD",
    "TEXT_SVD_COMPONENTS",
]

# TF-IDF on a concatenated news corpus produces tens of thousands of columns
# against a panel with maybe a couple of thousand rows. Left raw, the text
# block would swamp the ~150 numeric features purely on width, and any linear
# model would overfit it immediately. TruncatedSVD (latent semantic analysis)
# compresses each text block to this many dense components before it meets the
# numeric features, which puts the two on comparable footing.
#
# TruncatedSVD rather than PCA because it accepts sparse input without
# densifying -- densifying a 30,000-column TF-IDF matrix is what turns a
# two-minute fit into an out-of-memory error.
TEXT_SVD_COMPONENTS = 24


class AdaptiveSVD(BaseEstimator, TransformerMixin):
    """TruncatedSVD that clamps `n_components` to what the data can support.

    Plain `TruncatedSVD` raises when `n_components` exceeds the number of
    features, and here that is not a misconfiguration -- it is a normal
    consequence of the corpus being small. A short sweep, an obscure ticker
    with thin coverage, or a `min_df=2` cut on a handful of documents can all
    leave a TF-IDF vocabulary of fewer than 24 terms, and the vocabulary size
    is not knowable until the vectoriser has been fitted, which happens inside
    the fold.

    So the choice is between crashing on small panels and clamping. Clamping is
    right: the alternative is that `py run.py demo` fails on a fresh clone,
    which is the first thing anyone runs.

    Output width therefore varies with the fitted vocabulary. That is fine for
    every estimator used here -- they read the width at fit time -- but it does
    mean you should not hard-code a downstream input dimension.
    """

    def __init__(self, n_components: int = TEXT_SVD_COMPONENTS, random_state: int = 0) -> None:
        self.n_components = n_components
        self.random_state = random_state

    def fit(self, X, y=None):
        # TruncatedSVD requires n_components strictly less than n_features,
        # and at least 1.
        n_features = X.shape[1]
        self.n_components_ = max(1, min(self.n_components, n_features - 1))

        if self.n_components_ < self.n_components:
            log.debug(
                "text block has only %d features; reducing SVD components %d -> %d",
                n_features, self.n_components, self.n_components_,
            )

        self.svd_ = TruncatedSVD(n_components=self.n_components_, random_state=self.random_state)
        self.svd_.fit(X)
        return self

    def transform(self, X):
        return self.svd_.transform(X)

    def get_feature_names_out(self, input_features=None):
        return np.array([f"svd{i}" for i in range(self.n_components_)])

    @property
    def explained_variance_ratio_(self):
        """Forwarded so the #ML-2 knee plot works without unwrapping."""
        return self.svd_.explained_variance_ratio_


def split_columns(panel: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Partition panel columns into (numeric features, text features).

    Routing is by prefix, which is why `features/assemble.py` is disciplined
    about naming. `meta_*` and `target` are excluded from both -- meta columns
    are provenance, and feeding `meta_symbol` to the model would let it learn
    per-ticker biases that will not generalise to a ticker it has not seen.
    """
    text_cols = [c for c in panel.columns if c.startswith(TEXT_PREFIX)]
    numeric_cols = [
        c for c in panel.columns
        if not c.startswith((META_PREFIX, TEXT_PREFIX))
        and c != "target"
        and pd.api.types.is_numeric_dtype(panel[c])
    ]
    return numeric_cols, text_cols


def build_preprocessor(
    numeric_cols: list[str],
    text_cols: list[str],
    *,
    max_features: int = 20_000,
    svd_components: int = TEXT_SVD_COMPONENTS,
    ngram_range: tuple[int, int] = (1, 2),
) -> ColumnTransformer:
    """The ColumnTransformer: numeric on one branch, each text block on its own.

    Numeric branch -- median imputation then StandardScaler.

    Median rather than mean, which is where this departs from your Group20
    notebook: financial features have heavy tails (look at the kurtosis columns
    the feature module emits), and a mean imputed into a fat-tailed column is
    dragged by outliers toward a value no real observation ever took. Median is
    robust to exactly that.

    Text branches -- one TfidfVectorizer + TruncatedSVD **per block**.

    Usually there are now **zero** text branches: the default panel has no
    `text_*` columns, so this loop does not execute and the transformer is the
    numeric branch alone. The code stays because `include_raw_text=True`
    restores the corpora for the ablation, and because a preprocessor that
    silently could not handle text would be a trap for whoever runs it.

    When they are present, one vectoriser per block rather than one shared
    across all three, and that is deliberate: a shared vocabulary would let the
    baseline and recent windows be compared only through the model, whereas
    separate branches keep "what the baseline corpus said" and "what the recent
    corpus said" as distinct feature groups.

    Every fitted transformation lives inside the returned object, so
    `cross_validate` and `GridSearchCV` refit it per fold. That is what keeps
    the TF-IDF vocabulary from being learned across fold boundaries.

    #ML-1  Try `sublinear_tf=True` on the vectorizers. Long concatenated
           corpora make raw term frequencies dominate; log-scaling them often
           helps a lot on documents of uneven length -- which these are, since
           DS2 spans ten months and DS3 spans two.
    #ML-2  `svd_components=24` is a guess, not a result. Plot
           `explained_variance_ratio_.cumsum()` and pick the knee.
    """
    numeric_branch = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])

    transformers = [("numeric", numeric_branch, numeric_cols)]

    for col in text_cols:
        transformers.append((
            f"text_{col}",
            Pipeline([
                ("tfidf", TfidfVectorizer(
                    max_features=max_features,
                    ngram_range=ngram_range,
                    # A term in fewer than 2 documents cannot generalise across
                    # folds; one in over 85% of them carries no discriminative
                    # information. Both ends are noise.
                    min_df=2,
                    max_df=0.85,
                    stop_words="english",
                    strip_accents="unicode",
                    lowercase=True,
                )),
                # AdaptiveSVD, not TruncatedSVD: a thin corpus can yield fewer
                # terms than components, and that must clamp rather than crash.
                ("svd", AdaptiveSVD(n_components=svd_components, random_state=0)),
            ]),
            # A bare string, not a list: sklearn passes a 1-D Series to a text
            # vectorizer only when the column selector is a scalar. Passing
            # [col] hands it a DataFrame and raises a shape error that reads as
            # if the data is malformed.
            col,
        ))

    return ColumnTransformer(
        transformers=transformers,
        # Anything unrouted is meta and must not reach the model.
        remainder="drop",
        # Slight width penalty, big readability win: named output columns make
        # feature importances interpretable instead of being `x0 .. x412`.
        verbose_feature_names_out=True,
    )


def build_pipeline(
    panel: pd.DataFrame,
    model=None,
    **preprocessor_kwargs,
) -> Pipeline:
    """Preprocessor plus estimator, ready for `.fit`, `cross_validate`, or a grid.

        pipe = build_pipeline(panel, Ridge(alpha=10))
        pipe.fit(X_train, y_train)

    Defaults to Ridge because it is the right first model here: fast, stable
    under collinearity (and these features are heavily collinear -- `eq_vol_21d`
    and `eq_vol_63d` measure nearly the same thing), and its coefficients are
    directly readable. Establish what a linear model can do before reaching for
    a boosted ensemble.
    """
    numeric_cols, text_cols = split_columns(panel)
    if not numeric_cols and not text_cols:
        raise ValueError("panel has no usable feature columns")

    return Pipeline([
        ("preprocessor", build_preprocessor(numeric_cols, text_cols, **preprocessor_kwargs)),
        ("model", model if model is not None else Ridge(alpha=1.0, random_state=0)),
    ])


def baseline_models() -> dict[str, object]:
    """Three models for the first `cross_validate` pass, before any tuning.

    The same three-way shape as your Group20 notebook -- linear, bagged trees,
    boosted trees -- in their regression forms. Run this first. It tells you
    whether the problem has any linear structure at all, which decides whether
    the tuning effort belongs in feature engineering or in model capacity.

    #ML-3  Add a persistence baseline: predict the trailing 21-day return, or
           just predict zero. If none of these three beat "predict zero" on
           R-squared, the pipeline is not adding information and no amount of
           hyperparameter tuning will change that. This is the single most
           important comparison in the project and it is one line of code.
    """
    return {
        "Ridge": Ridge(alpha=1.0, random_state=0),
        "Random Forest": RandomForestRegressor(
            n_estimators=200,
            # Shallow on purpose. An unrestricted forest on ~150 collinear
            # features and a couple of thousand rows memorises the panel;
            # training R-squared near 1.0 with validation near 0 is the
            # signature, and you will see it if you remove this.
            max_depth=6,
            min_samples_leaf=20,
            random_state=0,
            n_jobs=-1,
        ),
        "Gradient Boosting": GradientBoostingRegressor(
            n_estimators=200, learning_rate=0.05, max_depth=3,
            subsample=0.8, random_state=0,
        ),
    }


def param_grid(panel: pd.DataFrame | None = None) -> list[dict]:
    """A multi-model grid for GridSearchCV, in your notebook's shape.

    All three estimators in one grid so the search picks both the model family
    and its hyperparameters in a single pass, scored on the same folds. Includes
    preprocessor parameters, because how many SVD components the text gets is a
    modelling choice exactly as much as tree depth is -- and one the search can
    make better than you can by hand.

    Sized to run in a few minutes on the synthetic panel. Expand it once you
    know which regions matter.

    Pass the panel to have the text-branch parameters included when the panel
    actually has a text branch. Omitting it is safe and simply skips them.

    #ML-4  `TruncatedSVD` is one of several ways to handle the text block. Only
           relevant when running with `include_raw_text=True`, since the
           default panel now carries `gem_*` scores instead of raw corpora.
           Also worth trying: `SelectKBest(f_regression)` on the raw TF-IDF, or
           dropping SVD and letting Ridge regularise the sparse matrix directly
           (it handles high-dimensional sparse input better than trees do).
    #ML-5  Sample weights. Recent as-of dates are more relevant to a forecast
           made today than 2021 rows are. `sample_weight` on an exponential
           decay in `as_of` is a cheap, well-motivated experiment.
    """
    grids: list[dict] = [
        {
            "model": [Ridge(random_state=0)],
            "model__alpha": [0.1, 1.0, 10.0, 100.0],
        },
        {
            "model": [RandomForestRegressor(random_state=0, n_jobs=-1)],
            "model__n_estimators": [200, 400],
            "model__max_depth": [4, 6, 10],
            "model__min_samples_leaf": [10, 20],
        },
        {
            "model": [GradientBoostingRegressor(random_state=0)],
            "model__n_estimators": [100, 200],
            "model__learning_rate": [0.02, 0.05, 0.1],
            "model__max_depth": [2, 3, 4],
        },
    ]

    # The SVD width is only a tunable parameter when there is a text branch to
    # tune, and since `build_row(include_raw_text=False)` is now the default
    # there usually is not. Naming a nonexistent step in a grid raises inside
    # `GridSearchCV.fit` -- after the folds have been built, with an error that
    # reads as a data problem rather than a configuration one.
    if panel is not None and split_columns(panel)[1]:
        grids[0]["preprocessor__text_text_recent__svd__n_components"] = [12, 24, 48]

    return grids


# --- what is left for you ------------------------------------------------
#
# #ML-6   Ablation. Fit on numeric-only, then text-only, then both. If the
#         combined model does not beat numeric-only, the news datasets are not
#         earning their keep and you should find out early. `split_columns`
#         makes this a two-line experiment, and it is the most informative
#         thing you can run on this project.
#
# #ML-7   Try `target_kind="direction"` (classification). Compare a
#         well-calibrated classifier's expected value against the regressor's
#         point estimate -- for a trading decision, a calibrated probability is
#         often worth more than a sharper point forecast.
#
# #ML-8   Try predicting the Chapter 8 *residual* instead of the raw return
#         (`finance.index_model.residual_series`). A model predicting raw
#         returns spends most of its capacity re-learning "the market moved",
#         which DS4 already tells you. Predicting the residual asks the question
#         the news datasets can actually answer, and then you add the market
#         component back analytically via beta.
#
# #ML-9   Multi-horizon output. The web app wants a 30-day *path*, not one
#         number. Either fit separate models per horizon (1, 5, 10, 21 days --
#         `compute_target` already takes a horizon), or a single
#         `MultiOutputRegressor`. Separate models usually win; they can weight
#         features differently by horizon, and short and long horizons genuinely
#         behave differently.
#
# #ML-10  Quantile regression for the interval. A point forecast on a
#         near-unpredictable target is close to useless on its own. Three
#         `GradientBoostingRegressor(loss="quantile", alpha=...)` fits at 0.1,
#         0.5, 0.9 give the app an honest fan chart, which is a far better thing
#         to show a user than a single confident line.
#
# #ML-11  A sequence model over the raw daily bars (LSTM/GRU, or a small
#         temporal CNN) instead of hand-built rolling features. You have torch
#         and keras installed already. Do this *after* the tabular baseline is
#         solid -- it is the interesting version of the project, and it is only
#         interesting once you have a number to beat.
