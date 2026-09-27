from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.routes.jobs import client_id
from app.config import Settings, get_settings
from app.services.container import Services, get_services

router = APIRouter(tags=["health"])


class DemoStatus(BaseModel):
    runs_per_hour: int
    runs_left_this_hour: int
    budget_remaining_usd: float
    claude_available: bool


class HealthResponse(BaseModel):
    status: str
    anthropic_configured: bool
    mock_external: bool
    commit: str | None = None
    demo: DemoStatus | None = None


@router.get("/health", response_model=HealthResponse)
def health(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    services: Annotated[Services, Depends(get_services)],
) -> HealthResponse:
    demo = None
    if services.guard is not None:
        status = services.guard.status()
        left = services.guard.remaining_for(client_id(request))
        demo = DemoStatus(
            runs_per_hour=status.runs_per_hour,
            runs_left_this_hour=left,
            budget_remaining_usd=status.budget_remaining_usd,
            claude_available=left > 0 and status.budget_remaining_usd > 0,
        )
    return HealthResponse(
        status="ok",
        anthropic_configured=bool(settings.anthropic_api_key),
        mock_external=settings.mock_external,
        commit=settings.git_commit,
        demo=demo,
    )
