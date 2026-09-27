from pathlib import PurePath
from typing import Annotated
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, Response, UploadFile
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.config import Settings, get_settings
from app.errors import AppError, ErrorCode
from app.schemas.job import JobCreated, JobState, utcnow
from app.schemas.options import AnalysisOptions
from app.schemas.profile import DatasetProfile
from app.services.analysis.roles import resolve_column
from app.services.container import Services, get_services
from app.services.ingestion.loader import load_dataset

router = APIRouter(prefix="/jobs", tags=["jobs"])

ServicesDep = Annotated[Services, Depends(get_services)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
MAX_FILENAME_LENGTH = 200
PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


@router.post("", status_code=202, response_model=JobCreated)
async def create_job(
    request: Request,
    background: BackgroundTasks,
    services: ServicesDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File(description="CSV or Excel file")],
    options: Annotated[str | None, Form(description="AnalysisOptions as JSON")] = None,
) -> JobCreated:
    opts = _parse_options(options)
    filename = PurePath(file.filename or "dataset.csv").name[-MAX_FILENAME_LENGTH:]
    data = await file.read(settings.max_upload_bytes + 1)
    df = await run_in_threadpool(load_dataset, data, filename, settings.max_upload_bytes)
    del data
    if opts.target_column:
        resolved = resolve_column(df, opts.target_column)
        if resolved is None:
            raise AppError(
                ErrorCode.INVALID_OPTIONS,
                f"target_column {opts.target_column!r} is not a column in this file.",
            )
        opts.target_column = resolved

    job = JobState(job_id=uuid4().hex, filename=filename, options=opts)
    ingest = job.stage("ingest")
    ingest.status, ingest.started_at, ingest.finished_at = "done", utcnow(), utcnow()
    services.pipeline.admit(job, client_id(request))
    services.store.create(job)
    services.datasets.put(job.job_id, df)
    background.add_task(services.pipeline.run, job.job_id)
    return JobCreated(job_id=job.job_id, status=job.status)


@router.get("/{job_id}", response_model=JobState)
def get_job(job_id: str, services: ServicesDep) -> JobState:
    return _get_or_404(services, job_id)


@router.get("/{job_id}/profile", response_model=DatasetProfile)
def get_job_profile(job_id: str, services: ServicesDep) -> DatasetProfile:
    job = _get_or_404(services, job_id)
    if job.profile is None:
        raise AppError(ErrorCode.PROFILE_NOT_READY, "The dataset profile is not ready yet.")
    return job.profile


@router.get(
    "/{job_id}/deck.pptx",
    response_class=Response,
    responses={200: {"content": {PPTX_MEDIA_TYPE: {}}, "description": "The slide deck"}},
)
def download_deck(job_id: str, services: ServicesDep) -> Response:
    job = _get_or_404(services, job_id)
    data = services.artifacts.get(job_id)
    if data is None:
        if job.status == "completed":
            raise AppError(ErrorCode.JOB_NOT_FOUND, "The deck has expired. Upload the file again.")
        raise AppError(ErrorCode.DECK_NOT_READY, "The slide deck is not ready yet.")
    filename = f"{PurePath(job.filename).stem[:80] or 'analysis'}-deck.pptx"
    return Response(
        content=data,
        media_type=PPTX_MEDIA_TYPE,
        headers={"Content-Disposition": _attachment(filename)},
    )


@router.post("/{job_id}/retry", status_code=202, response_model=JobCreated)
def retry_job(
    job_id: str, request: Request, background: BackgroundTasks, services: ServicesDep
) -> JobCreated:
    job = _get_or_404(services, job_id)
    if job.status != "failed":
        raise AppError(
            ErrorCode.JOB_NOT_RETRYABLE, f"Only failed jobs can be retried (job is {job.status})."
        )
    # Profiling and exploring need the rows; later stages can run from saved findings.
    if job.findings is None and services.datasets.get(job_id) is None:
        raise AppError(
            ErrorCode.JOB_NOT_RETRYABLE,
            "The dataset is no longer available for this job. Upload it again.",
        )
    for stage in job.stages:
        if stage.status == "failed":
            stage.status, stage.message = "pending", None
    job.status, job.error = "queued", None
    if job.insights is None and job.analyst == "claude":
        services.pipeline.admit(job, client_id(request))  # re-check the demo limits
    services.store.save(job)
    background.add_task(services.pipeline.run, job.job_id)
    return JobCreated(job_id=job.job_id, status=job.status)


def client_id(request: Request) -> str:
    """The visitor's IP. Behind Render's proxy the first X-Forwarded-For hop is the client."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _get_or_404(services: Services, job_id: str) -> JobState:
    job = services.store.get(job_id)
    if job is None:
        raise AppError(ErrorCode.JOB_NOT_FOUND, "Job not found. It may have expired.")
    return job


def _attachment(filename: str) -> str:
    """Content-Disposition with an ASCII fallback and the UTF-8 name (RFC 6266)."""
    ascii_name = filename.encode("ascii", "ignore").decode().replace('"', "") or "deck.pptx"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def _parse_options(raw: str | None) -> AnalysisOptions:
    if not raw:
        return AnalysisOptions()
    try:
        return AnalysisOptions.model_validate_json(raw)
    except ValidationError as e:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'options'}: {err['msg']}"
            for err in e.errors()
        )
        raise AppError(ErrorCode.INVALID_OPTIONS, f"Invalid options: {problems}") from e
