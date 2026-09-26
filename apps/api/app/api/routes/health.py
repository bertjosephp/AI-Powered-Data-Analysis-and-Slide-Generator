from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import Settings, get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    anthropic_configured: bool
    gamma_configured: bool
    mock_external: bool


@router.get("/health", response_model=HealthResponse)
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(
        status="ok",
        anthropic_configured=bool(settings.anthropic_api_key),
        gamma_configured=bool(settings.gamma_api_key),
        mock_external=settings.mock_external,
    )
