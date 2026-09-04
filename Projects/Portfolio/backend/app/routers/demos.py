"""Interactive demo endpoints.

These are the reason this site has a Python backend at all. Each one runs real
logic from a real project, so what a visitor plays with is the thing itself and
not a recording of it.

Live now:
    remote-classifier   the Jobs Web App's remote/hybrid/US-fence decision

Reserved (the model has to exist first):
    stocks-forecast     inference against the trained forecaster
    lol-build           matchup + rank conditioned build suggestion
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..demos import remote as remote_demo

router = APIRouter(prefix="/api/demos", tags=["demos"])

# A posting body is prose, not a payload. Cap it so a stray paste cannot turn
# into a pile of regex backtracking.
MAX_FIELD = 8000


class RemoteRequest(BaseModel):
    location: str = Field(default="", max_length=500)
    remote_status: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=MAX_FIELD)


@router.get("/remote-classifier/samples")
def remote_samples() -> list[dict]:
    """Worked examples, each chosen because it breaks a naive implementation."""
    return remote_demo.SAMPLES


@router.post("/remote-classifier")
def remote_classify(req: RemoteRequest) -> dict:
    if not (req.location or req.remote_status or req.description):
        raise HTTPException(status_code=422, detail="give it a location or a description to read")

    result = remote_demo.classify_remote(
        location=req.location,
        remote_status=req.remote_status,
        description=req.description,
    )
    return result.as_dict()


@router.get("/registry")
def registry() -> list[dict]:
    """What the frontend uses to decide which demos to render as live."""
    return [
        {
            "id": "remote-classifier",
            "project": "jobs-workbench",
            "name": "Remote classifier",
            "blurb": "Paste a posting. Watch three gates decide whether it is really remote.",
            "live": True,
        },
        {
            "id": "diagnostics-readout",
            "project": "diagnostics-toolkit",
            "name": "Telemetry readout",
            "blurb": "A simulated run of the diagnostics engine's snapshot output.",
            "live": True,
            "clientOnly": True,
        },
        {
            "id": "stocks-forecast",
            "project": "stocks-forecaster",
            "name": "Forecast inference",
            "blurb": "Waiting on the model.",
            "live": False,
        },
        {
            "id": "lol-build",
            "project": "lol-build-suggestor",
            "name": "Build suggestion",
            "blurb": "Waiting on the matchup data pull.",
            "live": False,
        },
    ]
