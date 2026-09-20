from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from harnesslab.db.base import Base
from harnesslab.db.models.experiment import JSON_DOCUMENT


class LocalCredentialRecord(Base):
    __tablename__ = "local_credential"
    credential_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    storage_reference: Mapped[str] = mapped_column(String(32), nullable=False)


class LocalConnectionRecord(Base):
    __tablename__ = "local_connection"
    connection_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    endpoint_storage_reference: Mapped[str] = mapped_column(String(32), nullable=False)
    configuration_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)


class LocalModelConfigurationRecord(Base):
    """Append-only revisions of user configuration, separate from built-in definitions."""

    __tablename__ = "local_model_configuration"

    configuration_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    configuration_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


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


class LocalHarnessConfigurationRecord(Base):
    __tablename__ = "local_harness_configuration"
    configuration_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    configuration_json: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
