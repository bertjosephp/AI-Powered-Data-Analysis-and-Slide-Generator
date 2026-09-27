"""Claude's structured output. Kept free of validation keywords that structured
outputs can't express, so the schema is enforced end to end.

Claims point at evidence through `finding_ids` (F1, F2, …): the statistics come
from those findings, not from the model.
"""

from typing import Literal

from pydantic import BaseModel

from app.schemas.deck import SlideSpec

Confidence = Literal["low", "medium", "high"]


class KeyFinding(BaseModel):
    title: str
    detail: str
    finding_ids: list[str]


class AnsweredQuestion(BaseModel):
    question: str
    answer: str
    finding_ids: list[str]
    confidence: Confidence


class OpenQuestion(BaseModel):
    question: str
    why_it_matters: str


class Hypothesis(BaseModel):
    statement: str
    rationale: str
    test: str
    finding_ids: list[str]
    confidence: Confidence


class Report(BaseModel):
    """Everything but the slides. Claude writes this and the slides in two structured
    calls, because one schema covering both exceeds the API's compiled-grammar limit."""

    executive_summary: str
    key_findings: list[KeyFinding]
    questions_answered: list[AnsweredQuestion]
    open_questions: list[OpenQuestion]
    hypotheses: list[Hypothesis]
    recommended_actions: list[str]
    data_quality_notes: list[str]


class DeckPlan(BaseModel):
    slides: list[SlideSpec]


class Insights(Report):
    slides: list[SlideSpec]


class UnverifiedNumber(BaseModel):
    location: str  # e.g. "key_findings[1].detail"
    value: str
    context: str


class GroundingReport(BaseModel):
    """Numbers in the prose checked against the profile and findings."""

    checked: int
    unverified: list[UnverifiedNumber]
