"""Finds slide text that is longer than its box, so Claude can rewrite it shorter.

Structured outputs can't enforce string lengths, and Claude sometimes runs a few
characters over. Clipping those (fit.py) cuts them mid-phrase, so the analyst first
asks Claude to shorten just the overlong strings; clipping remains the fallback.
"""

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.schemas.insights import DeckPlan
from app.services.deck import fit

# Per layout: field -> box limit, and list field -> (item field or None) -> limit.
_FIELDS: dict[str, dict[str, int]] = {
    "title": {"title": fit.TITLE, "subtitle": fit.SUBTITLE},
    "executive_summary": {"headline": fit.HEADLINE},
    "kpi_cards": {"title": fit.TITLE},
    "chart_insight": {"title": fit.TITLE},
    "hypotheses": {"title": fit.TITLE},
    "next_steps": {"title": fit.TITLE},
}
_LISTS: dict[str, dict[str, dict[str | None, int]]] = {
    "executive_summary": {"takeaways": {"title": fit.CARD_TITLE, "text": fit.CARD_TEXT}},
    "kpi_cards": {"kpis": {"label": fit.KPI_LABEL}},
    "chart_insight": {"bullets": {None: fit.BULLET}},
    "hypotheses": {"items": {"statement": fit.STATEMENT, "test": fit.STATEMENT}},
    "next_steps": {"steps": {None: fit.STEP}},
}

SHORTEN_SYSTEM = (
    "You shorten slide text to fit fixed-size boxes. Rewrite each text to at most its "
    "character limit while keeping its meaning. Keep every number, name and finding "
    "exactly as written, and never add new facts. Return every id you were given."
)


@dataclass(frozen=True)
class Overlong:
    id: str  # a path into the slides, e.g. "slides[3].bullets[1]"
    text: str
    limit: int


class Rewrite(BaseModel):
    id: str
    text: str


class Rewrites(BaseModel):
    items: list[Rewrite]


def find_overlong(deck: DeckPlan) -> list[Overlong]:
    found: list[Overlong] = []
    for i, slide in enumerate(deck.model_dump()["slides"]):
        layout = slide["layout"]
        for field, limit in _FIELDS.get(layout, {}).items():
            _check(found, f"slides[{i}].{field}", slide[field], limit)
        for field, parts in _LISTS.get(layout, {}).items():
            for j, item in enumerate(slide[field]):
                for part, limit in parts.items():
                    text = item if part is None else item[part]
                    suffix = "" if part is None else f".{part}"
                    _check(found, f"slides[{i}].{field}[{j}]{suffix}", text, limit)
    return found


def shorten_prompt(overlong: list[Overlong]) -> str:
    items = [{"id": o.id, "limit": o.limit, "text": o.text} for o in overlong]
    return "Shorten these texts:\n" + json.dumps(items, ensure_ascii=False, indent=1)


def apply_rewrites(deck: DeckPlan, overlong: list[Overlong], rewrites: Rewrites) -> DeckPlan:
    """Applies rewrites that are actually shorter, only at the ids that were asked for."""
    wanted = {o.id: o for o in overlong}
    data = deck.model_dump()
    for r in rewrites.items:
        asked = wanted.get(r.id)
        text = " ".join(r.text.split())
        if asked is None or not text or len(text) >= len(asked.text):
            continue
        _set(data, r.id, text)
    return DeckPlan.model_validate(data)


def _check(found: list[Overlong], path: str, text: str, limit: int) -> None:
    if len(" ".join(text.split())) > limit:
        found.append(Overlong(path, text, limit))


def _set(data: dict[str, Any], path: str, value: str) -> None:
    """Sets e.g. "slides[3].bullets[1]" or "slides[1].takeaways[0].title"."""
    target: Any = data
    steps: list[str | int] = []
    for part in path.split("."):
        name, _, rest = part.partition("[")
        steps.append(name)
        steps += [int(k) for k in rest.rstrip("]").split("][")] if rest else []
    for step in steps[:-1]:
        target = target[step]
    target[steps[-1]] = value
