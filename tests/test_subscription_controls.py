from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.local_execution.models import AuthorizationRequest
from harnesslab.local_execution.subscription import (
    SubscriptionLimits,
    deny_real_execution,
    observe_stub_quota,
    real_execution_readiness,
)
from harnesslab.local_execution.subscription_protocol import OfflineSubscriptionController
from harnesslab.local_plans.models import PlanningBudget, PlanRequest
from harnesslab.local_plans.service import assess
from harnesslab.registry.models import RegistryCatalog
from tests.test_local_execution import execution_policy as execution_policy
from tests.test_local_plans import configured as configured


def limits(**changes: object) -> SubscriptionLimits:
    return SubscriptionLimits.model_validate(
        {"wall_time_seconds": 20, "max_requests": 2, **changes}
    )


def controller(tmp_path: Path, **changes: object) -> OfflineSubscriptionController:
    return OfflineSubscriptionController(
        {
            "run_id": "offline-run",
            "authorization_digest": "sha256:" + "1" * 64,
            "model": "frozen-test-model",
            "max_requests": 2,
            "wall_time_seconds": 20,
            "scenario": "solve",
            **changes,
        },
        tmp_path / "journal.json",
    )


def request() -> dict[str, Any]:
    return {
        "model": "frozen-test-model",
        "stream": True,
        "tools": [{"type": "custom", "name": "apply_patch"}],
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"max_requests": 0},
        {"max_requests": True},
        {"max_requests": 11},
        {"max_turns": 2},
        {"physical_attempts": 2},
        {"automatic_retries": 1},
        {"purchase_extra_credits": True},
        {"wall_time_seconds": 0},
        {"wall_time_seconds": 301},
        {"token_limit": "HARD_LIMIT"},
        {"api_key": "development-placeholder"},
    ],
)
def test_subscription_controls_reject_unenforceable_or_unbounded_claims(
    changes: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        limits(**changes)


def test_subscription_authorization_needs_no_api_key_or_dollar_budget() -> None:
    budget = {**limits().model_dump(), "output_tokens_estimate": 2000}
    request_model = AuthorizationRequest.model_validate(
        {
            "mode": "REAL_CODEX",
            "plan_digest": "sha256:" + "1" * 64,
            "run_slot_digest": "sha256:" + "2" * 64,
            "idempotency_key": str(uuid4()),
            "confirmed_budget": budget,
            "subscription_limits": limits().model_dump(),
            "confirm_one_attempt": True,
            "acknowledge_reference_budgets": True,
        }
    )
    assert request_model.max_model_cost_usd is None
    with pytest.raises(WorkbenchAPIError, match="ChatGPT subscription"):
        deny_real_execution()
    assert real_execution_readiness()["real_execution_enabled"] is False
    assert real_execution_readiness()["api_key_required"] is False
    assert real_execution_readiness()["usd_hard_cap_required"] is False


def test_subscription_planning_blocks_before_credentials_or_processes() -> None:
    plan = PlanRequest.model_validate(
        {
            "name": "Subscription preparation",
            "task_reference": "core-python-deduplicate@1.0.2",
            "provider_profile_id": "subscription-pending",
            "harness_profile_id": "codex-pending",
            "budget": {**limits().model_dump(), "output_tokens_estimate": 2000},
        }
    )
    with patch(
        "harnesslab.local_plans.service.load_policy",
        side_effect=AssertionError("No credentials/process"),
    ):
        material, checks = assess(
            plan,
            cast(RegistryCatalog, None),
            frozenset(),
        )
    assert material is None and checks[0].code == "SUBSCRIPTION_RUNTIME_NOT_ADMITTED"
    # Existing serialization and frozen budget identities do not gain default billing fields.
    assert PlanningBudget(
        wall_time_seconds=20, output_tokens_estimate=2000, cost_budget_usd=1
    ).model_dump() == {
        "wall_time_seconds": 20,
        "output_tokens_estimate": 2000,
        "cost_budget_usd": 1.0,
    }


def test_request_debit_is_durable_no_reopen_no_credential_reflection(tmp_path: Path) -> None:
    c = controller(tmp_path)
    private = c._private_credential  # A newly generated offline canary, never a login credential.
    assert c.response(request())[0] == 200
    assert json.loads(c.journal.read_text())["requests_consumed"] == 1
    assert c.response(request())[0] == 200
    assert c.response(request())[0] == 403
    assert c.state["requests_consumed"] == 2 and c.state["turns_consumed"] == 1
    assert private not in c.journal.read_text()
    assert private not in json.dumps(c.response(request()))
    assert c.state["real_model_requests"] == 0 and c.state["token_usage"] is None
    with pytest.raises(FileExistsError):
        controller(tmp_path)


@pytest.mark.parametrize("scenario", ["auth_expired", "quota_exhausted", "upstream_failure"])
def test_auth_quota_failure_cannot_retry_refund_or_buy(tmp_path: Path, scenario: str) -> None:
    c = controller(tmp_path, scenario=scenario)
    assert c.response(request())[0] == 403
    spent = c.state["requests_consumed"]
    assert spent == (1 if scenario == "upstream_failure" else 0)
    assert c.response(request())[0] == 403 and c.state["requests_consumed"] == spent
    assert c.state["automatic_retries"] == c.state["real_model_requests"] == 0


def test_request_cap_rejects_before_second_transport(tmp_path: Path) -> None:
    c = controller(tmp_path, max_requests=1)
    assert c.response(request())[0] == 200
    assert c.response(request()) == (403, {"error": "REQUEST_LIMIT"})
    assert c.state["requests_consumed"] == 1


def test_deadline_and_route_deny_before_transport(tmp_path: Path) -> None:
    c = controller(tmp_path)
    c.deadline = 0
    assert c.response(request())[1] == {"error": "TIMEOUT"}
    assert c.state["requests_consumed"] == 0


@pytest.mark.parametrize(
    "percent,status",
    [
        (25, "AVAILABLE"),
        (100, "EXHAUSTED"),
        (None, "UNKNOWN"),
        (True, "UNKNOWN"),
        (float("nan"), "UNKNOWN"),
    ],
)
def test_quota_observations_remain_observations(percent: object, status: str) -> None:
    now = datetime.now(UTC)
    observation = observe_stub_quota(
        {
            "rateLimits": {
                "limitId": "codex",
                "primary": {"usedPercent": percent, "resetsAt": int(now.timestamp()) + 100},
            }
        },
        now,
    )
    assert observation.status == status and observation.source == "PROTOCOL_STUB"


def test_multi_bucket_secondary_and_unknown_quota_fail_closed() -> None:
    now = datetime.now(UTC)
    window = {"usedPercent": 100, "resetsAt": int(now.timestamp()) + 50}
    observed = observe_stub_quota(
        {
            "rateLimitsByLimitId": {
                "codex": {
                    "primary": {**window, "usedPercent": 10},
                    "secondary": window,
                    "credits": {"hasCredits": True},
                }
            }
        },
        now,
    )
    assert observed.status == "EXHAUSTED"  # Never silently spend extra credits.
    assert observe_stub_quota({}, now).status == "UNKNOWN"
    window["resetsAt"] = 0
    assert observe_stub_quota({"rateLimits": {"primary": window}}, now).status == "UNKNOWN"


@pytest.mark.integration
async def test_real_subscription_http_deny_and_readiness_without_api_or_usd(
    database_url: str,
    execution_policy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_local_model_configuration import local_client
    from tests.test_registry_lite import isolated_registry_database

    monkeypatch.setenv("HARNESSLAB_REAL_CODEX_ENABLED", "true")
    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        status = (await client.get("/api/local-execution/status")).json()
        assert status["real_execution_enabled"] is False
        assert status["subscription_readiness"]["api_key_required"] is False
        body = {
            "mode": "REAL_CODEX",
            "plan_digest": "sha256:" + "1" * 64,
            "run_slot_digest": "sha256:" + "2" * 64,
            "idempotency_key": str(uuid4()),
            "confirmed_budget": {**limits().model_dump(), "output_tokens_estimate": 2000},
            "subscription_limits": limits().model_dump(),
            "confirm_one_attempt": True,
            "acknowledge_reference_budgets": True,
        }
        r = await client.post("/api/local-execution/plans/uncreated/authorize", json=body)
        assert r.status_code == 403 and r.json()["error"]["code"] == "REAL_EXECUTION_BLOCKED"


def test_legacy_authorization_document_and_digest_remain_readable() -> None:
    from harnesslab.local_execution.models import ExecutionAuthorization
    from harnesslab.registry.models import canonical_digest

    legacy_request = {
        "plan_digest": "sha256:" + "1" * 64,
        "run_slot_digest": "sha256:" + "2" * 64,
        "idempotency_key": str(uuid4()),
        "mode": "FAKE_CODEX",
        "confirmed_budget": {
            "wall_time_seconds": 20,
            "output_tokens_estimate": 1000,
            "cost_budget_usd": 1.0,
        },
        "max_model_cost_usd": 0.0,
        "confirm_one_attempt": True,
        "acknowledge_reference_budgets": True,
    }
    payload = {
        "authorization_id": "legacy-authorization",
        "plan_id": "legacy-plan",
        "plan_digest": legacy_request["plan_digest"],
        "run_slot_digest": legacy_request["run_slot_digest"],
        "request": legacy_request,
        "operator_identity": "sha256:" + "3" * 64,
        "execution_policy_identity": "sha256:" + "4" * 64,
        "created_at": "2026-10-09T00:00:00Z",
        "expires_at": "2026-10-09T00:05:00Z",
        "model_calls_allowed": 0,
        "cost_enforcement": "ZERO_MODEL_CALLS_NETWORK_NONE_NO_CREDENTIALS",
        "token_enforcement": "REFERENCE_ONLY_NOT_A_HARD_LIMIT",
    }
    document = {**payload, "digest": canonical_digest(payload)}
    auth = ExecutionAuthorization.model_validate(document)
    assert auth.model_dump(mode="json") == document
    assert auth.request.subscription_limits is None
