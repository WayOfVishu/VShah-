"""Read-only content endpoints.

Everything here is derived from ``app/data/*.json``. No database, because the
content changes when I edit a file, not when a user does something.
"""

from fastapi import APIRouter, HTTPException

from .. import content

router = APIRouter(prefix="/api", tags=["content"])


@router.get("/summary")
def get_summary() -> dict:
    """One call that paints the whole landing page."""
    return content.summary()


@router.get("/profile")
def get_profile() -> dict:
    return content.profile()


@router.get("/projects")
def get_projects() -> list[dict]:
    return content.projects()


@router.get("/projects/{slug}")
def get_project(slug: str) -> dict:
    found = content.project(slug)
    if not found:
        raise HTTPException(status_code=404, detail=f"no project with slug {slug!r}")
    return found


@router.get("/experience")
def get_experience() -> list[dict]:
    return content.experience()


@router.get("/skills")
def get_skills() -> list[dict]:
    return content.skills()
