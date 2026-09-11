"""POST /api/recommend -- the CLI's `recommend` command, over HTTP.

# TODO (Phase 5 -- see docs/TODO.md #REC-2)
#
# The request/response models below are done -- they are the contract, and
# FastAPI turns them into validation and the /docs page for free. The handler
# is yours, and it is mostly one design question:
#
#   Where does the model come from? Loading a checkpoint on every request
#   rebuilds the network and re-reads the file each time -- fine at one
#   request a minute, wasteful at ten a second. Load once at startup (look up
#   FastAPI's lifespan handler) and keep it on app.state. Then: what does the
#   endpoint return while no checkpoint exists at all? A 503 with a message
#   beats a 500 with a traceback.
#
# Also worth a sentence: recommend_items() is CPU-bound and synchronous. A
# plain `def` handler (as below) runs in FastAPI's threadpool, which is
# correct; an `async def` handler would block the event loop for the length of
# the forward pass. Know why before you "upgrade" it.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["recommend"])

Role = Literal["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]


class RecommendRequest(BaseModel):
    champion: str = Field(..., examples=["Ahri"])
    enemy: str = Field(..., examples=["Zed"], description="the enemy laner")
    role: Role
    top_k: int = Field(3, ge=1, le=10)


class ItemScore(BaseModel):
    item: str
    lift: float = Field(..., description="predicted win-probability lift over #REC-1's baseline")


@router.post("/recommend", response_model=list[ItemScore])
def recommend(request: RecommendRequest) -> list[ItemScore]:
    raise HTTPException(status_code=501,
                        detail="recommendations are not built yet -- see docs/TODO.md #REC-1 and #REC-2")
