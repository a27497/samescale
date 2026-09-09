from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.analyst.real_backend import RealAnalystBackend, resolve_analyst_profile
from harnesslab.analyst.sessions import AnalystSessions, CreateInvestigation
from harnesslab.core.config import Settings
from harnesslab.db.models.experiment import ExperimentRecord
from harnesslab.db.session import create_engine
from harnesslab.experiment.plan import build_experiment_plan
from harnesslab.experiment.queue import enqueue_plan
from harnesslab.registry.service import registry_catalog
from tests.phase_g_helpers import ROOT, basic_spec


def test_official_responses_is_separate_and_matches_auditable_budget() -> None:
    catalog = registry_catalog(ROOT, {})
    profile = resolve_analyst_profile(catalog, "deepseek-official-v4flash-responses", ROOT)
    historical = next(
        p
        for p in catalog.provider_model_profiles
        if p.profile_id == "deepseek-official-v4flash-chat"
    )
    assert historical.route == "/chat/completions"
    assert historical.max_output_tokens == 2000
    assert historical.request_timeout_seconds == 180
    assert historical.pricing_snapshot_reference is None
    assert profile.runtime.route == "/responses"
    assert profile.context_window_tokens == 1_000_000
    assert profile.runtime.reasoning.max_output_tokens == 1200
    assert profile.runtime.request_timeout_seconds == 90
    assert profile.pricing is not None
    assert profile.pricing.input_usd_per_million_tokens == Decimal("0.44")
    assert profile.pricing.output_usd_per_million_tokens == Decimal("1.32")
    assert profile.pricing.request_usd == 0
    assert profile.pricing.evidence_reference
    assert (ROOT / profile.pricing.evidence_reference).is_file()
    model = next(m for m in catalog.models if m.model_id == "deepseek-v4-flash")
    assert "json_schema" in model.capabilities


def test_official_responses_smoke_v2_preserves_v1_and_adds_reasoning_headroom() -> None:
    catalog = registry_catalog(ROOT, {})
    v1 = resolve_analyst_profile(catalog, "deepseek-official-v4flash-responses", ROOT)
    v2 = resolve_analyst_profile(catalog, "deepseek-official-v4flash-responses-smoke-v2", ROOT)
    request = CreateInvestigation.model_validate_json(
        (ROOT / "profiles/analyst/core-real-matrix-v6-smoke-v2.json").read_bytes()
    )

    assert v1.runtime.reasoning.max_output_tokens == 1200
    assert v2.runtime.reasoning.max_output_tokens == 8192
    assert v2.profile_id != v1.profile_id and v2.profile_digest != v1.profile_digest
    assert v2.runtime.provider_route_identity == v1.runtime.provider_route_identity
    assert v2.pricing == v1.pricing
    assert request.provider_profile_id == v2.profile_id
    assert request.spend_limits is not None
    assert request.spend_limits.output_tokens_per_request == 8192
    assert request.spend_limits.cumulative_tokens == 1_150_000
    assert request.spend_limits.usd == Decimal("0.50")


def test_smoke_v3_only_expands_read_only_tool_headroom() -> None:
    v2 = CreateInvestigation.model_validate_json(
        (ROOT / "profiles/analyst/core-real-matrix-v6-smoke-v2.json").read_bytes()
    )
    v3 = CreateInvestigation.model_validate_json(
        (ROOT / "profiles/analyst/core-real-matrix-v6-smoke-v3.json").read_bytes()
    )
    assert v2.provider_profile_id == v3.provider_profile_id
    assert v2.decision_limit == v3.decision_limit == 3
    assert v2.tool_limit == 6 and v3.tool_limit == 8
    assert v2.spend_limits == v3.spend_limits


def test_smoke_v4_only_pins_low_reasoning_for_final_synthesis_headroom() -> None:
    catalog = registry_catalog(ROOT, {})
    v2 = resolve_analyst_profile(catalog, "deepseek-official-v4flash-responses-smoke-v2", ROOT)
    v4 = resolve_analyst_profile(catalog, "deepseek-official-v4flash-responses-smoke-v4", ROOT)
    request = CreateInvestigation.model_validate_json(
        (ROOT / "profiles/analyst/core-real-matrix-v6-smoke-v4.json").read_bytes()
    )

    assert v2.runtime.reasoning.effort is None
    assert v4.runtime.reasoning.effort == "low"
    assert v4.runtime.reasoning.max_output_tokens == v2.runtime.reasoning.max_output_tokens == 8192
    assert v4.runtime.provider_route_identity == v2.runtime.provider_route_identity
    assert v4.pricing == v2.pricing
    assert request.provider_profile_id == v4.profile_id
    assert request.decision_limit == 3 and request.tool_limit == 8
    assert request.spend_limits is not None
    assert request.spend_limits.output_tokens_per_request == 8192
    assert request.spend_limits.cumulative_tokens == 1_150_000
    assert request.spend_limits.usd == Decimal("0.50")


def test_smoke_v5_adds_final_synthesis_headroom_without_changing_provider_controls() -> None:
    v4 = CreateInvestigation.model_validate_json(
        (ROOT / "profiles/analyst/core-real-matrix-v6-smoke-v4.json").read_bytes()
    )
    v5 = CreateInvestigation.model_validate_json(
        (ROOT / "profiles/analyst/core-real-matrix-v6-smoke-v5.json").read_bytes()
    )
    assert v4.provider_profile_id == v5.provider_profile_id
    assert v4.decision_limit == 3 and v5.decision_limit == 4
    assert v4.tool_limit == 8 and v5.tool_limit == 12
    assert v4.spend_limits is not None and v5.spend_limits is not None
    assert v5.spend_limits.provider_requests == 4
    assert v5.spend_limits.output_tokens_per_request == v4.spend_limits.output_tokens_per_request
    assert v5.spend_limits.input_bytes_per_request == v4.spend_limits.input_bytes_per_request
    assert v5.spend_limits.timeout_seconds == v4.spend_limits.timeout_seconds
    assert v5.spend_limits.cumulative_tokens == 1_250_000
    assert v5.spend_limits.usd == Decimal("0.60")


def test_smoke_v6_only_expands_output_headroom_after_live_final_truncation() -> None:
    catalog = registry_catalog(ROOT, {})
    v4_profile = resolve_analyst_profile(
        catalog, "deepseek-official-v4flash-responses-smoke-v4", ROOT
    )
    v6_profile = resolve_analyst_profile(
        catalog, "deepseek-official-v4flash-responses-smoke-v6", ROOT
    )
    v5 = CreateInvestigation.model_validate_json(
        (ROOT / "profiles/analyst/core-real-matrix-v6-smoke-v5.json").read_bytes()
    )
    v6 = CreateInvestigation.model_validate_json(
        (ROOT / "profiles/analyst/core-real-matrix-v6-smoke-v6.json").read_bytes()
    )

    assert v4_profile.runtime.reasoning.effort == v6_profile.runtime.reasoning.effort == "low"
    assert v4_profile.runtime.reasoning.max_output_tokens == 8192
    assert v6_profile.runtime.reasoning.max_output_tokens == 32768
    assert v4_profile.runtime.provider_route_identity == v6_profile.runtime.provider_route_identity
    assert v4_profile.pricing == v6_profile.pricing
    assert v5.decision_limit == v6.decision_limit == 4
    assert v5.tool_limit == v6.tool_limit == 12
    assert v5.spend_limits is not None and v6.spend_limits is not None
    assert v6.spend_limits.output_tokens_per_request == 32768
    assert v6.spend_limits.input_bytes_per_request == v5.spend_limits.input_bytes_per_request
    assert v6.spend_limits.cumulative_tokens == v5.spend_limits.cumulative_tokens == 1_250_000
    assert v6.spend_limits.usd == v5.spend_limits.usd == Decimal("0.60")


@pytest.mark.integration
async def test_official_keyless_preflight_is_budget_ready_without_any_invocation(
    database_url: str,
    tmp_path: Path,
) -> None:
    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    experiment_id = "official-keyless-" + uuid4().hex[:12]
    spec = basic_spec(repeat_count=1).model_copy(update={"experiment_id": experiment_id})
    try:
        async with AsyncSession(engine) as db, db.begin():
            await enqueue_plan(db, build_experiment_plan(spec, ROOT))
        api = AnalystSessions(
            engine,
            repository_root=ROOT,
            artifact_roots=(tmp_path,),
            environment={},
        )
        request = json.loads((ROOT / "profiles/analyst/core-real-matrix-v6-smoke.json").read_text())
        request["experiment_id"] = experiment_id
        with patch.object(
            RealAnalystBackend, "decide", side_effect=AssertionError("NO INVOCATION")
        ):
            session = await api.create(CreateInvestigation.model_validate(request))
            result = await api.preflight(session.session_id)
            persisted = await api.get(session.session_id)
        assert result["status"] == "BLOCKED"
        assert result["reasons"] == ["CREDENTIAL_REFERENCE_MISSING"]
        assert result["credential_reference_status"] == "MISSING"
        assert result["base_url_reference_status"] == "SET"
        assert result["input_token_upper_bound"] == 1_000_000
        assert result["next_input_bytes"] <= 256000
        assert not result["server_real_enabled"]
        assert not result["execution_authorized"]
        assert result["request_budget_used"] == 0
        assert persisted.usage == () and persisted.state.tool_calls == 0
        assert await api.preflight(session.session_id) == result
    finally:
        async with AsyncSession(engine) as db, db.begin():
            await db.execute(delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id))
        await engine.dispose()
