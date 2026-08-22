from __future__ import annotations

import os

import pytest


@pytest.fixture
def database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        pytest.fail("DATABASE_URL is required for Gate A database tests")
    return value
