"""Deterministic, keyless failure diagnosis over immutable experiment evidence."""

from harnesslab.diagnosis.models import (
    AttributionKind,
    BadCaseExport,
    BadCaseExportRequest,
    DiagnosisReport,
    EvidenceOrigin,
    FailureClass,
    FailureScope,
)
from harnesslab.diagnosis.projection_models import (
    ClusterProjection,
    ClusterProjectionRequest,
    ProjectedClusterReadRequest,
    ProjectedClusterReport,
    RawFailureFact,
)
from harnesslab.diagnosis.projection_service import (
    build_cluster_projection,
    build_failure_cohort,
    build_projected_cluster_report,
    read_projected_failure_clusters,
)
from harnesslab.diagnosis.service import build_badcase_export, build_diagnosis_report

__all__ = [
    "AttributionKind",
    "BadCaseExport",
    "BadCaseExportRequest",
    "ClusterProjection",
    "ClusterProjectionRequest",
    "DiagnosisReport",
    "EvidenceOrigin",
    "FailureClass",
    "FailureScope",
    "ProjectedClusterReadRequest",
    "ProjectedClusterReport",
    "RawFailureFact",
    "build_badcase_export",
    "build_cluster_projection",
    "build_diagnosis_report",
    "build_failure_cohort",
    "build_projected_cluster_report",
    "read_projected_failure_clusters",
]
