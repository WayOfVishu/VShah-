"""DS3: the synthesis layer, its leakage defences, and its feature flattening.

**Why the redaction tests are the important ones here.** Everything else in this
file checks ordinary plumbing. `TestStrictGrounding` checks the one mechanism
standing between the training panel and lookahead bias, and it is a mechanism
with no runtime signal when it fails: a brief scored with knowledge of the
outcome looks exactly like a brief scored without it, produces a plausible
number, and inflates the backtest silently. There is no assertion available at
sweep time, so the assertions have to live here.

None of these tests call the Gemini API. `build_prompt` and `_parse` are pure,
which is why they are separate from `_call` -- the parts worth testing are the
parts that decide what leaves the machine and what comes back into the panel.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from stocks.features.synthesis import GEM_PREFIX, brief_features
from stocks.ingest.base import Document
from stocks.ingest.gemini import (
    BRIEF_FIELDS,
    GeminiProvider,
    SentimentBrief,
    SyntheticBriefProvider,
)
from stocks.windows import DateWindow

AS_OF = date(2023, 4, 12)
WINDOW = DateWindow(date(2022, 4, 12), AS_OF)


def _doc(i: int, title: str, text: str, kind: str = "news",
         published: date = date(2023, 2, 1)) -> Document:
    return Document(doc_id=str(i), published=published, title=title, text=text,
                    source="reuters.com", kind=kind)


@pytest.fixture
def corpora():
    baseline = [
        _doc(i, "Apple Inc beats on services revenue",
             "Apple Inc reported results in 2023 that topped estimates.")
        for i in range(12)
    ]
    recent = [
        _doc(100 + i, "Apple Inc faces EU antitrust probe",
             "Regulators opened an inquiry into Apple Inc's App Store in 2024.")
        for i in range(8)
    ]
    macro = [_doc(200, "Central bank holds rates",
                  "Policymakers left rates unchanged.", kind="macro")]
    return baseline, recent, macro


class TestStrictGrounding:
    """The leakage defence. A failure here is invisible everywhere else."""

    def test_ticker_never_appears_in_the_prompt(self, corpora):
        prompt = GeminiProvider("k", strict_grounding=True).build_prompt("AAPL", *corpora)
        assert "AAPL" not in prompt
        assert "aapl" not in prompt.lower()

    def test_inferred_company_name_is_redacted(self, corpora):
        """Redacting the bare ticker is not enough -- headlines say "Apple"."""
        prompt = GeminiProvider("k", strict_grounding=True).build_prompt("AAPL", *corpora)
        assert "Apple" not in prompt
        assert "the company" in prompt

    def test_years_are_stripped(self, corpora):
        """A bare year locates the window in history even with dates removed."""
        prompt = GeminiProvider("k", strict_grounding=True).build_prompt("AAPL", *corpora)
        assert "2023" not in prompt
        assert "2024" not in prompt
        assert "[year]" in prompt

    def test_publication_dates_and_sources_are_absent(self, corpora):
        prompt = GeminiProvider("k", strict_grounding=True).build_prompt("AAPL", *corpora)
        assert "2023-02-01" not in prompt
        assert "reuters.com" not in prompt

    def test_the_window_split_survives_redaction(self, corpora):
        """Collapsing three datasets into one must not lose the earlier/later
        comparison -- it was the most valuable feature in the old design."""
        prompt = GeminiProvider("k", strict_grounding=True).build_prompt("AAPL", *corpora)
        assert "EARLIER WINDOW" in prompt
        assert "LATER WINDOW" in prompt
        assert prompt.index("EARLIER WINDOW") < prompt.index("LATER WINDOW")

    def test_macro_is_marked_as_not_about_the_company(self, corpora):
        """Backdrop tone must not bleed into the company-level scores."""
        prompt = GeminiProvider("k", strict_grounding=True).build_prompt("AAPL", *corpora)
        assert "NOT about" in prompt

    def test_prompt_is_deterministic_across_calls(self, corpora):
        """The shuffle is seeded. An unseeded one would change the prompt --
        and therefore the cache key and the scores -- between identical runs,
        making every ablation result unreproducible."""
        p = GeminiProvider("k", strict_grounding=True)
        assert p.build_prompt("AAPL", *corpora) == p.build_prompt("AAPL", *corpora)

    def test_light_mode_keeps_what_strict_mode_removes(self, corpora):
        """The flag has to actually do something, in both directions."""
        prompt = GeminiProvider("k", strict_grounding=False).build_prompt("AAPL", *corpora)
        assert "AAPL" in prompt
        assert "Apple" in prompt
        assert "2023-02-01" in prompt

    def test_search_grounding_is_never_enabled(self):
        """Grounded search returns *today's* index. Enabling it would put the
        label inside the features on every historical panel row.

        Asserted against the source text because the tool list is passed inside
        `_call`, which cannot run without a live key -- and this is exactly the
        setting where a well-meaning future edit does the most damage.
        """
        import inspect

        from stocks.ingest import gemini

        source = inspect.getsource(gemini)
        assert "tools=None" in source
        assert "google_search" not in source.lower()


class TestSyntheticBrief:
    """The keyless fallback. Must fill the schema, and must admit what it is."""

    def test_fills_every_field_the_corpus_supports(self, corpora):
        """The lexicon path must not leave columns structurally empty.

        Two fields legitimately depend on source material this fixture has
        none of -- there are no community posts and no forward-looking claims
        -- so they are the only permitted absences. Everything else has a
        proxy and must be populated, or the synthetic panel silently exercises
        a fraction of the schema and `py run.py demo` stops being a dry run.
        """
        brief = SyntheticBriefProvider().fetch_brief("AAPL", AS_OF, *corpora, WINDOW)
        missing = {f for f in BRIEF_FIELDS if getattr(brief, f) is None}
        assert missing <= {"community_sentiment", "forward_looking_tone"}, (
            f"unexpectedly empty: {missing}"
        )

    def test_community_sentiment_appears_when_there_are_community_posts(self):
        recent = [_doc(1, "great quarter", "the stock looks strong", kind="community")]
        brief = SyntheticBriefProvider().fetch_brief("AAPL", AS_OF, [], recent, [], WINDOW)
        assert brief.community_sentiment is not None

    def test_forward_tone_appears_when_documents_look_ahead(self):
        recent = [_doc(1, "Guidance raised",
                       "The board expects revenue to grow and forecast a strong outlook.")]
        brief = SyntheticBriefProvider().fetch_brief("AAPL", AS_OF, [], recent, [], WINDOW)
        assert brief.forward_looking_tone is not None

    def test_unanimous_coverage_scores_zero_controversy_not_null(self):
        """Perfect consensus is a reading, not an absence -- the same rule the
        module applies to zero sentiment."""
        recent = [_doc(i, "results beat estimates", "strong quarter") for i in range(5)]
        brief = SyntheticBriefProvider().fetch_brief("AAPL", AS_OF, [], recent, [], WINDOW)
        assert brief.controversy == pytest.approx(0.0)

    def test_confidence_is_pinned_at_zero(self, corpora):
        """How a consumer tells a lexicon brief from a real one."""
        brief = SyntheticBriefProvider().fetch_brief("AAPL", AS_OF, *corpora, WINDOW)
        assert brief.confidence == 0.0
        assert brief.is_synthetic is True
        assert brief.grounding == "synthetic"

    def test_scores_stay_in_their_declared_ranges(self, corpora):
        brief = SyntheticBriefProvider().fetch_brief("AAPL", AS_OF, *corpora, WINDOW)
        unsigned = {"attention_level", "controversy", "uncertainty", "confidence"}
        for name in BRIEF_FIELDS:
            value = getattr(brief, name)
            if value is None:
                continue
            low = 0.0 if name in unsigned else -1.0
            assert low <= value <= 1.0, f"{name} = {value} out of range"

    def test_empty_corpora_yield_nulls_not_zeros(self):
        """Zero sentiment means balanced coverage. Silence is not balance, and
        conflating them lets the imputer invent a neutral opinion."""
        brief = SyntheticBriefProvider().fetch_brief("AAPL", AS_OF, [], [], [], WINDOW)
        assert brief.recent_sentiment is None
        assert brief.baseline_sentiment is None

    def test_round_trips_through_the_cache_format(self, corpora):
        brief = SyntheticBriefProvider().fetch_brief("AAPL", AS_OF, *corpora, WINDOW)
        again = SentimentBrief.from_dict(brief.to_dict())
        assert again.as_of == brief.as_of
        assert again.recent_sentiment == brief.recent_sentiment
        assert again.is_synthetic is True


class TestBriefParsing:
    def test_out_of_range_scores_are_clamped(self):
        """The schema declares ranges; constrained decoding does not enforce
        them. An unclamped outlier would be spread across the whole column by
        StandardScaler."""
        p = GeminiProvider("k")
        payload = {f: 5.0 for f in BRIEF_FIELDS}
        brief = p._parse("AAPL", AS_OF, payload, 20)
        assert brief.recent_sentiment == 1.0
        assert brief.confidence == 1.0

    def test_negative_scores_clamp_to_the_right_floor(self):
        p = GeminiProvider("k")
        brief = p._parse("AAPL", AS_OF, {"recent_sentiment": -9.0, "uncertainty": -9.0}, 20)
        assert brief.recent_sentiment == -1.0
        # Unsigned fields floor at 0, not -1.
        assert brief.uncertainty == 0.0

    def test_nulls_survive_as_none(self):
        p = GeminiProvider("k")
        brief = p._parse("AAPL", AS_OF, {"recent_sentiment": None}, 20)
        assert brief.recent_sentiment is None

    def test_unparseable_values_become_none_not_zero(self):
        p = GeminiProvider("k")
        brief = p._parse("AAPL", AS_OF, {"recent_sentiment": "quite positive"}, 20)
        assert brief.recent_sentiment is None

    def test_themes_are_capped_and_truncated(self):
        p = GeminiProvider("k")
        brief = p._parse("AAPL", AS_OF, {"themes": ["t" * 200] * 20}, 20)
        assert len(brief.themes) == 5
        assert len(brief.themes[0]) == 60


class TestBriefFeatures:
    def test_missing_brief_still_yields_the_full_key_set(self):
        """Every row must carry identical columns or the panel goes ragged."""
        empty = brief_features(None)
        populated = brief_features(
            SyntheticBriefProvider().fetch_brief("AAPL", AS_OF, [], [], [], WINDOW))
        assert set(empty) == set(populated)
        assert all(np.isnan(v) for v in empty.values())

    def test_none_becomes_nan_never_zero(self):
        brief = SentimentBrief(symbol="AAPL", as_of=AS_OF, recent_sentiment=None)
        f = brief_features(brief)
        assert np.isnan(f[f"{GEM_PREFIX}recent_sentiment"])

    def test_zero_sentiment_is_preserved_as_zero(self):
        """The other half of the same rule: balanced coverage is a real reading."""
        brief = SentimentBrief(symbol="AAPL", as_of=AS_OF, recent_sentiment=0.0)
        f = brief_features(brief)
        assert f[f"{GEM_PREFIX}recent_sentiment"] == 0.0

    def test_n_missing_counts_the_nulls(self):
        brief = SentimentBrief(symbol="AAPL", as_of=AS_OF,
                               recent_sentiment=0.5, confidence=0.8)
        f = brief_features(brief)
        assert f[f"{GEM_PREFIX}n_missing"] == len(BRIEF_FIELDS) - 2

    def test_conviction_damps_a_hedged_low_confidence_read(self):
        confident = SentimentBrief(symbol="A", as_of=AS_OF, recent_sentiment=0.8,
                                   confidence=0.9, uncertainty=0.1)
        hedged = SentimentBrief(symbol="A", as_of=AS_OF, recent_sentiment=0.8,
                                confidence=0.2, uncertainty=0.9)
        assert (brief_features(confident)[f"{GEM_PREFIX}conviction"]
                > brief_features(hedged)[f"{GEM_PREFIX}conviction"])

    def test_weighted_shift_scales_by_attention(self):
        """A tone change nobody covered is not the same event as one that
        dominated the cycle."""
        loud = SentimentBrief(symbol="A", as_of=AS_OF, sentiment_shift=0.5,
                              attention_level=1.0)
        quiet = SentimentBrief(symbol="A", as_of=AS_OF, sentiment_shift=0.5,
                               attention_level=0.1)
        assert brief_features(loud)[f"{GEM_PREFIX}weighted_shift"] == pytest.approx(0.5)
        assert brief_features(quiet)[f"{GEM_PREFIX}weighted_shift"] == pytest.approx(0.05)

    def test_macro_divergence_isolates_firm_specific_tone(self):
        """Chapter 8's decomposition, in one sentiment number: positive
        coverage against a negative backdrop is firm-specific strength."""
        brief = SentimentBrief(symbol="A", as_of=AS_OF, recent_sentiment=0.4,
                               macro_sentiment=-0.3)
        assert brief_features(brief)[f"{GEM_PREFIX}macro_divergence"] == pytest.approx(0.7)

    def test_sentiment_gap_flags_the_models_own_inconsistency(self):
        """`sentiment_shift` should equal recent minus baseline. When it does
        not, the model read the two windows as different subjects -- and that
        disagreement is signal, so it gets a column rather than a correction."""
        consistent = SentimentBrief(symbol="A", as_of=AS_OF, recent_sentiment=0.5,
                                    baseline_sentiment=0.2, sentiment_shift=0.3)
        assert brief_features(consistent)[f"{GEM_PREFIX}sentiment_gap"] == pytest.approx(0.0)

        inconsistent = SentimentBrief(symbol="A", as_of=AS_OF, recent_sentiment=0.5,
                                      baseline_sentiment=0.2, sentiment_shift=-0.4)
        assert brief_features(inconsistent)[f"{GEM_PREFIX}sentiment_gap"] == pytest.approx(-0.7)

    def test_synthetic_flag_reaches_the_model(self):
        """So a mixed panel can be discounted rather than averaged."""
        real = SentimentBrief(symbol="A", as_of=AS_OF, is_synthetic=False)
        fake = SentimentBrief(symbol="A", as_of=AS_OF, is_synthetic=True)
        assert brief_features(real)[f"{GEM_PREFIX}is_synthetic"] == 0.0
        assert brief_features(fake)[f"{GEM_PREFIX}is_synthetic"] == 1.0


class TestProviderAvailability:
    def test_unavailable_without_a_key(self):
        assert GeminiProvider(None).available() is False

    def test_fetch_brief_raises_rather_than_faking_when_unavailable(self, corpora):
        """It must not silently return a synthetic brief under its own name --
        the registry decides on fallbacks, and records them."""
        from stocks.ingest.base import ProviderError

        with pytest.raises(ProviderError):
            GeminiProvider(None).fetch_brief("AAPL", AS_OF, *corpora, WINDOW)
