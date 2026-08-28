from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column

from harnesslab.db.base import Base
from harnesslab.db.models.experiment import JSON_DOCUMENT


class RegistryExperimentSnapshotRecord(Base):
    """Immutable planning snapshot; it creates no experiment run or queue row."""

    __tablename__ = "registry_experiment_snapshot"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    snapshot_digest: Mapped[str] = mapped_column(String(71), nullable=False, unique=True)
    methodology_id: Mapped[str] = mapped_column(String(100), nullable=False)
    methodology_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    preflight_status: Mapped[str] = mapped_column(String(30), nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
