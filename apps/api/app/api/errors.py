"""Every non-2xx response uses {"error": {"code", "message", "details"?}}."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.errors import AppError, ErrorCode

_HTTP_STATUS = {
    ErrorCode.INVALID_FILE: 400,
    ErrorCode.EMPTY_DATASET: 400,
    ErrorCode.INVALID_OPTIONS: 400,
    ErrorCode.FILE_TOO_LARGE: 413,
    ErrorCode.JOB_NOT_FOUND: 404,
    ErrorCode.JOB_NOT_RETRYABLE: 409,
    ErrorCode.PROFILE_NOT_READY: 409,
}


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            error_body(exc.code, exc.message), status_code=_HTTP_STATUS.get(exc.code, 500)
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg", "")} for e in exc.errors()]
        return JSONResponse(
            error_body("VALIDATION_ERROR", "The request is invalid.", details), status_code=422
        )

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            error_body(f"HTTP_{exc.status_code}", str(exc.detail)), status_code=exc.status_code
        )
