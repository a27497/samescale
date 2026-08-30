from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"


def _load(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((RELEASE / name).read_text()))


def _sha256(name: str) -> str:
    return "sha256:" + hashlib.sha256((ROOT / name).read_bytes()).hexdigest()


def _all_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _all_strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _all_strings(child)]
    return []


def test_kb2f_preserves_the_exact_v5_scientific_design_and_r2_evidence() -> None:
    dossier = _load("kb2f-full-matrix-authorization-dossier.json")
    expected = dossier["immutable_scientific_evidence"]

    assert {name: _sha256(name) for name in expected} == expected
    assert dossier["frozen_inputs"]["pricing_snapshot_sha256"] == _sha256(
        "release/core-real-matrix-v5-pricing-snapshot.json"
    )
    assert dossier["frozen_inputs"]["operator_input_template_sha256"] == _sha256(
        "release/operator-pricing-input-template.json"
    )
    assert dossier["frozen_inputs"]["operator_input_closure_sha256"] == _sha256(
        "release/kb2f-operator-input-closure.json"
    )
    plan = _load("core-real-evidence-plan-v5.json")
    assert [cell["cell_id"] for cell in plan["cells"]] == [
        "model-gpt56-relay-responses",
        "model-qwen38-opencode-go-messages",
        "model-deepseek-v4pro-chat",
        "harness-codex-gpt56-medium",
        "harness-codex-gpt56-high",
        "harness-claude-qwen38-opencode-go",
        "model-deepseek-v4flash-chat",
    ]
    assert plan["preflight"]["total_subject_runs"] == 630
    assert plan["judge"]["planned_calls"] == 63


def test_current_deepseek_rates_and_scenarios_are_exact() -> None:
    snapshot = _load("core-real-matrix-v5-pricing-snapshot.json")
    deepseek = snapshot["deepseek_official"]

    assert deepseek["pricing_status"] == "OFFICIAL_CURRENT_PRICING_FROZEN"
    assert deepseek["effective_from"] == "2026-08-16T16:00:00Z"
    assert deepseek["peak_schedule"]["intervals"] == ["01:00-04:00", "06:00-10:00"]
    rates = {item["requested_model"]: item for item in deepseek["models"]}
    assert rates["deepseek-v4-pro"]["resolved_version"] == "DeepSeek-V4-Pro-0813"
    assert rates["deepseek-v4-flash"]["resolved_version"] == "DeepSeek-V4-Flash-0731"
    assert rates["deepseek-v4-pro"]["peak"] == {
        "cache_hit_input": "0.044",
        "cache_miss_input": "1.32",
        "output": "3.96",
    }
    assert rates["deepseek-v4-flash"]["off_peak"] == {
        "cache_hit_input": "0.007",
        "cache_miss_input": "0.22",
        "output": "0.66",
    }
    assert all(
        source["url"].startswith("https://api-docs.deepseek.com/")
        and source["response_body_sha256"].startswith("sha256:")
        for source in deepseek["sources"]
    )

    million = Decimal(1_000_000)
    off_peak = (
        Decimal(90)
        * (
            Decimal(379) * Decimal("0.66")
            + Decimal(222) * Decimal("1.98")
            + Decimal(458) * Decimal("0.22")
            + Decimal(2000) * Decimal("0.66")
        )
        / million
    )
    peak = (
        Decimal(90)
        * (
            Decimal(379) * Decimal("1.32")
            + Decimal(222) * Decimal("3.96")
            + Decimal(458) * Decimal("0.44")
            + Decimal(2000) * Decimal("1.32")
        )
        / million
    )
    assert Decimal(snapshot["empirical_projection"]["deepseek_off_peak_estimate"]) == off_peak
    assert Decimal(snapshot["empirical_projection"]["deepseek_peak_estimate"]) == peak


def test_subscription_accounting_is_confirmed_and_quota_guarded() -> None:
    snapshot = _load("core-real-matrix-v5-pricing-snapshot.json")
    opencode = snapshot["opencode_go_public_contract"]
    closure = _load("kb2f-operator-input-closure.json")["opencode_go"]

    assert opencode["operator_account_status"] == "ACTIVE_GO_SUBSCRIPTION_CONFIRMED"
    assert opencode["accounting_model"] == "SUBSCRIPTION_INCLUDED_QUOTA"
    assert opencode["monthly_subscription_fee"] == "10.00"
    assert opencode["general_usage_value_limits"] == {
        "five_hour": "12.00",
        "weekly": "30.00",
        "monthly": "60.00",
    }
    models = {item["requested_model"]: item for item in opencode["models"]}
    assert models["qwen3.8-max"]["official_estimated_requests"] == {
        "five_hour": 160,
        "weekly": 400,
        "monthly": 810,
    }
    assert models["glm-5.2"]["official_estimated_requests"] == {
        "five_hour": 880,
        "weekly": 2150,
        "monthly": 4300,
    }
    assert opencode["overage_semantics"]["operator_zen_balance"] == "0.00"
    assert opencode["overage_semantics"]["operator_paid_overage_capacity"] == "NONE_CONFIRMED"
    assert opencode["overage_semantics"]["quota_exhaustion_policy"] == (
        "FAIL_CLOSED_NO_PROVIDER_SUBSTITUTION"
    )
    assert snapshot["accounting_semantics"]["included_quota_treated_as_free"] is False
    assert (
        snapshot["accounting_semantics"][
            "economic_allocated_cost_is_separate_from_marginal_cash_spend"
        ]
        is True
    )
    assert all(
        source["url"].startswith("https://opencode.ai/docs/")
        and source["response_body_sha256"].startswith("sha256:")
        for source in opencode["sources"]
    )

    dashboard = closure["dashboard_snapshot"]
    assert dashboard["reset_observations_are_durable_facts"] is False
    dashboard_models = {item["requested_model"]: item for item in dashboard["models"]}
    qwen = dashboard_models["qwen3.8-max"]
    glm = dashboard_models["glm-5.2"]
    for model in (qwen, glm):
        assert model["projection_fits_current_snapshot"] is True
        for window in model["windows"].values():
            usage = Decimal(window["usage"])
            quota = Decimal(window["quota"])
            remaining = Decimal(window["remaining"])
            projected = Decimal(window["projected_remaining_after_matrix"])
            assert quota - usage == remaining
            assert projected >= 0
    assert Decimal(qwen["windows"]["five_hour"]["projected_remaining_after_matrix"]) == (
        Decimal("3.00") - Decimal("0.0372") - Decimal("1.870380000")
    )
    assert Decimal(glm["windows"]["monthly"]["projected_remaining_after_matrix"]) == (
        Decimal("60.00") - Decimal("0.0017") - Decimal("0.049870800")
    )


def test_operator_export_costs_reconcile_and_remain_planning_projections() -> None:
    snapshot = _load("core-real-matrix-v5-pricing-snapshot.json")
    dossier = _load("kb2f-full-matrix-authorization-dossier.json")
    closure = _load("kb2f-operator-input-closure.json")
    relay = closure["gpt_relay"]

    assert snapshot["gpt_relay"]["pricing_status"] == ("OPERATOR_USAGE_DERIVED_PRICING_FROZEN")
    assert snapshot["gpt_relay"]["public_openai_pricing_substituted"] is False
    assert relay["operator_provided_csv_sha256"] == (
        "sha256:eb4831effff557177acb84931a562efa31c61e66f1edb490846e9027b2e2bb8b"
    )
    assert relay["raw_csv_stored"] is False
    assert relay["maximum_observed_multiplier_is_contractual_permanent_maximum"] is False

    rates = relay["base_rates_per_million_tokens"]
    million = Decimal(1_000_000)
    for row in relay["canary_rows"]:
        original = (
            Decimal(row["uncached_input_tokens"]) * Decimal(rates["uncached_input"])
            + Decimal(row["cache_read_tokens"]) * Decimal(rates["cache_read_input"])
            + Decimal(row["output_tokens"]) * Decimal(rates["output"])
        ) / million
        assert original == Decimal(row["original_cost"])
        assert (
            row["uncached_input_tokens"] + row["cache_read_tokens"] == row["aggregate_input_tokens"]
        )

    empirical = (
        sum(
            (Decimal(row["actual_billed_cost"]) for row in relay["canary_rows"]),
            start=Decimal(0),
        )
        * 90
    )
    original = sum(
        (Decimal(row["original_cost"]) for row in relay["canary_rows"]),
        start=Decimal(0),
    )
    observed_max = original * Decimal("0.06") * 90
    assert empirical == Decimal("2.07326340")
    assert observed_max == Decimal("3.02259060")
    assert Decimal(relay["matrix_projection"]["empirical_270_run_cost"]) == empirical
    assert Decimal(relay["matrix_projection"]["observed_max_multiplier_projection"]) == (
        observed_max
    )

    combined = closure["combined_projection"]
    assert Decimal(combined["expected_total_marginal_cash_low"]) == (
        empirical + Decimal("0.18994140")
    )
    assert Decimal(combined["expected_total_marginal_cash_high"]) == (
        empirical + Decimal("0.37988280")
    )
    assert Decimal(combined["planning_conservative_total"]) == (
        observed_max + Decimal("1.01356200")
    )
    assert combined["planning_conservative_total_is_hard_monetary_ceiling"] is False
    assert snapshot["hard_resource_ceiling"]["aggregate_input_token_ceiling"] is None
    assert dossier["authorization_result"] == "READY_FOR_OPERATOR_SPEND_APPROVAL"
    assert dossier["operator_pricing_inputs_remaining"] == []
    assert dossier["cost_estimate"]["spend_authorization_status"] == (
        "AWAITING_EXPLICIT_OPERATOR_APPROVAL"
    )
    assert dossier["cost_estimate"]["soft_spend_warning_usd"] == "5.00"
    assert dossier["cost_estimate"]["proposed_hard_operator_spend_ceiling_usd"] == "10.00"
    assert [item["scenario_id"] for item in snapshot["cost_scenarios"]] == [
        "OFF_PEAK_ESTIMATE",
        "PEAK_ESTIMATE",
        "WORST_CASE_AUTHORIZATION_ESTIMATE",
    ]
    assert snapshot["cost_scenarios"][2]["complete_cost_bound_available"] is False
    assert dossier["cost_estimate"]["subscription_cost_dimensions"] == {
        "ECONOMIC_ALLOCATED_COST": "EXISTING_10_USD_MONTHLY_SUBSCRIPTION_NOT_ALLOCATED_TO_MATRIX",
        "MARGINAL_CASH_SPEND": "0.000000000_CURRENT_QUOTA_SNAPSHOT",
    }
    assert {item["reason_code"] for item in dossier["spend_authorization_prerequisites"]} == {
        "EXPLICIT_OPERATOR_SPEND_APPROVAL_REQUIRED",
        "OPENCODE_QUOTA_SNAPSHOT_REFRESH_REQUIRED_AT_LAUNCH",
    }


def test_operator_template_is_null_only_for_unknown_values_and_secret_safe() -> None:
    template = _load("operator-pricing-input-template.json")
    closure = _load("kb2f-operator-input-closure.json")
    relay = template["gpt_relay_rate_card"]
    account = template["opencode_go_account_confirmation"]

    assert relay["status"] == "GPT_RELAY_RATE_CARD_REQUIRED"
    assert relay["input_usd_per_million_tokens"] is None
    assert relay["cached_input_usd_per_million_tokens"] is None
    assert relay["output_usd_per_million_tokens"] is None
    assert relay["safe_binding"]["private_endpoint_value_required"] is False
    assert relay["safe_binding"]["credential_value_required"] is False
    assert account["status"] == "OPENCODE_ACCOUNT_PLAN_CONFIRMATION_REQUIRED"
    assert account["credential_value_required"] is False
    assert account["subscription_product"] is None
    assert account["use_balance_enabled"] is None

    strings = _all_strings(template)
    assert not any(value.startswith(("/home/", "/Users/")) for value in strings)
    assert not any("api_key=" in value.lower() or "bearer " in value.lower() for value in strings)
    assert not any("http://" in value or "https://" in value for value in strings)

    closure_strings = _all_strings(closure)
    assert not any(value.startswith(("/home/", "/Users/")) for value in closure_strings)
    assert not any(
        "api_key=" in value.lower() or "bearer " in value.lower() for value in closure_strings
    )
    assert not any("http://" in value or "https://" in value for value in closure_strings)


def test_kb2f_performed_no_evaluation_calls_and_did_not_start_kb3() -> None:
    dossier = _load("kb2f-full-matrix-authorization-dossier.json")
    closure = _load("kb2f-operator-input-closure.json")
    matrix = dossier["matrix_state"]

    assert matrix["scientific_design_changed"] is False
    assert matrix["cells_changed"] is False
    assert matrix["canary_rerun"] is False
    assert matrix["subject_provider_calls"] == 0
    assert matrix["harness_calls"] == 0
    assert matrix["judge_calls"] == 0
    assert matrix["full_matrix_executed"] is False
    assert matrix["k_b3_started"] is False
    assert closure["execution_state"] == {
        "provider_calls": 0,
        "harness_calls": 0,
        "judge_calls": 0,
        "full_matrix_executed": False,
        "k_b3_started": False,
        "main_promoted_by_this_continuation": False,
    }
    assert dossier["implementation_scope"] == {
        "release_and_test_artifacts_only": True,
        "phase_m_production_code_changed": False,
        "full_release_required": False,
    }
