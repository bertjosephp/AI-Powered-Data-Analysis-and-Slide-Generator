from anthropic import AsyncAnthropic

from app.config import Settings

LLM_TIMEOUT_S = 300.0


def make_anthropic_client(settings: Settings) -> AsyncAnthropic:
    return AsyncAnthropic(
        api_key=settings.anthropic_api_key or None,
        timeout=LLM_TIMEOUT_S,
        max_retries=3,
    )
