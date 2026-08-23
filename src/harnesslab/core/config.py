from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables and a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    environment: str = Field(default="development", alias="HARNESSLAB_ENVIRONMENT")
    database_url: SecretStr = Field(alias="DATABASE_URL")
    workbench_artifact_roots: tuple[Path, ...] = Field(
        default=(Path("artifacts"), Path("harnesslab-artifacts")),
        alias="HARNESSLAB_WORKBENCH_ARTIFACT_ROOTS",
    )

    @field_validator("environment")
    @classmethod
    def environment_is_named(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("environment must not be empty")
        return value

    @field_validator("database_url")
    @classmethod
    def database_url_uses_psycopg(cls, value: SecretStr) -> SecretStr:
        parsed = urlsplit(value.get_secret_value())
        if (
            parsed.scheme != "postgresql+psycopg"
            or not parsed.hostname
            or not parsed.path.strip("/")
        ):
            raise ValueError(
                "DATABASE_URL must use postgresql+psycopg and include a host and database name"
            )
        return value

    @field_validator("workbench_artifact_roots")
    @classmethod
    def artifact_roots_are_explicit(cls, value: tuple[Path, ...]) -> tuple[Path, ...]:
        if not value:
            raise ValueError("at least one Workbench artifact root is required")
        return value

    @property
    def database_url_value(self) -> str:
        return self.database_url.get_secret_value()

    @classmethod
    def without_dotenv(cls, *, database_url: str, environment: str = "development") -> Self:
        return cls(
            _env_file=None,
            database_url=SecretStr(database_url),
            environment=environment,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
