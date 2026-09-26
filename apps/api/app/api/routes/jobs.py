from pathlib import PurePath
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.config import Settings, get_settings
from app.errors import AppError, ErrorCode
from app.schemas.job import JobCreated, JobState, utcnow
from app.schemas.options import AnalysisOptions
from app.schemas.profile import DatasetProfile
from app.services.container import Services, get_services
from app.services.ingestion.loader import load_dataset

router = APIRouter(prefix="/jobs", tags=["jobs"])

ServicesDep = Annotated[Services, Depends(get_services)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
MAX_FILENAME_LENGTH = 200


@router.post("", status_code=202, response_model=JobCreated)
async def create_job(
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

    job = JobState(job_id=uuid4().hex, filename=filename, options=opts)
    ingest = job.stage("ingest")
    ingest.status, ingest.started_at, ingest.finished_at = "done", utcnow(), utcnow()
    services.store.create(job)
    background.add_task(services.pipeline.run, job.job_id, df)
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


@router.post("/{job_id}/retry", status_code=202, response_model=JobCreated)
def retry_job(job_id: str, background: BackgroundTasks, services: ServicesDep) -> JobCreated:
    job = _get_or_404(services, job_id)
    if job.status != "failed":
        raise AppError(
            ErrorCode.JOB_NOT_RETRYABLE, f"Only failed jobs can be retried (job is {job.status})."
        )
    if job.profile is None:
        raise AppError(
            ErrorCode.JOB_NOT_RETRYABLE,
            "The dataset is no longer available for this job. Upload it again.",
        )
    for stage in job.stages:
        if stage.status == "failed":
            stage.status, stage.message = "pending", None
    job.status, job.error = "queued", None
    services.store.save(job)
    background.add_task(services.pipeline.run, job.job_id)
    return JobCreated(job_id=job.job_id, status=job.status)


def _get_or_404(services: Services, job_id: str) -> JobState:
    job = services.store.get(job_id)
    if job is None:
        raise AppError(ErrorCode.JOB_NOT_FOUND, "Job not found. It may have expired.")
    return job


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
