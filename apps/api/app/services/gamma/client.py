"""Async client for Gamma's generations API (v1.0).

POST /generations returns a generationId; GET /generations/{id} is polled until
status is "completed" or "failed". Creation is kept separate from waiting so the
caller can persist the id and resume polling on retry, instead of paying for a
second deck.
"""

import asyncio
import time
from typing import Any, Protocol

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.errors import AppError, ErrorCode
from app.schemas.presentation import Presentation

REQUEST_TIMEOUT_S = 30.0
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_STATUS_MESSAGES = {
    400: "Gamma rejected the request",
    401: "The Gamma API key was rejected",
    402: "The Gamma workspace is out of credits",
    403: "The Gamma API key lacks access to this feature",
    404: "Gamma generation not found",
}


class GammaGenerator(Protocol):
    async def create_generation(self, body: dict[str, Any]) -> str: ...

    async def wait_for_completion(self, generation_id: str) -> Presentation: ...


class GammaClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout_s: float,
        poll_interval_s: float,
        http: httpx.AsyncClient | None = None,
        retry_wait: Any = None,
    ) -> None:
        self._timeout_s = timeout_s
        self._retry_wait = retry_wait or wait_exponential(multiplier=1, max=10)
        self._poll_interval_s = poll_interval_s
        self._http = http or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S)
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}

    async def aclose(self) -> None:
        await self._http.aclose()

    async def create_generation(self, body: dict[str, Any]) -> str:
        # Only retry failures where Gamma cannot have started a generation, so a
        # retry never produces (and bills) a duplicate deck.
        data = await self._request(
            "POST", "/generations", json=body, retry_on=_is_safe_to_retry_create
        )
        generation_id = data.get("generationId")
        if not isinstance(generation_id, str):
            raise AppError(ErrorCode.GAMMA_ERROR, "Gamma did not return a generation id.")
        return generation_id

    async def get_generation(self, generation_id: str) -> Presentation:
        data = await self._request("GET", f"/generations/{generation_id}", retry_on=_is_transient)
        status = data.get("status")
        if status not in ("pending", "completed", "failed"):
            raise AppError(ErrorCode.GAMMA_ERROR, f"Unexpected Gamma status: {status!r}.")
        if status == "failed":
            error = data.get("error") or {}
            raise AppError(
                ErrorCode.GAMMA_ERROR,
                f"Gamma could not generate the deck: {error.get('message', 'unknown error')}",
            )
        credits = data.get("credits") or {}
        return Presentation(
            gamma_generation_id=generation_id,
            status=status,
            gamma_url=data.get("gammaUrl"),
            export_url=data.get("exportUrl"),
            credits_deducted=credits.get("deducted"),
        )

    async def wait_for_completion(self, generation_id: str) -> Presentation:
        deadline = time.monotonic() + self._timeout_s
        while True:
            presentation = await self.get_generation(generation_id)
            if presentation.status == "completed":
                return presentation
            if time.monotonic() + self._poll_interval_s > deadline:
                raise AppError(
                    ErrorCode.GAMMA_TIMEOUT,
                    f"Gamma did not finish within {self._timeout_s:.0f}s. "
                    "Retry to keep waiting on the same generation.",
                )
            await asyncio.sleep(self._poll_interval_s)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        retry_on: Any,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception(retry_on),
                stop=stop_after_attempt(4),
                wait=self._retry_wait,
                reraise=True,
            ):
                with attempt:
                    res = await self._http.request(
                        method, self._base_url + path, headers=self._headers, json=json
                    )
                    res.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise _to_app_error(e.response) from e
        except httpx.TimeoutException as e:
            raise AppError(ErrorCode.GAMMA_ERROR, "Timed out talking to the Gamma API.") from e
        except httpx.TransportError as e:
            raise AppError(ErrorCode.GAMMA_ERROR, "Could not reach the Gamma API.") from e

        try:
            data = res.json()
        except ValueError as e:
            raise AppError(ErrorCode.GAMMA_ERROR, "Gamma returned a non-JSON response.") from e
        if not isinstance(data, dict):
            raise AppError(ErrorCode.GAMMA_ERROR, "Gamma returned an unexpected response.")
        return data


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    return isinstance(exc, httpx.TransportError)


def _is_safe_to_retry_create(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429
    return isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout)


def _to_app_error(res: httpx.Response) -> AppError:
    detail = ""
    try:
        body = res.json()
        if isinstance(body, dict):
            detail = str(body.get("message") or body.get("error") or "")
    except ValueError:
        pass
    base = _STATUS_MESSAGES.get(res.status_code, f"Gamma API error {res.status_code}")
    return AppError(ErrorCode.GAMMA_ERROR, f"{base}: {detail}" if detail else f"{base}.")
