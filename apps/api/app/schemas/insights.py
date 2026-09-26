"""Claude's structured output. Kept free of validation keywords that
structured outputs can't express, so the schema is enforced end to end."""

from typing import Literal

from pydantic import BaseModel


class KeyFinding(BaseModel):
    title: str
    detail: str
    supporting_stats: list[str]


class Hypothesis(BaseModel):
    statement: str
    rationale: str
    suggested_test: str
    confidence: Literal["low", "medium", "high"]


class AnalyticalQuestion(BaseModel):
    question: str
    why_it_matters: str


class SlideOutline(BaseModel):
    title: str
    bullets: list[str]


class Insights(BaseModel):
    executive_summary: str
    key_findings: list[KeyFinding]
    hypotheses: list[Hypothesis]
    analytical_questions: list[AnalyticalQuestion]
    data_quality_notes: list[str]
    recommended_next_steps: list[str]
    slide_outline: list[SlideOutline]
