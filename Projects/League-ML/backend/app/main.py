"""FastAPI application -- the recommender's backend.

Mirrors Stocks' and Portfolio's layout (`backend/app/{main,routers}`) so all
three are navigable the same way. Replaces the draft's #STRETCH-2 ("FastAPI
wrapper, no scaffold") with a skeleton, because Stocks now shows the shape and
there is nothing left to learn from re-deriving it.

    py run.py serve              api on :8000, docs at /docs

Two route groups:

    /api/health     liveness, the target patch, which checkpoints exist
    /api/recommend  top items for a matchup -- 501 until #REC-1 and #REC-2

...plus a frontend at `/` once one exists (#REC-3). Same arrangement as
Stocks: one HTML file, one stylesheet, one script in frontend/, served
straight from here with no build step.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from leagueml import __version__
from leagueml.config import CHECKPOINT_DIR, PATCH_LABEL, TARGET_PATCH

from .routers import recommend as recommend_router

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(
    title="League-ML -- item recommendations",
    description="Riot match data through a neural network to item recommendations for a matchup.",
    version=__version__,
)

app.include_router(recommend_router.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    """Liveness plus what the service would be serving.

    The checkpoint list is here for the same reason Stocks' health endpoint
    names its providers: a service with no trained model can still answer
    requests, and this is how you notice before a user does.
    """
    checkpoints = sorted(p.name for p in CHECKPOINT_DIR.glob("*.pt")) if CHECKPOINT_DIR.is_dir() else []
    return {
        "status": "ok",
        "version": __version__,
        "patch": PATCH_LABEL,
        "gameVersion": TARGET_PATCH,
        "checkpoints": checkpoints,
    }


# Mounted last, after every /api route, because StaticFiles(html=True) at "/"
# is a catch-all and would otherwise shadow them.
if FRONTEND.is_dir():
    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(FRONTEND / "index.html")

    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
else:
    logging.getLogger(__name__).info("no frontend/ yet (#REC-3); serving the API only")
