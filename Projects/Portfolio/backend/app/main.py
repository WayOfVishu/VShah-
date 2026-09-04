"""FastAPI application entry point.

Two jobs: serve the content and demo APIs, and in production serve the built
frontend as static files. In development the frontend runs on Vite's own dev
server and proxies /api here, so this process only handles the API.

    dev   py run.py                 (api on :8000, vite on :5173)
    prod  py run.py --serve-static  (one process on :8000, serves frontend/dist)
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routers import content as content_router
from .routers import demos as demos_router

DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

# In dev the frontend is a different origin (Vite on 5173). In prod it is the
# same origin, so this list only ever matters locally.
DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app = FastAPI(
    title="Vihang Shah — Portfolio API",
    description="Content and live project demos for vihangshah.dev",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_ORIGINS + [o for o in os.getenv("PORTFOLIO_ORIGINS", "").split(",") if o],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(content_router.router)
app.include_router(demos_router.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "staticMounted": DIST.exists()}


def mount_static() -> None:
    """Serve the built frontend, with SPA-style fallback to index.html.

    Called only when running with --serve-static, so a dev run does not fail
    just because frontend/dist has not been built yet.
    """
    if not DIST.exists():
        raise SystemExit(
            f"no build found at {DIST}\n"
            "run `npm run build` in frontend/ first, or start without --serve-static"
        )

    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        candidate = DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
