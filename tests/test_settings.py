from __future__ import annotations

import pytest
from pydantic import ValidationError

from harnesslab.core.config import Settings


def test_valid_configuration_is_loaded_without_exposing_secret() -> None:
    settings = Settings.without_dotenv(
        environment="TEST",
        database_url="postgresql+psycopg://user:super-secret@localhost:5432/harnesslab",
    )

    assert settings.environment == "test"
    assert settings.database_url_value.endswith("/harnesslab")
    assert "super-secret" not in repr(settings)
    assert "**********" in repr(settings)


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///harnesslab.db",
        "postgresql+psycopg://localhost",
        "postgresql+asyncpg://user:pass@localhost/harnesslab",
    ],
)
def test_invalid_database_url_fails_clearly(url: str) -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL must use postgresql\\+psycopg"):
        Settings.without_dotenv(database_url=url)


def test_missing_database_url_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(_env_file=None)
