"""FastAPI application -- the web app's backend.

Mirrors the Portfolio project's layout (`backend/app/{main,routers}`) so the
two are navigable the same way, and so this can eventually be mounted behind
the same process.

    py run.py serve                app + api on :8000

Four route groups:

    /api/resolve   free text -> ticker candidates
    /api/datasets  the retrieval windows for a ticker, summarised
    /api/predict   the 30-day forecast plus a Chapter 6 position recommendation
    /api/health    liveness, and which providers resolved

...plus the frontend itself at `/`, served straight from `frontend/` as static
files. There is no build step: it is one HTML file, one stylesheet, and one
script, in the same shape as the Jobs dashboard's `public/`. A bundler here
would add a toolchain to maintain and buy nothing, since the page loads three
files and imports nothing.

**On latency.** A cold `/api/predict` builds every dataset, which means a
dozen provider calls with rate limits between them -- a minute or two, not
milliseconds. The disk cache makes repeat calls fast, but a first request for
an unseen ticker will be slow, and the frontend shows a paced progress list
because of it. A production deployment would move this to a job queue and poll;
that is noted in `docs/project-charter.md` Section 8 rather than built here,
because the queue is only worth adding once the model is worth serving.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from stocks import __version__
from stocks.config import get_settings

from .routers import datasets as datasets_router
from .routers import predict as predict_router
from .routers import resolve as resolve_router

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)-28s %(message)s")

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

# Only relevant if you ever serve the frontend from a different origin. As
# shipped it is same-origin, so this list is empty in practice.
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

app = FastAPI(
    title="Stocks -- 30-Day Forecast API",
    description=(
        "Five datasets (prices, news baseline, recent news, indices, macro) "
        "through an ML pipeline to a 30-day forecast."
    ),
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_ORIGINS + list(get_settings().origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(resolve_router.router)
app.include_router(datasets_router.router)
app.include_router(predict_router.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    """Liveness plus provider provenance.

    The provider table is included deliberately: a deployment silently running
    on synthetic data would return confident, meaningless forecasts, and this
    endpoint is how you notice.
    """
    from stocks.ingest.registry import Registry

    registry = Registry()
    providers = {
        "prices": registry.prices.name,
        "news": registry.news.name,
        "community": registry.community.name if registry.community else None,
        "macro_text": registry.macro_text.name,
        "sentiment": registry.sentiment.name,
        "macro_numeric": registry.macro_numeric.name,
    }
    # Named rather than a bare boolean. "synthetic: true" because FRED has no
    # key reads identically to "synthetic: true" because nothing is configured
    # at all, and those are very different situations -- the first still gives
    # real prices and real news.
    synthetic = sorted(k for k, v in providers.items() if v == "synthetic")

    return {
        "status": "ok",
        "version": __version__,
        "providers": providers,
        "syntheticSlots": synthetic,
        "fullySynthetic": len(synthetic) >= 4,
    }


# Mounted last, after every /api route, because StaticFiles(html=True) at "/"
# is a catch-all and would otherwise shadow them.
if FRONTEND.is_dir():
    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(FRONTEND / "index.html")

    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
else:  # pragma: no cover -- only if the directory is deleted
    logging.getLogger(__name__).warning("no frontend/ directory at %s; serving API only", FRONTEND)
