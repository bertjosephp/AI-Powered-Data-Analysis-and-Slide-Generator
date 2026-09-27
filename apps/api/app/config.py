from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables or a .env file."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-5"
    # Deck typeface. Aptos is the default in current Office; override for other viewers.
    deck_font: str = "Aptos"

    max_upload_mb: int = Field(default=25, gt=0)
    profile_sample_rows: int = Field(default=200_000, gt=0)
    job_ttl_s: int = Field(default=3600, gt=0)
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    mock_external: bool = False

    # Claude pricing for cost accounting (USD per million tokens; defaults: claude-sonnet-5).
    llm_input_usd_per_mtok: float = Field(default=2.0, ge=0)
    llm_output_usd_per_mtok: float = Field(default=10.0, ge=0)

    # Public-demo protection. When a limit is hit, runs fall back to the mock analyst.
    demo_runs_per_hour: int = Field(default=3, ge=0)
    daily_budget_usd: float = Field(default=3.0, ge=0)
    max_concurrent_analyses: int = Field(default=2, ge=1)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
