from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.deck import ResolvedSlide
from app.schemas.findings import ColumnRoles, Finding
from app.schemas.insights import GroundingReport, Insights
from app.schemas.options import AnalysisOptions
from app.schemas.presentation import Presentation
from app.schemas.profile import DatasetProfile

JobStatus = Literal["queued", "running", "completed", "failed"]
StageKey = Literal["ingest", "profile", "explore", "analyze", "generate_deck"]
StageStatus = Literal["pending", "running", "done", "failed"]

STAGE_LABELS: dict[StageKey, str] = {
    "ingest": "Reading file",
    "profile": "Profiling data",
    "explore": "Finding patterns",
    "analyze": "Writing the story",
    "generate_deck": "Building slide deck",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


class Stage(BaseModel):
    key: StageKey
    label: str
    status: StageStatus = "pending"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    message: str | None = None


class JobError(BaseModel):
    stage: StageKey | None
    code: str
    message: str


class JobUsage(BaseModel):
    """Claude usage for this job's analysis (absent for the offline analyst)."""

    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float


class JobState(BaseModel):
    job_id: str
    filename: str
    options: AnalysisOptions
    status: JobStatus = "queued"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    stages: list[Stage] = Field(
        default_factory=lambda: [Stage(key=k, label=v) for k, v in STAGE_LABELS.items()]
    )
    profile: DatasetProfile | None = None
    roles: ColumnRoles | None = None
    findings: list[Finding] | None = None
    insights: Insights | None = None
    grounding: GroundingReport | None = None
    # Which analyst wrote the story, and why it fell back to the offline one if it did.
    analyst: Literal["claude", "mock"] = "mock"
    analyst_note: str | None = None
    usage: JobUsage | None = None
    deck: list[ResolvedSlide] | None = None  # the slides as rendered, for the web preview
    presentation: Presentation | None = None
    error: JobError | None = None

    def stage(self, key: StageKey) -> Stage:
        return next(s for s in self.stages if s.key == key)


class JobCreated(BaseModel):
    job_id: str
    status: JobStatus
