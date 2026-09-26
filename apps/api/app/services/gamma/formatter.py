"""Insights -> Gamma create-generation request body."""

from typing import Any

from app.schemas.insights import Insights, SlideOutline
from app.schemas.options import AnalysisOptions

CARD_BREAK = "\n---\n"
MAX_INPUT_CHARS = 400_000

_TEXT_AMOUNT = {"executive": "brief", "technical": "detailed", "casual": "medium"}
_TONE = {
    "executive": "professional, concise, confident",
    "technical": "precise, analytical",
    "casual": "friendly, plain-spoken",
}

ADDITIONAL_INSTRUCTIONS = (
    "Keep one card per section of the input. Use only the figures that appear in the input; "
    "do not invent statistics, dates or trends. Present correlations as associations, "
    "not causes."
)


def to_gamma_request(
    insights: Insights, options: AnalysisOptions, dataset_name: str, image_source: str
) -> dict[str, Any]:
    slides = insights.slide_outline
    body: dict[str, Any] = {
        "inputText": build_input_text(slides)[:MAX_INPUT_CHARS],
        "textMode": "generate",
        "format": "presentation",
        "numCards": len(slides),
        "cardSplit": "inputTextBreaks",
        "title": slides[0].title if slides else f"Analysis of {dataset_name}",
        "additionalInstructions": ADDITIONAL_INSTRUCTIONS,
        "textOptions": {
            "amount": _TEXT_AMOUNT[options.tone],
            "tone": _TONE[options.tone],
            "audience": options.audience,
            "language": "en",
        },
        "imageOptions": {"source": image_source},
    }
    if options.theme_id:
        body["themeId"] = options.theme_id
    if options.export_as:
        body["exportAs"] = options.export_as
    return body


def build_input_text(slides: list[SlideOutline]) -> str:
    cards = []
    for slide in slides:
        bullets = "\n".join(f"- {b}" for b in slide.bullets)
        cards.append(f"# {slide.title}\n{bullets}".rstrip())
    return CARD_BREAK.join(cards)
