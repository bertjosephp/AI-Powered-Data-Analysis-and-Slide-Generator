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
