from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from harnesslab.db.base import Base
from harnesslab.db.models.experiment import JSON_DOCUMENT


class LocalPlanPreflightRecord(Base):
    __tablename__ = "local_plan_preflight"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    digest: Mapped[str] = mapped_column(String(71), unique=True, nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)


class LocalTaskPlanRecord(Base):
    __tablename__ = "local_task_plan"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    preflight_id: Mapped[str] = mapped_column(
        ForeignKey("local_plan_preflight.id"), unique=True, nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    digest: Mapped[str] = mapped_column(String(71), unique=True, nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
