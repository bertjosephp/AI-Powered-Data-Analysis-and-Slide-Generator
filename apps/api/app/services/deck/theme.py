"""Design tokens for generated decks. Mirrors the web app's palette (globals.css)."""

from dataclasses import dataclass
from typing import cast

from pptx.dml.color import RGBColor
from pptx.util import Inches, Length


def rgb(hex_color: str) -> RGBColor:
    return cast(RGBColor, RGBColor.from_string(hex_color.lstrip("#")))  # type: ignore[no-untyped-call]


@dataclass(frozen=True)
class Theme:
    font: str = "Aptos"

    # Surfaces
    dark_bg: str = "#101016"
    canvas: str = "#F6F6F8"
    card: str = "#FFFFFF"
    card_border: str = "#E4E4EA"

    # Ink
    ink: str = "#16161D"
    muted: str = "#5F6070"
    on_dark: str = "#F2F2F6"
    on_dark_muted: str = "#A3A3B5"

    # Accent (indigo) and data colors (validated diverging pair, see web viz tokens)
    accent: str = "#4F46E5"
    accent_soft: str = "#EEF0FF"
    accent_muted: str = "#C9C6F5"  # de-emphasized bars; the standout stays full accent
    motif_dark: str = "#23233A"  # decorative shapes on dark slides
    accent_on_dark: str = "#8B85FF"
    positive: str = "#2A78D6"
    negative: str = "#E34948"

    # Geometry (16:9)
    width: Length = Inches(13.333)
    height: Length = Inches(7.5)
    margin: Length = Inches(0.6)
    gutter: Length = Inches(0.3)
    corner: float = 0.06  # rounded-rectangle adjustment, relative to the short side

    @property
    def content_width(self) -> int:
        return int(self.width - 2 * self.margin)


DEFAULT_THEME = Theme()
