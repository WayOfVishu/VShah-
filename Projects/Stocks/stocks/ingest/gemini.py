"""DS3: the synthesised sentiment dataset. Gemini reads the corpora, not the web.

**What changed and why.** This project used to feed the model five datasets, of
which three were raw text: a 12-month news baseline, a 2-month recent window,
and a 6-month macro/political window. Each arrived at `pipeline.py` as a
concatenated string, was TF-IDF'd to tens of thousands of columns, and was then
crushed to 24 opaque SVD components. Three text blocks, 72 components, against
a panel of maybe two thousand rows -- and not one of those components had a
name a human could interpret.

Those three windows now go to Gemini instead, which returns a small fixed
schema of named scores: how positive the coverage is, how much of it there is,
whether the story changed, how the macro backdrop looks, how confident it is in
any of that. Roughly a dozen dense, interpretable numbers replace 72 opaque
ones. On a panel this small that is not a marginal improvement, it is the
difference between features a model can use and features it can only overfit.

**Gemini synthesises. It does not retrieve.** This distinction is the whole
design and getting it backwards would destroy the project:

    GDELT   -> retrieval. Point-in-time: `startdatetime`/`enddatetime` return
               what was published in a window, and nothing published after it.
    Gemini  -> synthesis. Reads what GDELT returned. Never searches.

Google Search grounding is deliberately **not** enabled. Grounding searches
today's index, so asking a grounded model about April 2023 returns articles
written after the fact -- every panel row would be scored with knowledge of its
own label. That is not a subtle bias, it is the answer key. If you are tempted
to turn grounding on for "better recency", note that live inference already has
recency: GDELT indexes worldwide news every 15 minutes.

**The leakage that remains, and what is done about it.** Even reading only
correctly-dated documents, the model *recognises* them. Hand it 2023 headlines
about a large-cap technology company and it may well remember how the quarter
ended. `_sanitize` is the defence, and it is imperfect by nature:

    - the ticker and every company name variant become "the company"
    - publication dates are stripped from the rendered prompt
    - document order is shuffled, so recency cannot be read off position
    - the system instruction forbids outside knowledge and requires `null`
      rather than a guess when the text does not support a field

Set `GEMINI_STRICT_GROUNDING=0` to disable all of that and let the model see
tickers and dates. It produces visibly richer briefs. It is also the
configuration that will quietly inflate your backtest, so the flag defaults to
on and `build_row` records which mode produced each row.

**Cost.** Roughly 10k input tokens per call. A ten-symbol, three-year weekly
sweep is about 1,560 bundles, so on the order of $5 on flash -- and the
`DiskCache` means re-running a sweep costs nothing. This is cheap enough that
the honest configuration is also the affordable one.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
import numpy as np

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from ..windows import DateWindow
from .base import BaseProvider, DiskCache, Document, ProviderError, RateLimiter

log = logging.getLogger(__name__)

__all__ = ["SentimentBrief", "GeminiProvider", "SyntheticBriefProvider", "BRIEF_FIELDS"]

# Free-tier Gemini allows a low requests-per-minute ceiling and returns 429 with
# no Retry-After, exactly like GDELT. Two seconds survives a sustained sweep on
# the free tier; paid keys can lower it, but a sweep is cache-backed anyway so
# the wall-clock saving is small and only applies to the first pass.
MIN_INTERVAL = 2.0

# Transient failures get retried; setup failures do not. The distinction is the
# point: a 503 is the model being busy and will pass on its own, whereas a
# disabled API fails identically forever and retrying it three times just makes
# a broken sweep three times slower.
MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 2.0

# The numeric fields the model must return. Kept as a module-level tuple because
# three separate things need to agree on it -- the JSON schema sent to the API,
# the fallback record built when the call fails, and the feature names emitted
# by `features/synthesis.py`. Defining it once means a field cannot be added to
# the schema and silently dropped from the panel.
BRIEF_FIELDS: tuple[str, ...] = (
    "baseline_sentiment",
    "recent_sentiment",
    "sentiment_shift",
    "community_sentiment",
    "macro_sentiment",
    "narrative_change",
    "attention_level",
    "controversy",
    "uncertainty",
    "forward_looking_tone",
    "confidence",
)


@dataclass(slots=True)
class SentimentBrief:
    """One synthesised read of everything textual known about a stock on a date.

    Every score is on [-1, 1] except `attention_level`, `controversy`,
    `uncertainty` and `confidence`, which are on [0, 1]. The asymmetry is
    deliberate: sentiment has a natural sign and a natural zero, whereas
    "how much coverage" does not -- a signed attention score would need an
    arbitrary midpoint and the model would have to guess where it sits.

    `None` means the documents did not support a judgement, and it survives all
    the way to the panel as NaN rather than being coerced to zero. Zero is a
    real reading -- balanced coverage -- and conflating it with "we could not
    tell" would let the median imputer fill genuine silence with a fabricated
    neutral opinion.
    """

    symbol: str
    as_of: date

    baseline_sentiment: float | None = None      # tone of the 12-2 month window
    recent_sentiment: float | None = None        # tone of the last 2 months
    sentiment_shift: float | None = None         # recent minus baseline, as the model reads it
    community_sentiment: float | None = None     # retail/forum tone specifically
    macro_sentiment: float | None = None         # political and economic backdrop
    narrative_change: float | None = None        # -1 story deteriorated, +1 improved
    attention_level: float | None = None         # 0 ignored, 1 saturation coverage
    controversy: float | None = None             # 0 consensus, 1 sharply divided
    uncertainty: float | None = None             # 0 confident coverage, 1 hedged
    forward_looking_tone: float | None = None    # tone of claims about the future only
    confidence: float | None = None              # the model's own self-report

    rationale: str = ""
    themes: list[str] = field(default_factory=list)
    n_documents: int = 0
    grounding: str = "strict"                    # strict | light | synthetic
    model: str = ""
    is_synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["as_of"] = self.as_of.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SentimentBrief":
        d = dict(d)
        d["as_of"] = date.fromisoformat(d["as_of"])
        return cls(**d)


# The response schema, in the subset of OpenAPI that the Gemini API accepts.
# Lowercase type names: the `google-genai` SDK normalises these itself, and the
# uppercase spelling the old `google-generativeai` package wanted is rejected.
# Constrained decoding rather than "please return JSON" in the prompt: a schema
# the API enforces cannot come back malformed, whereas a prompt asking for JSON
# fails on maybe a percent of calls, and a percent of a sweep is a lot of rows
# lost to a parse error.
def _response_schema() -> dict[str, Any]:
    signed = {"type": "number", "nullable": True,
              "description": "score from -1.0 to 1.0, or null if unsupported"}
    unsigned = {"type": "number", "nullable": True,
                "description": "score from 0.0 to 1.0, or null if unsupported"}
    unsigned_fields = {"attention_level", "controversy", "uncertainty", "confidence"}

    return {
        "type": "object",
        "properties": {
            **{f: (unsigned if f in unsigned_fields else signed) for f in BRIEF_FIELDS},
            "themes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "up to 5 short topic labels drawn only from the documents",
            },
            "rationale": {
                "type": "string",
                "description": "two sentences citing what in the documents drove the scores",
            },
        },
        "required": list(BRIEF_FIELDS),
    }


SYSTEM_INSTRUCTION_STRICT = """\
You are scoring a corpus of documents. Follow these rules exactly.

1. Score ONLY from the documents provided below. They are the entire world.
2. Assume you have NO knowledge of this company, its industry, or any events
   whatsoever. If you believe you recognise the company, disregard that
   entirely -- it is not evidence and using it corrupts the result.
3. Never reason about what happened after these documents were written. There
   is no "after". You are scoring the documents, not predicting an outcome.
4. If the documents do not support a field, return null for it. Returning null
   is correct and expected. A guess is worse than an absence.
5. Set `confidence` to reflect how much the documents actually support your
   scores: thin, repetitive, or off-topic corpora should score low.

Sentiment scores run -1.0 (uniformly negative) to +1.0 (uniformly positive),
with 0.0 meaning balanced or neutral coverage. Intensity scores run 0.0 to 1.0.
"""

SYSTEM_INSTRUCTION_LIGHT = """\
You are scoring a corpus of news and community documents about a public company.

1. Base your scores on the documents provided. They are the primary evidence.
2. Do not reason about events after the documents' publication dates.
3. If the documents do not support a field, return null rather than guessing.
4. Set `confidence` to reflect how well the documents support your scores.

Sentiment scores run -1.0 (uniformly negative) to +1.0 (uniformly positive),
with 0.0 meaning balanced or neutral coverage. Intensity scores run 0.0 to 1.0.
"""


class GeminiProvider(BaseProvider):
    """Synthesises DS3 from the retrieved corpora. Needs GEMINI_API_KEY.

    Degrades exactly like every other provider in this package: no key, no
    package, or a failed call all fall through to `SyntheticBriefProvider`, and
    the bundle records it in `synthetic` so a run built on fabricated sentiment
    cannot be mistaken for a real one.
    """

    name = "gemini"

    def __init__(
        self,
        api_key: str | None,
        model: str = "gemini-2.5-flash",
        cache: DiskCache | None = None,
        *,
        strict_grounding: bool = True,
    ) -> None:
        super().__init__(cache)
        self.api_key = api_key
        self.model = model
        self.strict_grounding = strict_grounding
        self._limiter = RateLimiter(MIN_INTERVAL)

    def available(self) -> bool:
        if not self.api_key:
            return False
        try:
            from google import genai  # noqa: F401
        except ImportError:
            log.debug("google-genai not installed; gemini provider unavailable")
            return False
        return True

    # --- prompt construction ---------------------------------------------

    @staticmethod
    def _name_variants(symbol: str, docs: list[Document]) -> list[str]:
        """Strings to redact: the ticker, plus company names inferred from titles.

        Redacting the bare ticker is not enough -- headlines say "Apple", not
        "AAPL". There is no company-name field anywhere in the pipeline (GDELT
        does not supply one), so this infers candidates from capitalised tokens
        that recur across many titles, which is what a company name does and
        what an ordinary noun does not.

        Imperfect on purpose rather than by neglect. A company mentioned in
        only a couple of documents will not clear the threshold, and a
        distinctive product name will not be caught at all. This raises the
        cost of recognition; it does not make recognition impossible, and
        `docs/TODO.md` records that limitation rather than papering over it.
        """
        variants = {symbol.upper(), symbol.lower(), symbol.capitalize()}

        counts: dict[str, int] = {}
        for doc in docs:
            # Capitalised runs, e.g. "Canadian Natural Resources".
            for token in set(re.findall(r"\b[A-Z][A-Za-z&.'-]{2,}(?:\s+[A-Z][A-Za-z&.'-]{2,})*", doc.title)):
                counts[token] = counts.get(token, 0) + 1

        threshold = max(3, len(docs) // 10)
        for token, count in counts.items():
            if count >= threshold:
                variants.add(token)
                # "Apple Inc" should also redact a bare "Apple".
                variants.update(part for part in token.split() if len(part) > 3)

        # Longest first, so "Apple Inc" is replaced before its own "Apple".
        return sorted((v for v in variants if len(v) > 1), key=len, reverse=True)

    def _sanitize(self, text: str, variants: list[str]) -> str:
        if not self.strict_grounding:
            return text
        for variant in variants:
            text = re.sub(rf"\b{re.escape(variant)}\b", "the company", text)
        # Bare four-digit years leak the window's position in history even when
        # the dates themselves have been stripped from the rendering.
        return re.sub(r"\b(19|20)\d{2}\b", "[year]", text)

    def _render_docs(self, docs: list[Document], variants: list[str], label: str) -> str:
        if not docs:
            return f"-- {label}: no documents --"

        items = list(docs)
        if self.strict_grounding:
            # Seeded on the label so a given window renders identically every
            # run: an unseeded shuffle would make the prompt -- and therefore
            # the cache key and the answer -- differ between sweeps.
            random.Random(label).shuffle(items)

        lines = [f"-- {label} ({len(items)} documents) --"]
        for i, doc in enumerate(items, 1):
            body = self._sanitize(doc.combined_text()[:600], variants)
            if self.strict_grounding:
                lines.append(f"[{i}] ({doc.kind}) {body}")
            else:
                lines.append(f"[{i}] ({doc.published.isoformat()}, {doc.source}) {body}")
        return "\n".join(lines)

    def build_prompt(
        self,
        symbol: str,
        baseline: list[Document],
        recent: list[Document],
        macro: list[Document],
    ) -> str:
        """Assemble the user-turn prompt from the three corpora.

        Windows are labelled EARLIER and LATER rather than by date. The
        baseline-versus-recent comparison is the single most valuable thing the
        old five-dataset design produced -- `sentiment_shift_features` called it
        "the comparison the dataset split exists to enable" -- so collapsing
        three datasets into one must not lose it. Handing both windows to one
        call, ordered but undated, keeps the comparison while giving the model
        no calendar to anchor on.

        Macro is labelled as a separate backdrop section and explicitly marked
        as not about the company, so its tone does not bleed into the
        company-level scores. Asking for `macro_sentiment` as its own field is
        what keeps the two separable downstream.
        """
        variants = self._name_variants(symbol, baseline + recent)
        subject = "the company" if self.strict_grounding else symbol.upper()

        return "\n\n".join([
            f"Score the coverage of {subject} across the document sets below.",
            self._render_docs(baseline, variants, "EARLIER WINDOW (company coverage)"),
            self._render_docs(recent, variants, "LATER WINDOW (company coverage)"),
            self._render_docs(macro, variants,
                              "BACKDROP (general political and economic news, NOT about "
                              "this company -- score only into macro_sentiment)"),
            "Score the EARLIER window into baseline_sentiment and the LATER window into "
            "recent_sentiment. sentiment_shift is how much tone moved from EARLIER to "
            "LATER. community_sentiment covers documents marked (community) only; return "
            "null if there are none. narrative_change asks whether the subject matter "
            "itself changed between windows, not merely its tone.",
        ])

    # --- the call ---------------------------------------------------------

    def fetch_brief(
        self,
        symbol: str,
        as_of: date,
        baseline: list[Document],
        recent: list[Document],
        macro: list[Document],
        window: DateWindow,
    ) -> SentimentBrief:
        """One synthesised brief. Cached on (symbol, as_of, grounding mode).

        The cache key includes the grounding mode so that flipping
        `GEMINI_STRICT_GROUNDING` does not silently serve briefs generated
        under the other regime -- which would make an A/B comparison of the two
        modes meaningless in exactly the way that is hardest to notice.
        """
        if not self.available():
            raise ProviderError("gemini unavailable: no key or google-generativeai not installed")

        mode = "strict" if self.strict_grounding else "light"
        subject = f"{symbol.upper()}:{as_of.isoformat()}:{mode}:{self.model}"

        if self.cache is not None:
            cached = self.cache.get_documents(self.name, "brief", subject, window)
            if cached:
                try:
                    return SentimentBrief.from_dict(json.loads(cached[0].text))
                except Exception as exc:
                    log.debug("discarding unreadable cached brief for %s: %s", subject, exc)

        if not (baseline or recent or macro):
            raise ProviderError(f"no documents to synthesise for {symbol} @ {as_of}")

        brief = self._call(symbol, as_of, baseline, recent, macro)

        if self.cache is not None:
            self.cache.put_documents(self.name, "brief", subject, window, [
                Document(
                    doc_id=f"brief-{symbol}-{as_of.isoformat()}",
                    published=as_of,
                    title=f"sentiment brief {symbol} {as_of.isoformat()}",
                    text=json.dumps(brief.to_dict()),
                    source=self.name,
                    kind="brief",
                )
            ])
        return brief

    def _call(
        self,
        symbol: str,
        as_of: date,
        baseline: list[Document],
        recent: list[Document],
        macro: list[Document],
    ) -> SentimentBrief:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)
        config = types.GenerateContentConfig(
            system_instruction=(
                SYSTEM_INSTRUCTION_STRICT if self.strict_grounding
                else SYSTEM_INSTRUCTION_LIGHT
            ),
            # Zero temperature because this is measurement, not writing. Any
            # sampling noise here becomes noise in a feature column, and a
            # feature that changes between identical runs makes every ablation
            # result unreproducible.
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=_response_schema(),
            # Google Search grounding is *not* in this tool list, and must not
            # be added. See the module docstring: grounded search returns
            # today's index for a historical as-of date, which puts the label
            # inside the features.
            tools=None,
            # With no tools there is nothing to call, but the SDK still spins up
            # its automatic-function-calling path and warns about it once per
            # request -- which across a sweep is thousands of lines of noise
            # burying the warnings that matter. Disabling it says the same thing
            # the empty tool list says, in the place the SDK checks.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True, maximum_remote_calls=None),
        )

        prompt = self.build_prompt(symbol, baseline, recent, macro)

        last: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            self._limiter.wait()
            try:
                response = client.models.generate_content(
                    model=self.model, contents=prompt, config=config)
                payload = json.loads(response.text)
                break
            except Exception as exc:
                last = exc
                if not _is_transient(exc) or attempt == MAX_ATTEMPTS - 1:
                    raise ProviderError(_explain(exc, symbol, as_of, self.model)) from exc
                # Exponential backoff: 2s, 4s, 8s. No jitter, because this
                # client is already serialised behind a rate limiter -- there is
                # no fleet of workers here to spread out.
                delay = BACKOFF_BASE_SECONDS * (2 ** attempt)
                log.warning("gemini transient failure on %s @ %s (attempt %d/%d), "
                            "retrying in %.0fs: %s",
                            symbol, as_of, attempt + 1, MAX_ATTEMPTS, delay, exc)
                time.sleep(delay)
        else:  # pragma: no cover - the loop always breaks or raises
            raise ProviderError(_explain(last, symbol, as_of, self.model))

        return self._parse(symbol, as_of, payload, len(baseline) + len(recent) + len(macro))

    def _parse(self, symbol: str, as_of: date, payload: dict,
               n_documents: int) -> SentimentBrief:
        """Payload -> brief, clamping every score into its declared range.

        The schema declares the ranges but does not enforce them -- constrained
        decoding guarantees a number, not a number in [-1, 1]. An out-of-range
        score is rare and, left alone, would sit in the panel as an outlier
        that StandardScaler then spreads across every other row in the column.
        """
        unsigned = {"attention_level", "controversy", "uncertainty", "confidence"}

        def score(field_name: str) -> float | None:
            value = payload.get(field_name)
            if value is None:
                return None
            try:
                value = float(value)
            except (TypeError, ValueError):
                return None
            lo = 0.0 if field_name in unsigned else -1.0
            return max(lo, min(1.0, value))

        return SentimentBrief(
            symbol=symbol.upper(),
            as_of=as_of,
            **{f: score(f) for f in BRIEF_FIELDS},
            rationale=str(payload.get("rationale", ""))[:1000],
            themes=[str(t)[:60] for t in (payload.get("themes") or [])][:5],
            n_documents=n_documents,
            grounding="strict" if self.strict_grounding else "light",
            model=self.model,
        )


def _is_transient(exc: Exception) -> bool:
    """Would retrying this exact call plausibly succeed?

    Retrying a permanent failure is not free here. `build_panel` catches
    per-row exceptions and continues, so a misconfigured key already produces a
    panel quietly built on fallbacks -- adding four attempts each would turn a
    two-hour sweep into an eight-hour one that fails just as completely.

    Server overload (503), rate limiting (429) and internal errors (500) pass on
    their own. A disabled API, a bad key, or a retired model do not.
    """
    text = str(exc)
    transient_markers = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED",
                         "500", "INTERNAL", "504", "DEADLINE_EXCEEDED")
    permanent_markers = ("SERVICE_DISABLED", "API_KEY_INVALID", "PERMISSION_DENIED",
                         "no longer available", "not found")

    if any(m in text for m in permanent_markers):
        return False
    return any(m in text for m in transient_markers)


def _explain(exc: Exception, symbol: str, as_of: date, model: str) -> str:
    """Turn a provider exception into something that names the fix.

    Worth the twenty lines because of where these errors surface. A sweep makes
    one call per (symbol, as-of) and swallows failures per row, so a
    misconfiguration does not stop the run -- it produces thousands of identical
    log lines and a panel quietly built on lexicon fallbacks. The raw gRPC error
    for a disabled API is roughly thirty lines of metadata with the actionable
    URL buried in the middle, repeated once per row.

    Both cases below are *setup* failures: they fail every call identically and
    are fixed once, outside the code. Naming them precisely is the difference
    between a two-minute fix and reading a stack trace at row 900.
    """
    text = str(exc)

    if "SERVICE_DISABLED" in text or "has not been used in project" in text:
        project = re.search(r"project (\d+)", text)
        pid = project.group(1) if project else "<your project>"
        return (
            f"the Gemini API is not enabled for Google Cloud project {pid}. "
            f"Enable it at https://console.developers.google.com/apis/api/"
            f"generativelanguage.googleapis.com/overview?project={pid} "
            "and wait a minute for it to propagate. This fails every call until fixed."
        )

    if "no longer available" in text or ("404" in text and "models/" in text):
        suggested = re.search(r"use (models/[\w.-]+)", text)
        hint = (f" Google suggests {suggested.group(1)}." if suggested else "")
        return (
            f"model {model!r} is not available to this key.{hint} "
            "Set GEMINI_MODEL in .env, or run `py run.py models` to list what "
            "your key can reach. This fails every call until fixed."
        )

    if "API_KEY_INVALID" in text or "API key not valid" in text:
        return (
            "GEMINI_API_KEY was rejected. Check it against "
            "https://aistudio.google.com/apikey -- note that an AI Studio key and a "
            "Google Cloud key are not interchangeable. Fails every call until fixed."
        )

    if "503" in text or "UNAVAILABLE" in text:
        return (
            f"{model} is overloaded (503) and did not recover after "
            f"{MAX_ATTEMPTS} attempts on {symbol} @ {as_of}. This is Google-side "
            "load, not a configuration problem -- re-running resumes from the "
            "cache, so nothing already fetched is lost."
        )

    if "429" in text or "RESOURCE_EXHAUSTED" in text:
        return (
            f"rate limited on {symbol} @ {as_of}. The free tier allows only a few "
            "requests per minute; raise MIN_INTERVAL in this module or move to a "
            "paid key. Cached briefs are unaffected, so re-running resumes cheaply."
        )

    return f"gemini call failed for {symbol} @ {as_of}: {exc}"


class SyntheticBriefProvider(BaseProvider):
    """The offline fallback: a deterministic brief derived from the documents.

    Not a language model and not pretending to be one. It scores the corpus
    with the same crude lexicon `features/text.py` uses, so the schema is
    populated and the pipeline runs end-to-end with no key -- which is this
    project's stated first-run experience.

    `is_synthetic` is set on every brief it produces and the registry adds the
    slot to `bundle.synthetic`, so a panel built this way is flagged all the
    way through to `evaluate.py`. It exists so the plumbing is exercisable, not
    so results can be produced without a key.
    """

    name = "synthetic"

    def available(self) -> bool:
        return True

    def fetch_brief(
        self,
        symbol: str,
        as_of: date,
        baseline: list[Document],
        recent: list[Document],
        macro: list[Document],
        window: DateWindow,
    ) -> SentimentBrief:
        """Fill the **whole** schema from the lexicon, not just the easy half.

        An earlier version returned None for `narrative_change`, `controversy`,
        `uncertainty` and `forward_looking_tone`, on the grounds that a word
        list cannot really judge them. That was defensible and wrong: those
        four columns then arrived at the panel as all-NaN in every synthetic
        run, so `py run.py demo` -- the first thing anyone executes -- silently
        exercised only two-thirds of the schema, and the imputer warned about
        columns it could not fill.

        Each field below has a crude but genuine proxy available from
        `features/text.py`, which already computes most of these quantities for
        the `ds*_` control features. Using them makes the synthetic path a real
        dry-run of the real schema. `confidence` stays pinned at 0.0, which is
        how a consumer tells a lexicon brief from a real one.
        """
        from ..features.text import (
            FORWARD_LOOKING_TERMS,
            UNCERTAINTY_TERMS,
            _vocab_novelty,
            score_sentiment,
        )

        def tone(docs: list[Document]) -> float | None:
            if not docs:
                return None
            return max(-1.0, min(1.0, score_sentiment(docs).mean))

        base, rec, mac = tone(baseline), tone(recent), tone(macro)
        community = [d for d in recent if d.kind == "community"]

        # Per-day rates, for the same reason `text_stats_features` normalises:
        # the windows are ten months and two months, so raw counts are not
        # comparable and a fall in coverage would read as a rise.
        recent_rate = len(recent) / 60.0
        attention = min(1.0, recent_rate / 5.0) if recent else None

        # Disagreement among documents, as a stand-in for controversy. Not the
        # same thing -- uniformly negative coverage is uncontroversial and
        # scores low here, correctly -- but sentiment dispersion is the closest
        # single number a lexicon can offer. Scaled by 2 because VADER's
        # per-document means rarely disperse past 0.5.
        # `is not None`, not truthiness. A standard deviation of exactly 0.0 is
        # perfect consensus -- a real and meaningful reading -- and a truthy
        # check would turn it into "could not tell", which is the precise
        # zero-versus-missing conflation this class documents against.
        summary = score_sentiment(recent) if recent else None
        controversy = (
            min(1.0, summary.std * 2.0)
            if summary is not None and summary.std is not None and np.isfinite(summary.std)
            else None
        )

        # Share of recent documents that hedge, which is what
        # `text_stats_features` calls `uncertainty_rate`.
        uncertainty = None
        if recent:
            hedged = sum(
                bool(set(d.combined_text().lower().split()) & UNCERTAINTY_TERMS)
                for d in recent
            )
            uncertainty = hedged / len(recent)

        # Vocabulary turnover between the windows: how much the *subject*
        # changed, as opposed to its tone. Signed by the direction of the tone
        # move, since `narrative_change` is a signed field.
        narrative = None
        if baseline and recent:
            novelty = _vocab_novelty(baseline, recent)
            direction = 1.0 if (rec or 0.0) >= (base or 0.0) else -1.0
            narrative = max(-1.0, min(1.0, novelty * direction))

        # Tone of the forward-looking documents only. A real subset, not a
        # restatement of `recent_sentiment`: reporting on a quarter that already
        # happened and guidance about the next one routinely disagree in sign,
        # and a 21-day forecast cares about the second. None when no document
        # in the window makes a claim about the future at all, which is a
        # legitimate reading of a purely retrospective news cycle.
        forward_docs = [
            d for d in recent
            if set(d.combined_text().lower().split()) & FORWARD_LOOKING_TERMS
        ]
        forward_tone = tone(forward_docs)

        return SentimentBrief(
            symbol=symbol.upper(),
            as_of=as_of,
            baseline_sentiment=base,
            recent_sentiment=rec,
            sentiment_shift=(rec - base) if (rec is not None and base is not None) else None,
            community_sentiment=tone(community),
            macro_sentiment=mac,
            narrative_change=narrative,
            attention_level=attention,
            controversy=controversy,
            uncertainty=uncertainty,
            forward_looking_tone=forward_tone,
            # Explicitly zero. A synthetic brief has no confidence in itself,
            # and reporting anything higher would let a synthetic row look
            # trustworthy to a model that learns to weight by confidence.
            confidence=0.0,
            rationale=(
                "Synthetic brief: VADER sentiment and term-overlap proxies. "
                "No language model was called."
            ),
            themes=[],
            n_documents=len(baseline) + len(recent) + len(macro),
            grounding="synthetic",
            model="synthetic",
            is_synthetic=True,
        )
