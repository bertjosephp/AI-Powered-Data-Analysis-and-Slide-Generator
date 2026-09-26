from typing import Literal

from pydantic import BaseModel, Field


class AnalysisOptions(BaseModel):
    """User-tunable knobs sent alongside the upload."""

    num_slides: int = Field(default=10, ge=4, le=25)
    tone: Literal["executive", "technical", "casual"] = "executive"
    audience: str = Field(default="business stakeholders", max_length=200)
    theme: str | None = Field(default=None, max_length=100)
