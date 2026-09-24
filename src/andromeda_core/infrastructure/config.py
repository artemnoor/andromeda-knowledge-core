"""Validated application settings."""

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "Andromeda Knowledge Core"
    log_level: str = "INFO"
    database_url: str = "sqlite+aiosqlite:///./andromeda.db"
    engine_version: str = "engine-0.1.0"
    auto_seed: bool = False
    api_docs_enabled: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    max_request_body_bytes: Annotated[int, Field(gt=0, le=10_000_000)] = 1_048_576
    max_dsl_depth: Annotated[int, Field(gt=1, le=100)] = 30
    max_trace_nodes: Annotated[int, Field(gt=10, le=100_000)] = 5_000
    confidence_review_threshold: Annotated[float, Field(ge=0, le=1)] = 0.8
    enable_security_headers: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
