"""Subscription preparation contracts. No credential reader or live transport exists here."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from harnesslab.registry.models import RegistryModel


class SubscriptionLimits(RegistryModel):
    billing_mode: Literal["CHATGPT_SUBSCRIPTION"] = "CHATGPT_SUBSCRIPTION"
    wall_time_seconds: int = Field(gt=0, le=300, strict=True)
    max_requests: int = Field(ge=1, le=10, strict=True)
    max_turns: Literal[1] = 1
    physical_attempts: Literal[1] = 1
    automatic_retries: Literal[0] = 0
    purchase_extra_credits: Literal[False] = False
    token_limit: Literal["OBSERVATION_ONLY_NOT_ENFORCEABLE"] = "OBSERVATION_ONLY_NOT_ENFORCEABLE"
    quota_limit: Literal["OBSERVED_AVAILABILITY_NOT_RESERVED_OR_HARD_CAPPED"] = (
        "OBSERVED_AVAILABILITY_NOT_RESERVED_OR_HARD_CAPPED"
    )


class SubscriptionPlanningBudget(SubscriptionLimits):
    output_tokens_estimate: int = Field(gt=0, le=1_000_000, strict=True)


class QuotaObservation(RegistryModel):
    """Sanitized observation, never a reservation or a promise of request capacity."""

    status: Literal["AVAILABLE", "EXHAUSTED", "UNKNOWN"]
    used_percent: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    resets_at: int | None = Field(default=None, ge=0, strict=True)
    observed_at: datetime
    source: Literal["PROTOCOL_STUB", "NOT_READ"]


def observe_stub_quota(payload: dict[str, Any], observed_at: datetime) -> QuotaObservation:
    """Parse an offline account/rateLimits/read response; no RPC is issued."""
    try:
        buckets = payload.get("rateLimitsByLimitId")
        bucket = buckets["codex"] if isinstance(buckets, dict) else payload["rateLimits"]
        if bucket.get("limitId") not in (None, "codex"):
            raise ValueError("wrong quota bucket")
        windows = [bucket.get("primary"), bucket.get("secondary")]
        used: list[float] = []
        resets: list[int] = []
        for window in windows:
            if window is None:
                continue
            percent = window["usedPercent"]
            reset = window["resetsAt"]
            if (
                isinstance(percent, bool)
                or not isinstance(percent, (float, int))
                or not 0 <= percent <= 100
                or isinstance(reset, bool)
                or not isinstance(reset, int)
                or reset <= int(observed_at.timestamp())
            ):
                raise ValueError("invalid or expired quota window")
            used.append(float(percent))
            resets.append(reset)
        if not used:
            raise ValueError("missing quota windows")
        exhausted = max(used) >= 100 or bucket.get("rateLimitReachedType") is not None
        return QuotaObservation(
            status="EXHAUSTED" if exhausted else "AVAILABLE",
            used_percent=max(used),
            resets_at=min(resets),
            observed_at=observed_at,
            source="PROTOCOL_STUB",
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return QuotaObservation(status="UNKNOWN", observed_at=observed_at, source="PROTOCOL_STUB")


def real_execution_readiness() -> dict[str, Any]:
    # Code gate, not a configurable enablement flag. Even offline success grants no live access.
    return {
        "real_execution_enabled": False,
        "billing_mode": "CHATGPT_SUBSCRIPTION",
        "api_key_required": False,
        "usd_hard_cap_required": False,
        "credential_access": "NONE_PHASE25",
        "quota": "NOT_READ",
        "token_usage": "NOT_REPORTED",
        "blockers": [
            "PHASE25_REAL_EXECUTION_CLOSED",
            "TRUSTED_SUBSCRIPTION_CREDENTIAL_BOUNDARY_NOT_LIVE_VERIFIED",
            "LIVE_ROUTE_AND_QUOTA_NOT_VERIFIED",
            "LIVE_REQUEST_INTERCEPTION_AND_NO_RETRY_NOT_VERIFIED",
            "SEPARATE_FIRST_REAL_AUTHORIZATION_REQUIRED",
        ],
    }


def deny_real_execution() -> None:
    from harnesslab.local_plans.tasks import fail

    raise fail(
        "REAL_EXECUTION_BLOCKED",
        "ChatGPT subscription execution remains closed in Phase 2.5; trusted credential "
        "isolation, live route/quota and request controls need independent verification "
        "and separate first-real authorization. No API key or USD hard cap is required.",
        403,
    )
