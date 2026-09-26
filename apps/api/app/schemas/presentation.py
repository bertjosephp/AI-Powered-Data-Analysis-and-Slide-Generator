from typing import Literal

from pydantic import BaseModel

GenerationStatus = Literal["pending", "completed", "failed"]


class Presentation(BaseModel):
    gamma_generation_id: str
    status: GenerationStatus
    gamma_url: str | None = None
    export_url: str | None = None
    credits_deducted: float | None = None
    mock: bool = False
