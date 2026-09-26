"""Bundled example datasets, so the product can be tried without your own data."""

import json
from functools import cache
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.errors import AppError, ErrorCode

router = APIRouter(prefix="/samples", tags=["samples"])

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample_data"


class Sample(BaseModel):
    name: str
    title: str
    description: str
    rows: int
    columns: int
    suggested_question: str
    suggested_target: str
    filename: str


@cache
def _catalog() -> dict[str, Sample]:
    samples: dict[str, Sample] = {}
    for manifest_path in sorted(SAMPLE_DIR.glob("*.expected.json")):
        m = json.loads(manifest_path.read_text())
        samples[m["name"]] = Sample(
            name=m["name"],
            title=m["title"],
            description=m["description"],
            rows=m["rows"],
            columns=m["columns"],
            suggested_question=m["suggested_question"],
            suggested_target=m["suggested_target"],
            filename=f"{m['name']}.csv",
        )
    return samples


@router.get("", response_model=list[Sample])
def list_samples() -> list[Sample]:
    return list(_catalog().values())


@router.get("/{name}.csv", response_class=FileResponse)
def download_sample(name: str) -> FileResponse:
    sample = _catalog().get(name)  # only names from the catalog; never a raw path
    if sample is None:
        raise AppError(ErrorCode.SAMPLE_NOT_FOUND, f"No sample dataset named {name!r}.")
    return FileResponse(
        SAMPLE_DIR / sample.filename, media_type="text/csv", filename=sample.filename
    )
