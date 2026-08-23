from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from harnesslab.db.base import Base

JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class JudgeCalibrationRecord(Base):
    __tablename__ = "judge_calibration"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_digest: Mapped[str] = mapped_column(String(71), nullable=False, unique=True)
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'planned'")
    )
    report_json_path: Mapped[str | None] = mapped_column(Text)
    report_markdown_path: Mapped[str | None] = mapped_column(Text)
    report_digest: Mapped[str | None] = mapped_column(String(71))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JudgeEvaluationRecord(Base):
    __tablename__ = "judge_evaluation"

    evaluation_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    calibration_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("judge_calibration.id", ondelete="CASCADE"), nullable=False
    )
    judge_cell_id: Mapped[str] = mapped_column(String(100), nullable=False)
    case_id: Mapped[str] = mapped_column(String(100), nullable=False)
    repeat_index: Mapped[int] = mapped_column(Integer, nullable=False)
    order_variant: Mapped[str] = mapped_column(String(30), nullable=False)
    slot_id: Mapped[str] = mapped_column(String(71), nullable=False, unique=True)
    slot_order: Mapped[int] = mapped_column(Integer, nullable=False)
    slot_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'queued'"))
    outcome: Mapped[str | None] = mapped_column(String(30))
    artifact_manifest_path: Mapped[str | None] = mapped_column(Text)
    artifact_digest: Mapped[str | None] = mapped_column(String(71))
    requested_judge_model: Mapped[str] = mapped_column(String(200), nullable=False)
    observed_judge_model: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "calibration_id",
            "judge_cell_id",
            "case_id",
            "repeat_index",
            "order_variant",
            name="uq_judge_logical_evaluation_slot",
        ),
    )
