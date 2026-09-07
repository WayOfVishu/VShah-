"""DS3 -> feature row: the synthesised sentiment brief as numeric columns.

This module replaces what three TF-IDF blocks used to do, and the shape of the
replacement is the point.

**Before.** Three raw corpora (`text_baseline`, `text_recent`, `text_macro`)
each went through `TfidfVectorizer` -> `AdaptiveSVD`, producing 72 columns
named `svd0 .. svd23` three times over. Nobody could say what any of them
measured. Feature importances on them were uninterpretable, the vocabulary was
refit inside every fold, and the whole block competed with ~150 numeric
features on width alone.

**After.** One Gemini call per (symbol, as-of) returns a fixed schema, and this
module flattens it to about fifteen `gem_*` columns with names that state what
they measure. A Ridge coefficient on `gem_sentiment_shift` is readable. A tree
split on `gem_attention_level` is explicable to whoever asks why the model said
what it said.

**The interaction features are where the value concentrates.** The model does
not need to be told sentiment is positive; `gem_recent_sentiment` says that
directly. What it cannot easily discover from a couple of thousand rows is that
sentiment matters *more* when attention is high and confidence is high, and
matters not at all when the brief was hedged. `gem_conviction` and
`gem_weighted_shift` encode those interactions explicitly, which is the same
reasoning that put `scl_*_firm_specific_share` in `tabular.py`: hand the model
the ratio rather than making it spend splits rediscovering it.

**Missing is a value, not an absence.** Every field can be None -- the model is
instructed to return null rather than guess -- and None becomes NaN here, never
0.0. Zero sentiment means balanced coverage, which is a real reading. Coercing
"could not tell" to "balanced" would let the median imputer manufacture a
neutral opinion out of silence, and the model would have no way to tell the two
apart. `gem_n_missing` counts the nulls so the model can learn to distrust a
sparse brief wholesale.
"""

from __future__ import annotations

import numpy as np

from ..ingest.gemini import BRIEF_FIELDS, SentimentBrief

__all__ = ["brief_features", "GEM_PREFIX"]

GEM_PREFIX = "gem_"


def brief_features(brief: SentimentBrief | None) -> dict[str, float]:
    """Flatten a `SentimentBrief` into `gem_*` numeric features.

    Returns the full key set even when `brief` is None, because every row in
    the panel must carry identical columns -- a ragged frame makes structural
    absence indistinguishable from random missingness, and the imputer treats
    the two very differently.
    """
    f: dict[str, float] = {f"{GEM_PREFIX}{name}": np.nan for name in BRIEF_FIELDS}
    f.update({
        f"{GEM_PREFIX}n_documents": np.nan,
        f"{GEM_PREFIX}n_themes": np.nan,
        f"{GEM_PREFIX}n_missing": np.nan,
        f"{GEM_PREFIX}is_synthetic": np.nan,
        f"{GEM_PREFIX}conviction": np.nan,
        f"{GEM_PREFIX}weighted_shift": np.nan,
        f"{GEM_PREFIX}sentiment_gap": np.nan,
        f"{GEM_PREFIX}macro_divergence": np.nan,
    })

    if brief is None:
        return f

    values: dict[str, float | None] = {}
    for name in BRIEF_FIELDS:
        value = getattr(brief, name, None)
        values[name] = value
        f[f"{GEM_PREFIX}{name}"] = float(value) if value is not None else np.nan

    f[f"{GEM_PREFIX}n_documents"] = float(brief.n_documents)
    f[f"{GEM_PREFIX}n_themes"] = float(len(brief.themes))
    # How much of the schema the model declined to fill. A brief with eight
    # nulls is a statement that the corpus was thin, and that is worth a column
    # of its own -- the individual NaNs get imputed away, this survives.
    f[f"{GEM_PREFIX}n_missing"] = float(sum(v is None for v in values.values()))
    # Carried as a feature, not just provenance: on a mixed panel the model can
    # learn to discount synthetic rows instead of averaging them in.
    f[f"{GEM_PREFIX}is_synthetic"] = 1.0 if brief.is_synthetic else 0.0

    recent = values.get("recent_sentiment")
    baseline = values.get("baseline_sentiment")
    shift = values.get("sentiment_shift")
    attention = values.get("attention_level")
    confidence = values.get("confidence")
    uncertainty = values.get("uncertainty")
    macro = values.get("macro_sentiment")

    # Sentiment the brief actually stands behind. A strong reading from a
    # hedged, low-confidence brief over four documents should not enter the
    # model at the same magnitude as the same reading from a confident one.
    if recent is not None and confidence is not None:
        damp = 1.0 - (uncertainty if uncertainty is not None else 0.0)
        f[f"{GEM_PREFIX}conviction"] = float(recent * confidence * max(0.0, damp))

    # The shift, scaled by how much the market was watching. A tone change
    # nobody covered is not the same event as one that dominated the cycle,
    # and the raw shift cannot distinguish them.
    if shift is not None and attention is not None:
        f[f"{GEM_PREFIX}weighted_shift"] = float(shift * attention)

    # The model's own arithmetic, checked. `sentiment_shift` should equal
    # recent minus baseline; when it does not, the model is reporting a change
    # in tone it did not reflect in the levels, which is usually a sign it read
    # the windows as being about different subjects. Worth a column rather than
    # a correction -- the disagreement is the signal.
    if recent is not None and baseline is not None and shift is not None:
        f[f"{GEM_PREFIX}sentiment_gap"] = float(shift - (recent - baseline))

    # Company tone against the macro backdrop. Chapter 8's decomposition in one
    # sentiment number: a stock with positive coverage in a negative macro
    # climate is showing firm-specific strength, which is exactly the residual
    # the index regression is trying to isolate from the price side.
    if recent is not None and macro is not None:
        f[f"{GEM_PREFIX}macro_divergence"] = float(recent - macro)

    return f
