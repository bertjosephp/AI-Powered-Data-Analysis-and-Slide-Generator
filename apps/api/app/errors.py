from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_FILE = "INVALID_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    EMPTY_DATASET = "EMPTY_DATASET"
    LLM_ERROR = "LLM_ERROR"
    LLM_SCHEMA_ERROR = "LLM_SCHEMA_ERROR"
    DECK_RENDER_ERROR = "DECK_RENDER_ERROR"
    INVALID_OPTIONS = "INVALID_OPTIONS"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    PROFILE_NOT_READY = "PROFILE_NOT_READY"
    DECK_NOT_READY = "DECK_NOT_READY"
    DATASET_EXPIRED = "DATASET_EXPIRED"
    SAMPLE_NOT_FOUND = "SAMPLE_NOT_FOUND"
    JOB_NOT_RETRYABLE = "JOB_NOT_RETRYABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """A failure with a stable, client-facing error code."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
