from dataclasses import dataclass, field
from typing import Protocol

from app.schemas.findings import ColumnRoles, Finding
from app.schemas.insights import Insights
from app.schemas.options import AnalysisOptions
from app.schemas.profile import DatasetProfile
from app.services.analysis.analyses import Frame
from app.services.llm.usage import Usage


@dataclass
class AnalysisContext:
    """Everything the analyst works from. `frame` powers follow-up tools; when the
    dataset is no longer available it is None and the analyst works from findings only."""

    profile: DatasetProfile
    findings: list[Finding]
    roles: ColumnRoles
    options: AnalysisOptions
    dataset_name: str
    frame: Frame | None = None


@dataclass
class AnalystOutput:
    insights: Insights
    follow_ups: list[Finding] = field(default_factory=list)
    tool_calls: int = 0
    usage: Usage | None = None  # None for the mock analyst


class InsightsGenerator(Protocol):
    async def generate(self, context: AnalysisContext) -> AnalystOutput: ...
