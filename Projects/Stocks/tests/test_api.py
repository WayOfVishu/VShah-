"""FastAPI route tests.

Offline except for `/api/resolve`, which may reach Yahoo for the long tail —
the assertions here only depend on the alias table, which is local, so the
tests pass with the network down.

`/api/datasets` and `/api/predict` are *not* covered end-to-end: both build all
five datasets, which against live providers is a couple of minutes and a dozen
rate-limited calls. Their component parts are covered in `test_pipeline.py`;
what is checked here is the wiring — schemas, status codes, and the provenance
fields that stop a synthetic run being mistaken for a real one.
"""

from __future__ import annotations

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")


@pytest.fixture(scope="module")
def client():
    from backend.app.main import app

    return fastapi_testclient.TestClient(app)


class TestHealth:
    def test_reports_ok_and_every_provider_slot(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200

        body = r.json()
        assert body["status"] == "ok"
        assert set(body["providers"]) == {
            "prices", "news", "community", "macro_text", "macro_numeric"
        }

    def test_names_which_slots_are_synthetic(self, client):
        """A bare `synthetic: true` cannot distinguish 'no FRED key' from
        'nothing configured at all', and those are very different."""
        body = client.get("/api/health").json()
        assert isinstance(body["syntheticSlots"], list)
        assert isinstance(body["fullySynthetic"], bool)
        for slot in body["syntheticSlots"]:
            assert body["providers"][slot] == "synthetic"


class TestWindows:
    def test_returns_all_five_windows(self, client):
        r = client.get("/api/windows?as_of=2025-06-15")
        assert r.status_code == 200

        windows = r.json()["windows"]
        assert set(windows) == {
            "prices_equity", "news_baseline", "news_recent", "prices_index", "macro"
        }

    def test_no_window_reaches_the_as_of_date(self, client):
        """The leakage rule, as the API reports it."""
        body = client.get("/api/windows?as_of=2025-06-15").json()
        for name, w in body["windows"].items():
            assert w["end"] <= body["as_of"], f"{name} ends at or after as_of"

    def test_news_windows_tile_the_year(self, client):
        w = client.get("/api/windows?as_of=2025-06-15").json()["windows"]
        assert w["news_baseline"]["end"] == w["news_recent"]["start"]
        assert w["news_recent"]["end"] == "2025-06-15"

    def test_labels_each_window_text_or_tabular(self, client):
        w = client.get("/api/windows?as_of=2025-06-15").json()["windows"]
        kinds = {name: v["kind"] for name, v in w.items()}
        assert kinds["prices_equity"] == "tabular"
        assert kinds["news_baseline"] == "text"
        assert sum(v == "text" for v in kinds.values()) == 3

    def test_defaults_to_today_when_as_of_is_omitted(self, client):
        assert client.get("/api/windows").status_code == 200


class TestResolve:
    def test_resolves_a_known_alias(self, client):
        r = client.get("/api/resolve?q=apple")
        assert r.status_code == 200

        body = r.json()
        assert body["candidates"][0]["symbol"] == "AAPL"

    def test_an_exact_alias_is_unambiguous(self, client):
        """A margin rule got this wrong: "apple" scores 0.90 against a 0.70
        substring hit, and a 0.20 gap is not real ambiguity."""
        assert client.get("/api/resolve?q=apple").json()["unambiguous"]

    def test_a_literal_ticker_is_unambiguous(self, client):
        body = client.get("/api/resolve?q=AAPL").json()
        assert body["unambiguous"]
        assert body["candidates"][0]["source"] == "literal"

    def test_unresolvable_input_is_a_404(self, client):
        """Better than returning a guess -- a wrong resolution poisons the
        forecast and the user has no way to tell which went wrong."""
        assert client.get("/api/resolve?q=zzzznotarealthing").status_code == 404

    def test_empty_query_is_rejected_by_validation(self, client):
        assert client.get("/api/resolve?q=").status_code == 422

    def test_respects_the_limit(self, client):
        assert len(client.get("/api/resolve?q=bank&limit=2").json()["candidates"]) <= 2


class TestPredictContract:
    """Schema-level checks. The endpoint itself needs live data, so this
    verifies the response model rather than calling it."""

    def test_the_untrained_path_is_machine_readable(self):
        """The frontend has to be able to tell a real forecast from the
        placeholder baseline without a human reading a note."""
        from backend.app.routers.predict import ModelInfo, _baseline_forecast
        import pandas as pd

        daily = pd.Series([0.001] * 300)
        expected, info = _baseline_forecast(daily, 21)

        assert isinstance(info, ModelInfo)
        assert info.trained is False
        assert info.kind == "baseline"
        assert isinstance(expected, float)

    def test_the_baseline_shrinks_hard_toward_zero(self):
        """Extrapolating trailing drift naively produces confident nonsense;
        momentum at a 30-day horizon is weak and unstable."""
        from backend.app.routers.predict import _baseline_forecast
        import pandas as pd

        drift = 0.002
        expected, _ = _baseline_forecast(pd.Series([drift] * 300), 21)
        assert abs(expected) < abs(drift * 21)

    def test_allocation_note_flags_leverage_and_shorts(self):
        from backend.app.routers.predict import _allocation_note
        from stocks.finance import portfolio

        levered = portfolio.capital_allocation_line(0.40, 0.15, 0.04, 2.0)
        assert levered.is_levered and "lever" in _allocation_note(levered)

        short = portfolio.capital_allocation_line(0.01, 0.30, 0.05, 4.0)
        assert short.is_short and "short" in _allocation_note(short)


class TestFrontend:
    """The frontend is served as static files from the same process."""

    def test_index_is_served_at_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_static_assets_are_served(self, client):
        assert client.get("/style.css").status_code == 200
        assert client.get("/app.js").status_code == 200

    def test_api_routes_are_not_shadowed_by_the_static_mount(self, client):
        """StaticFiles at "/" is a catch-all, so it must be mounted last."""
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.get("/api/windows").status_code == 200


class TestLegalNotices:
    """These are load-bearing, not decoration.

    Two are licence conditions -- GDELT requires citation and a link, FRED
    requires its sentence verbatim -- and removing either breaches the terms
    that make those APIs free to use. The third is the liability disclaimer the
    whole page exists behind. A test is the only thing that stops a future
    redesign quietly dropping one. See docs/api-terms.md.
    """

    @staticmethod
    def _html(client):
        return client.get("/").text

    def test_not_financial_advice_disclaimer_is_present(self, client):
        html = self._html(client)
        assert "Not financial advice" in html
        assert "no responsibility or liability" in html.lower() or "no liability" in html.lower()

    def test_disclaimer_appears_before_any_forecast_markup(self, client):
        """It has to be read before the number it qualifies, so it is first in
        the DOM and painted first -- not a footer someone scrolls past."""
        html = self._html(client)
        assert html.index("Not financial advice") < html.index('id="resultPanel"')

    def test_disclaimer_is_not_dismissible_by_default(self, client):
        """The bar itself must not start hidden; only the *expanded* text does."""
        html = self._html(client)
        bar = html[html.index('class="disclaimer-bar"'):html.index('id="disclaimerFull"')]
        assert "hidden" not in bar

    def test_gdelt_attribution_and_link_are_present(self, client):
        """GDELT's licence: "any use or redistribution of the data must include
        a citation to the GDELT Project and a link to this website"."""
        html = self._html(client)
        assert "GDELT" in html
        assert "gdeltproject.org" in html

    def test_fred_notice_is_present_verbatim(self, client):
        """FRED requires this exact sentence. It is a quotation from the
        licence -- rewording it does not satisfy the term.

        Whitespace is collapsed before comparing, because the source wraps the
        sentence across lines and HTML renders that as a single space. What has
        to match verbatim is the text a reader sees, not the source layout.
        """
        import re

        required = (
            "This product uses the FRED® API but is not endorsed or "
            "certified by the Federal Reserve Bank of St. Louis."
        )
        rendered = re.sub(r"\s+", " ", self._html(client).replace("&reg;", "®"))
        assert required in rendered

    def test_yahoo_personal_use_limitation_is_disclosed(self, client):
        html = self._html(client)
        assert "personal use only" in html


class TestNewsApiIsOffByDefault:
    """NewsAPI's free plan forbids production use, so a key alone must not
    enable it -- see docs/api-terms.md."""

    def test_key_alone_does_not_enable_it(self):
        from stocks.ingest.news import NewsApiProvider

        assert NewsApiProvider("some-key").available() is False

    def test_key_plus_explicit_flag_enables_it(self):
        from stocks.ingest.news import NewsApiProvider

        assert NewsApiProvider("some-key", allow_nonproduction=True).available() is True

    def test_flag_alone_does_not_enable_it(self):
        from stocks.ingest.news import NewsApiProvider

        assert NewsApiProvider(None, allow_nonproduction=True).available() is False
