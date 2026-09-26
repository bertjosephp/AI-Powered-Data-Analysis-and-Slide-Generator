from pydantic import BaseModel


class Presentation(BaseModel):
    """The rendered deck. The file itself is served from `download_path` (under /api/v1)."""

    format: str = "pptx"
    slide_count: int
    size_bytes: int
    download_path: str
