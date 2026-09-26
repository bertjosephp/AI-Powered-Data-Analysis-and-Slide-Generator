from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_FILE = "INVALID_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    EMPTY_DATASET = "EMPTY_DATASET"
    LLM_ERROR = "LLM_ERROR"
    LLM_SCHEMA_ERROR = "LLM_SCHEMA_ERROR"
    GAMMA_ERROR = "GAMMA_ERROR"
    GAMMA_TIMEOUT = "GAMMA_TIMEOUT"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    JOB_NOT_RETRYABLE = "JOB_NOT_RETRYABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """A failure with a stable, client-facing error code."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
