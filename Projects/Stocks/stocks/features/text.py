"""Text features from DS2 (news baseline), DS3 (recent), DS5 (macro).

Two kinds of output, and the split is the important design decision in this
module.

**Dense scalar features** (`text_stats_features`) -- volume, sentiment, source
mix, and above all the *deltas between DS2 and DS3*. These are computed here,
eagerly, into plain floats that sit in the same row as the price features.

**Sparse vectorised features** (`corpus_for_vectorizer`) -- raw text handed to a
`TfidfVectorizer` inside the sklearn Pipeline, never fitted here.

Why vectorisation is deliberately *not* done in this module: fitting a TF-IDF
vocabulary is a learned transformation. Fit it on the whole corpus and the
vocabulary is built partly from documents in your validation folds, which is
textbook data leakage -- and it is the leak most likely to survive review,
because a vocabulary does not look like a model. Assignment 5 in the reference
notebooks puts `TfidfVectorizer` inside a `Pipeline` for exactly this reason,
and that pattern is preserved here. This module hands out strings; the pipeline
learns from them, inside the fold.

**The DS2/DS3 comparison is the point.** The user's design splits a year of
news at the two-month mark, and the value of that split is entirely in the
difference between the halves. A stock with steadily negative coverage all year
is priced for it. A stock whose coverage turned negative in the last two months
against a positive baseline is a different situation, and only the delta
distinguishes them. `sentiment_shift_features` computes that comparison
explicitly rather than hoping a model finds it across two blocks of columns.

**On the sentiment model.** The default is VADER (via nltk), chosen because it
is lexicon-based -- no training, no fitting, therefore no leakage risk and no
fold-dependence. It was tuned for social media, which suits Reddit better than
it suits Reuters. A finance-domain transformer (FinBERT) is meaningfully more
accurate on news copy and is wired behind `sentiment_backend="finbert"`, at the
cost of a ~400MB download and roughly 100x the compute. Start with VADER; if
the sentiment features earn their place in ablation, upgrade.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from ..ingest.base import Document

log = logging.getLogger(__name__)

__all__ = [
    "text_stats_features",
    "sentiment_shift_features",
    "corpus_for_vectorizer",
    "score_sentiment",
    "SentimentSummary",
]

# Hand-built finance lexicon, used by the "lexicon" backend and as the fallback
# when nltk is absent. Loughran-McDonald is the standard academic finance
# sentiment dictionary and would be better -- this is a small stand-in that
# needs no download, so the offline path still produces a real signal.
POSITIVE_TERMS = frozenset("""
beat beats exceeded outperform upgrade upgraded raised surge surged rally
rallied gain gains profit profitable growth expanding strong record high
bullish optimistic momentum breakthrough approval partnership acquisition
buyback dividend guidance-raise recovery rebound
""".split())

NEGATIVE_TERMS = frozenset("""
miss missed misses downgrade downgraded cut cuts slash slashed plunge plunged
fell decline declined loss losses unprofitable shrinking weak bearish
pessimistic lawsuit investigation probe recall bankruptcy default layoffs
restructuring warning writedown impairment delisting fraud
""".split())

UNCERTAINTY_TERMS = frozenset("""
uncertain uncertainty may might could possibly potential risk risks volatile
volatility unclear pending awaiting depends contingent speculative
""".split())


@dataclass(frozen=True, slots=True)
class SentimentSummary:
    """Aggregate sentiment over one document window."""

    mean: float
    std: float
    positive_share: float
    negative_share: float
    n_docs: int

    @property
    def net(self) -> float:
        return self.positive_share - self.negative_share


def text_stats_features(docs: list[Document], prefix: str,
                        window_days: int, sentiment_backend: str = "vader") -> dict[str, float]:
    """Dense scalar features for one text window.

    `window_days` is needed because DS2 spans ten months and DS3 spans two, so
    raw document counts are not comparable between them. Every volume measure
    here is per-day for that reason -- comparing 400 baseline documents against
    90 recent ones without normalising would read a *drop* in coverage as a
    rise every time.
    """
    n = len(docs)
    f: dict[str, float] = {
        f"{prefix}_n_docs": float(n),
        f"{prefix}_docs_per_day": n / max(1, window_days),
    }

    if n == 0:
        # Explicit zeros/NaNs rather than absent keys: every row in the panel
        # must have the same columns, or the assembled DataFrame becomes ragged
        # and the imputer sees structural absence as random missingness.
        f.update({
            f"{prefix}_sentiment_mean": np.nan,
            f"{prefix}_sentiment_std": np.nan,
            f"{prefix}_sentiment_positive_share": np.nan,
            f"{prefix}_sentiment_negative_share": np.nan,
            f"{prefix}_sentiment_net": np.nan,
            f"{prefix}_uncertainty_rate": np.nan,
            f"{prefix}_mean_word_count": np.nan,
            f"{prefix}_source_diversity": np.nan,
            f"{prefix}_community_share": np.nan,
            f"{prefix}_burst_ratio": np.nan,
            f"{prefix}_provider_tone_mean": np.nan,
        })
        return f

    summary = score_sentiment(docs, backend=sentiment_backend)
    f[f"{prefix}_sentiment_mean"] = summary.mean
    f[f"{prefix}_sentiment_std"] = summary.std
    f[f"{prefix}_sentiment_positive_share"] = summary.positive_share
    f[f"{prefix}_sentiment_negative_share"] = summary.negative_share
    f[f"{prefix}_sentiment_net"] = summary.net

    texts = [d.combined_text().lower() for d in docs]
    tokens_per_doc = [set(re.findall(r"[a-z][a-z\-']+", t)) for t in texts]

    # Share of documents that hedge. Distinct from negative sentiment: a
    # hedging article is not bearish, it is *unsure*, and uncertainty in
    # coverage tends to precede volatility rather than direction.
    f[f"{prefix}_uncertainty_rate"] = float(
        np.mean([bool(t & UNCERTAINTY_TERMS) for t in tokens_per_doc])
    )
    f[f"{prefix}_mean_word_count"] = float(np.mean([d.word_count for d in docs]))

    # How many distinct outlets, relative to document count. Near 1.0 means
    # broad independent coverage; near 0 means one outlet repeating itself, or
    # a wire story syndicated everywhere.
    sources = Counter(d.source for d in docs)
    f[f"{prefix}_source_diversity"] = len(sources) / n

    f[f"{prefix}_community_share"] = float(np.mean([d.kind == "community" for d in docs]))

    # Burstiness: busiest week against the window's own average. News arrives
    # in clusters around events, and a high burst ratio means something
    # discrete happened rather than coverage being uniformly elevated.
    f[f"{prefix}_burst_ratio"] = _burst_ratio(docs, window_days)

    # GDELT ships its own tone score. Carrying it through gives an
    # independently-computed sentiment estimate to cross-check ours against.
    tones = [d.score for d in docs if d.score is not None]
    f[f"{prefix}_provider_tone_mean"] = float(np.mean(tones)) if tones else np.nan

    return f


def sentiment_shift_features(
    baseline: list[Document], recent: list[Document],
    baseline_days: int, recent_days: int, sentiment_backend: str = "vader",
) -> dict[str, float]:
    """DS2 versus DS3 -- the comparison the dataset split exists to enable.

    Everything here is a difference or a ratio. Levels are already covered by
    `text_stats_features` on each window; what this adds is *change*, which is
    what a 30-day forecast actually turns on. Coverage that has been mildly
    negative for a year is priced in. Coverage that flipped negative six weeks
    ago is not.

    `attention_ratio` is separate from and often more predictive than the
    sentiment delta: a sharp rise in coverage volume signals that something
    happened, regardless of what the coverage says, and volume tends to lead
    volatility more reliably than sentiment leads direction.
    """
    b = score_sentiment(baseline, backend=sentiment_backend) if baseline else None
    r = score_sentiment(recent, backend=sentiment_backend) if recent else None

    f: dict[str, float] = {}

    if b and r:
        f["shift_sentiment_delta"] = r.mean - b.mean
        f["shift_sentiment_net_delta"] = r.net - b.net
        f["shift_negative_share_delta"] = r.negative_share - b.negative_share
        # Normalising the shift by baseline dispersion asks "is this move large
        # for this stock?" -- a 0.1 sentiment move is noise for a name with
        # noisy coverage and a real signal for one with steady coverage.
        f["shift_sentiment_zscore"] = (
            (r.mean - b.mean) / b.std if b.std and b.std > 0 else np.nan
        )
    else:
        f.update({k: np.nan for k in (
            "shift_sentiment_delta", "shift_sentiment_net_delta",
            "shift_negative_share_delta", "shift_sentiment_zscore")})

    # Per-day rates, because the windows are different lengths.
    b_rate = len(baseline) / max(1, baseline_days)
    r_rate = len(recent) / max(1, recent_days)
    f["shift_attention_ratio"] = r_rate / b_rate if b_rate > 0 else np.nan
    f["shift_attention_delta"] = r_rate - b_rate

    # Vocabulary turnover: what fraction of the recent window's common terms
    # were not common in the baseline. High turnover means the *story* changed,
    # not just its tone -- a merger, a lawsuit, a product line. A sentiment
    # score cannot see that; this can.
    f["shift_vocab_novelty"] = _vocab_novelty(baseline, recent)

    return f


def corpus_for_vectorizer(docs: list[Document], max_docs: int = 2000) -> str:
    """Concatenate a window's documents into one string for TF-IDF.

    One row of the panel is one as-of date, so a window's documents have to
    collapse into a single "document" from the vectoriser's point of view. That
    loses per-article structure, which is a real cost, and it is the right
    trade at this stage: the alternative is a per-article model with an
    aggregation layer on top, which is a much larger project and should not be
    the thing standing between you and a first end-to-end run.

    Truncation is by recency when a window is very large, because if something
    has to be dropped the older half of a two-month window is the right half to
    drop.
    """
    if not docs:
        return ""
    selected = sorted(docs, key=lambda d: d.published)[-max_docs:]
    return "\n\n".join(d.combined_text() for d in selected)


@lru_cache(maxsize=1)
def _vader():
    """Load VADER once, or return None if nltk is unavailable.

    Cached because `SentimentIntensityAnalyzer()` loads a lexicon file, and the
    walk-forward sweep calls `score_sentiment` a few hundred times.
    """
    try:
        from nltk.sentiment.vader import SentimentIntensityAnalyzer

        try:
            return SentimentIntensityAnalyzer()
        except LookupError:
            # The lexicon is a separate download from the package.
            import nltk

            nltk.download("vader_lexicon", quiet=True)
            return SentimentIntensityAnalyzer()
    except Exception as exc:
        log.warning("VADER unavailable (%s); using the built-in finance lexicon", exc)
        return None


def score_sentiment(docs: list[Document], backend: str = "vader") -> SentimentSummary:
    """Aggregate sentiment over a document list, in [-1, 1] per document.

    Backends:
        vader     nltk's VADER. No fitting, so no leakage. The default.
        lexicon   the module's own finance word lists. No dependencies.
        finbert   ProsusAI/finbert via transformers. Best on news copy,
                  slowest, and needs a ~400MB download on first use.
    """
    if not docs:
        return SentimentSummary(np.nan, np.nan, np.nan, np.nan, 0)

    texts = [d.combined_text() for d in docs]

    if backend == "finbert":
        scores = _finbert_scores(texts)
    elif backend == "vader" and (analyzer := _vader()) is not None:
        scores = np.array([analyzer.polarity_scores(t)["compound"] for t in texts])
    else:
        scores = np.array([_lexicon_score(t) for t in texts])

    return SentimentSummary(
        mean=float(np.nanmean(scores)),
        std=float(np.nanstd(scores)),
        # A |score| below 0.05 is VADER's own neutrality band; reused for the
        # other backends so the shares stay comparable across them.
        positive_share=float(np.mean(scores > 0.05)),
        negative_share=float(np.mean(scores < -0.05)),
        n_docs=len(docs),
    )


def _lexicon_score(text: str) -> float:
    """Normalised (positive - negative) term count, in [-1, 1]."""
    tokens = re.findall(r"[a-z][a-z\-']+", text.lower())
    if not tokens:
        return 0.0
    pos = sum(t in POSITIVE_TERMS for t in tokens)
    neg = sum(t in NEGATIVE_TERMS for t in tokens)
    total = pos + neg
    return (pos - neg) / total if total else 0.0


def _finbert_scores(texts: list[str]) -> np.ndarray:
    """FinBERT sentiment, mapped from {positive, negative, neutral} to [-1, 1].

    Falls back to the lexicon on any failure -- a missing model download should
    degrade the feature, not abort a training sweep.
    """
    try:
        from transformers import pipeline as hf_pipeline

        clf = _load_finbert(hf_pipeline)
        # Truncated to 512 tokens, the model's limit. For a concatenated window
        # corpus that is a real loss, which is another reason FinBERT is not
        # the default at this level of aggregation.
        out = clf([t[:2000] for t in texts], truncation=True, max_length=512)
        mapping = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}
        return np.array([mapping.get(o["label"].lower(), 0.0) * o["score"] for o in out])
    except Exception as exc:
        log.warning("FinBERT scoring failed (%s); falling back to the lexicon", exc)
        return np.array([_lexicon_score(t) for t in texts])


@lru_cache(maxsize=1)
def _load_finbert(hf_pipeline):
    return hf_pipeline("sentiment-analysis", model="ProsusAI/finbert", truncation=True)


def _burst_ratio(docs: list[Document], window_days: int) -> float:
    """Busiest 7-day stretch against the window's daily average."""
    if not docs or window_days < 14:
        return float("nan")
    counts = Counter(d.published for d in docs)
    days = sorted(counts)
    if len(days) < 2:
        return float("nan")

    best = 0
    for i, day in enumerate(days):
        total = sum(c for d, c in counts.items() if 0 <= (d - day).days < 7)
        best = max(best, total)

    baseline = len(docs) / window_days * 7
    return best / baseline if baseline > 0 else float("nan")


def _vocab_novelty(baseline: list[Document], recent: list[Document], top_n: int = 100) -> float:
    """Share of the recent window's top terms absent from the baseline's top terms.

    A crude topic-shift detector: near 0 means the same story continued, near 1
    means the narrative changed. Frequency-ranked rather than TF-IDF weighted
    because this is a scalar feature computed outside the fold, and anything
    fitted would reintroduce the leakage this module avoids.
    """
    if not baseline or not recent:
        return float("nan")

    stop = frozenset("""
    the a an and or but of to in for on at by with from as is are was were be
    been being it its this that these those has have had will would could
    should said says say new more than after over into about
    """.split())

    def top_terms(docs: list[Document]) -> set[str]:
        words = re.findall(r"[a-z][a-z\-']{2,}", " ".join(d.combined_text() for d in docs).lower())
        return {w for w, _ in Counter(w for w in words if w not in stop).most_common(top_n)}

    b, r = top_terms(baseline), top_terms(recent)
    return len(r - b) / len(r) if r else float("nan")
