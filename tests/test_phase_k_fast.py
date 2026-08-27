from __future__ import annotations

# ruff: noqa: E501 -- immutable historical evidence bytes are kept as base64 fixtures.
import base64
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from harnesslab.egress import EGRESS_PROXY_IMAGE
from harnesslab.harness_lane.profile import CODEX_IMAGE
from harnesslab.multi_harness.profile import CLAUDE_IMAGE, DEEPSEEK_IMAGE
from harnesslab.release.diagnostic import execute_component_diagnostics
from harnesslab.release.evidence import summarize_smoke_evidence, verify_history_against_summary
from harnesslab.release.matrix import (
    MatrixControlPlane,
    MatrixControlPlaneError,
    execute_real_matrix,
)
from harnesslab.release.models import EvidenceBinding, EvidenceState
from harnesslab.release.smoke import (
    EXPECTED_CALL_IDS,
    RuntimeIdentities,
    SmokeCallFailure,
    SmokeCallResult,
    SmokeControlPlane,
    SmokeExecutionReceipt,
    SmokeExecutionStatus,
    SmokeFailureCategory,
)
from harnesslab.release.telemetry import summarize_smoke_telemetry
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.tasks.package import digest_tree

ROOT = Path(__file__).resolve().parents[1]
CALL_1 = EXPECTED_CALL_IDS[0]
SMOKE_DIGEST = "sha256:8e0b6482dac4ccb0312d881eff3ab68f741d2b22b085557b1f9315e99fd1a18a"
RELEASE_DIGEST = "sha256:9ed4e586a663b5f1aba161718bbca584a6dc306bcb895fe1bc05d7b94aa3b4eb"

RECEIPTS = {
    10: "eyJhdHRlbXB0ZWRfdG9wX2xldmVsX2xhdW5jaGVzIjoxLCJmYWlsaW5nX2NhbF9pZCI6InNtb2tlLTEtbW9kZWwtZ3B0NTYtcmVsYXktcmVzcG9uc2VzIiwiZmFpbHVyZV9jYXRlZ29yeSI6IlBST1ZJREVSX0ZBSUxVUkUiLCJwbGFuX2lkIjoiY29yZS1yZWFsLXNtb2tlLXYyIiwicmVsZWFzZV9wbGFuX2RpZ2VzdCI6InNoYTI1Njo5ZWQ0ZTU4NmE2NjNiNWYxYWJhMTYxNzE4YmJjYTU4NGE2ZGMzMDZiY2I4OTVmZTFiYzA1ZDdiOTRhYTNiNGViIiwicmVzdWx0cyI6W3siY2FsbF9pZCI6InNtb2tlLTEtbW9kZWwtZ3B0NTYtcmVsYXktcmVzcG9uc2VzIiwiZXZpZGVuY2VfZGlnZXN0cyI6WyJzaGEyNTY6OTdhOWFhNzIxYTJjMGQxNmViODBjZjhhMDNiZTA1ZWE5NDRiODZkMThhM2M0OGJlNTg4NzZmN2I3OWRjNjA1NyJdLCJldmlkZW5jZV9yZWZlcmVuY2VzIjpbIi9ob21lL2Rldi9oYXJuZXNzbGFiLW9wZXJhdG9yLWV2aWRlbmNlL2NvcmUtcmVhbC1zbW9rZS12Mi1hdHRlbXB0LTEwLWZhZjNiNTA2L3Ntb2tlLTEtbW9kZWwtZ3B0NTYtcmVsYXktcmVzcG9uc2VzL3Ntb2tlLTEtbW9kZWwtZ3B0NTYtcmVsYXktcmVzcG9uc2VzIl19XSwic2NoZW1hX3ZlcnNpb24iOjEsInNtb2tlX3BsYW5fZGlnZXN0Ijoic2hhMjU2OjhlMGI2NDgyZGFjNGNjYjAzMTJkODgxZWZmM2FiNjhmNzQxZDJiMjJiMDg1NTU3YjFmOTMxNWU5OWZkMWExOGEiLCJzdGF0dXMiOiJBQk9SVEVEIn0K",
    11: "eyJhdHRlbXB0ZWRfdG9wX2xldmVsX2xhdW5jaGVzIjoxLCJmYWlsaW5nX2NhbF9pZCI6InNtb2tlLTEtbW9kZWwtZ3B0NTYtcmVsYXktcmVzcG9uc2VzIiwiZmFpbHVyZV9jYXRlZ29yeSI6IlBST1ZJREVSX0ZBSUxVUkUiLCJwbGFuX2lkIjoiY29yZS1yZWFsLXNtb2tlLXYyIiwicmVsZWFzZV9wbGFuX2RpZ2VzdCI6InNoYTI1Njo5ZWQ0ZTU4NmE2NjNiNWYxYWJhMTYxNzE4YmJjYTU4NGE2ZGMzMDZiY2I4OTVmZTFiYzA1ZDdiOTRhYTNiNGViIiwicmVzdWx0cyI6W3siY2FsbF9pZCI6InNtb2tlLTEtbW9kZWwtZ3B0NTYtcmVsYXktcmVzcG9uc2VzIiwiZXZpZGVuY2VfZGlnZXN0cyI6WyJzaGEyNTY6NWVhODI0ZmJjYWUyNGVlM2I0YWQ2Y2NlZGQzYzVmNTExNjdjNzYyOGRjNzI3ODUwOWVmNmFlY2Y0NGE4ODI1OSJdLCJldmlkZW5jZV9yZWZlcmVuY2VzIjpbIi9ob21lL2Rldi9oYXJuZXNzbGFiLW9wZXJhdG9yLWV2aWRlbmNlL2NvcmUtcmVhbC1zbW9rZS12Mi1hdHRlbXB0LTExLWE4ODAwYzFjL3Ntb2tlLTEtbW9kZWwtZ3B0NTYtcmVsYXktcmVzcG9uc2VzL3Ntb2tlLTEtbW9kZWwtZ3B0NTYtcmVsYXktcmVzcG9uc2VzIl19XSwic2NoZW1hX3ZlcnNpb24iOjEsInNtb2tlX3BsYW5fZGlnZXN0Ijoic2hhMjU2OjhlMGI2NDgyZGFjNGNjYjAzMTJkODgxZWZmM2FiNjhmNzQxZDJiMjJiMDg1NTU3YjFmOTMxNWU5OWZkMWExOGEiLCJzdGF0dXMiOiJBQk9SVEVEIn0K",
    12: "eyJhdHRlbXB0ZWRfdG9wX2xldmVsX2xhdW5jaGVzIjoxLCJmYWlsaW5nX2NhbF9pZCI6InNtb2tlLTEtbW9kZWwtZ3B0NTYtcmVsYXktcmVzcG9uc2VzIiwiZmFpbHVyZV9jYXRlZ29yeSI6IlBST1ZJREVSX0ZBSUxVUkUiLCJwbGFuX2lkIjoiY29yZS1yZWFsLXNtb2tlLXYyIiwicmVsZWFzZV9wbGFuX2RpZ2VzdCI6InNoYTI1Njo5ZWQ0ZTU4NmE2NjNiNWYxYWJhMTYxNzE4YmJjYTU4NGE2ZGMzMDZiY2I4OTVmZTFiYzA1ZDdiOTRhYTNiNGViIiwicmVzdWx0cyI6W3siY2FsbF9pZCI6InNtb2tlLTEtbW9kZWwtZ3B0NTYtcmVsYXktcmVzcG9uc2VzIiwiZXZpZGVuY2VfZGlnZXN0cyI6WyJzaGEyNTY6MThhMTVlOTE2NmEyODQ4YjRjYWIyNGNkMDRmNzEwMjY4ZDU4MWMyYzk3MzcxOGMyZjMxZGU0YmFiZTE5YzY4NyJdLCJldmlkZW5jZV9yZWZlcmVuY2VzIjpbIi9ob21lL2Rldi9oYXJuZXNzbGFiLW9wZXJhdG9yLWV2aWRlbmNlL2NvcmUtcmVhbC1zbW9rZS12Mi1hdHRlbXB0LTEyLThkODdjNjQxL3Ntb2tlLTEtbW9kZWwtZ3B0NTYtcmVsYXktcmVzcG9uc2VzL3Ntb2tlLTEtbW9kZWwtZ3B0NTYtcmVsYXktcmVzcG9uc2VzIl19XSwic2NoZW1hX3ZlcnNpb24iOjEsInNtb2tlX3BsYW5fZGlnZXN0Ijoic2hhMjU2OjhlMGI2NDgyZGFjNGNjYjAzMTJkODgxZWZmM2FiNjhmNzQxZDJiMjJiMDg1NTU3YjFmOTMxNWU5OWZkMWExOGEiLCJzdGF0dXMiOiJBQk9SVEVEIn0K",
}

MANIFEST_10 = "eyJjb250ZXh0X2RpZ2VzdCI6bnVsbCwiZW5kcG9pbnRfaWRlbnRpdHkiOiJncHQ1Ni1yZWxheXxyZXNwb25zZXN8ZW52OkhBUk5FU1NMQUJfR1BUNTZfUkVMQVlfQkFTRV9VUkwvcmVzcG9uc2VzIiwiZ2VuZXJhdGlvbl9zZXR0aW5ncyI6eyJhdHRlbXB0X2NvdW50IjoxLCJlZmZvcnQiOiJtZWRpdW0iLCJtYXhfb3V0cHV0X3Rva2VucyI6MjAwMCwicmVxdWVzdF90aW1lb3V0X3NlY29uZHMiOjkwLjAsInRlbXBlcmF0dXJlIjpudWxsfSwib2JzZXJ2ZWRfbW9kZWwiOm51bGwsIm91dGNvbWUiOiJwcm92aWRlcl9lcnJvciIsInBhcnNlZF9wYXRjaF9kaWdlc3QiOm51bGwsInByb21wdF9oYXNoIjoic2hhMjU2OmExZDU3OGNlY2JiOTYzMjAxMTE3ZGYyZTFhMjdmZDI5ODk2YzdlY2ZiYWM4ZDhkNjA2MmE0NjcxZTBiNjQzZWQiLCJwcm9tcHRfdGVtcGxhdGVfdmVyc2lvbiI6ImRpcmVjdC1wYXRjaC12MSIsInByb3RvY29sIjoicmVzcG9uc2VzIiwicHJvdmlkZXIiOiJncHQ1Ni1yZWxheSIsInByb3ZpZGVyX2Vycm9yIjp7ImF0dGVtcHRfY291bnQiOjEsImNhdGVnb3J5IjoidGltZW91dCIsImxhdGVuY3lfbXMiOjkwMjc3LCJyZXF1ZXN0X2lkIjpudWxsLCJyZXNwb25zZV9zdGF0dXMiOm51bGwsInN0YXR1c19jb2RlIjpudWxsLCJ0aW1lb3V0X3BoYXNlIjoicmVhZCJ9LCJwcm92aWRlcl9mYWlsdXJlIjoidGltZW91dCIsInByb3ZpZGVyX3Jlc3VsdCI6bnVsbCwicHVibGljX3Jlc3BvbnNlX2RpZ2VzdCI6bnVsbCwicHVibGljX3Jlc3BvbnNlX3RleHQiOm51bGwsInJlcXVlc3RlZF9tb2RlbCI6ImdwdC01LjYtc29sIiwicmVzb3VyY2VfYnVkZ2V0Ijp7Im1heF9vdXRwdXRfdG9rZW5zIjoyMDAwLCJuZXR3b3JrX3BvbGljeSI6ImRlbnkiLCJ0aW1lb3V0X3NlY29uZHMiOjkwfSwicnVuX2lkIjoic21va2UtMS1tb2RlbC1ncHQ1Ni1yZWxheS1yZXNwb25zZXMiLCJzY2hlbWFfdmVyc2lvbiI6MSwic3VtbWFyeSI6InByb3ZpZGVyIGludm9jYXRpb24gZmFpbGVkOiB0aW1lb3V0IiwidGFza19kaWdlc3QiOiJzaGEyNTY6YWY2NWY1ZjNhN2U3ZTBmOGMyOGZhMTY5MGM3NDE2MzE0YjgxOWQzZTI0NmIyMWQxYzQzM2U4MWRjYWFjZDdmOCIsInRhc2tfaWQiOiJjb3JlLXB5dGhvbi1kZWR1cGxpY2F0ZSIsInRhc2tfdmVyc2lvbiI6IjEuMC4wIiwidmVyaWZpZXJfYXJ0aWZhY3RfZGlnZXN0IjpudWxsLCJ2ZXJpZmllcl9hcnRpZmFjdF9uYW1lc3BhY2UiOm51bGwsInZlcmlmaWVyX2RlZmluaXRpb25fZGlnZXN0Ijoic2hhMjU2OjcxYmFkYzdiMzUyZDQzYmZlZTM0NjQxNjQ5MjFiYzBkZmQxYWRiMGNkMDhmOTgzOTdkNjU3MjE5MWQxZjFhMzIiLCJ2ZXJpZmllcl9wYXNzZWQiOm51bGwsInZlcmlmaWVyX3NhbmRib3hfbWFuaWZlc3QiOm51bGwsInZlcmlmaWVyX3Njb3JlIjpudWxsLCJ3b3Jrc3BhY2VfaW5wdXRfZGlnZXN0Ijoic2hhMjU2OjhjYTA5NWZkYmU5NDcxYzU1N2RmNGIxYzRjOWUzOTE0YmZhZWM0NmZkYWNkMDUyOTE4M2UzNjc5NWE2MWM2MGQiLCJ3b3Jrc3BhY2Vfb3V0cHV0X2RpZ2VzdCI6bnVsbH0="
MANIFEST_12 = "eyJjb250ZXh0X2RpZ2VzdCI6bnVsbCwiZW5kcG9pbnRfaWRlbnRpdHkiOiJncHQ1Ni1yZWxheXxyZXNwb25zZXN8ZW52OkhBUk5FU1NMQUJfR1BUNTZfUkVMQVlfQkFTRV9VUkwvcmVzcG9uc2VzIiwiZ2VuZXJhdGlvbl9zZXR0aW5ncyI6eyJhdHRlbXB0X2NvdW50IjoxLCJlZmZvcnQiOiJtZWRpdW0iLCJtYXhfb3V0cHV0X3Rva2VucyI6MjAwMCwicmVxdWVzdF90aW1lb3V0X3NlY29uZHMiOjkwLjAsInRlbXBlcmF0dXJlIjpudWxsfSwib2JzZXJ2ZWRfbW9kZWwiOm51bGwsIm91dGNvbWUiOiJwcm92aWRlcl9lcnJvciIsInBhcnNlZF9wYXRjaF9kaWdlc3QiOm51bGwsInByb21wdF9oYXNoIjoic2hhMjU2OmExZDU3OGNlY2JiOTYzMjAxMTE3ZGYyZTFhMjdmZDI5ODk2YzdlY2ZiYWM4ZDhkNjA2MmE0NjcxZTBiNjQzZWQiLCJwcm9tcHRfdGVtcGxhdGVfdmVyc2lvbiI6ImRpcmVjdC1wYXRjaC12MSIsInByb3RvY29sIjoicmVzcG9uc2VzIiwicHJvdmlkZXIiOiJncHQ1Ni1yZWxheSIsInByb3ZpZGVyX2Vycm9yIjp7ImF0dGVtcHRfY291bnQiOjEsImNhdGVnb3J5IjoidGltZW91dCIsImxhdGVuY3lfbXMiOjkwMzU4LCJyZWFkX3RpbWVvdXRfc3RhZ2UiOiJ3YWl0aW5nX2Zvcl9yZXNwb25zZV9oZWFkZXJzIiwicmVxdWVzdF9pZCI6bnVsbCwicmVzcG9uc2VfYm9keV9ieXRlc19yZWNlaXZlZCI6bnVsbCwicmVzcG9uc2VfaGVhZGVyX2xhdGVuY3lfbXMiOm51bGwsInJlc3BvbnNlX3N0YXR1cyI6bnVsbCwic3RhdHVzX2NvZGUiOm51bGwsInRpbWVvdXRfcGhhc2UiOiJyZWFkIn0sInByb3ZpZGVyX2ZhaWx1cmUiOiJ0aW1lb3V0IiwicHJvdmlkZXJfcmVzdWx0IjpudWxsLCJwdWJsaWNfcmVzcG9uc2VfZGlnZXN0IjpudWxsLCJwdWJsaWNfcmVzcG9uc2VfdGV4dCI6bnVsbCwicmVxdWVzdGVkX21vZGVsIjoiZ3B0LTUuNi1zb2wiLCJyZXNvdXJjZV9idWRnZXQiOnsibWF4X291dHB1dF90b2tlbnMiOjIwMDAsIm5ldHdvcmtfcG9saWN5IjoiZGVueSIsInRpbWVvdXRfc2Vjb25kcyI6OTB9LCJydW5faWQiOiJzbW9rZS0xLW1vZGVsLWdwdDU2LXJlbGF5LXJlc3BvbnNlcyIsInNjaGVtYV92ZXJzaW9uIjoxLCJzdW1tYXJ5IjoicHJvdmlkZXIgaW52b2NhdGlvbiBmYWlsZWQ6IHRpbWVvdXQiLCJ0YXNrX2RpZ2VzdCI6InNoYTI1NjphZjY1ZjVmM2E3ZTdlMGY4YzI4ZmExNjkwYzc0MTYzMTRiODE5ZDNlMjQ2YjIxZDFjNDMzZTgxZGNhYWNkN2Y4IiwidGFza19pZCI6ImNvcmUtcHl0aG9uLWRlZHVwbGljYXRlIiwidGFza192ZXJzaW9uIjoiMS4wLjAiLCJ2ZXJpZmllcl9hcnRpZmFjdF9kaWdlc3QiOm51bGwsInZlcmlmaWVyX2FydGlmYWN0X25hbWVzcGFjZSI6bnVsbCwidmVyaWZpZXJfZGVmaW5pdGlvbl9kaWdlc3QiOiJzaGEyNTY6NzFiYWRjN2IzNTJkNDNiZmVlMzQ2NDE2NDkyMWJjMGRmZDFhZGIwY2QwOGY5ODM5N2Q2NTcyMTkxZDFmMWEzMiIsInZlcmlmaWVyX3Bhc3NlZCI6bnVsbCwidmVyaWZpZXJfc2FuZGJveF9tYW5pZmVzdCI6bnVsbCwidmVyaWZpZXJfc2NvcmUiOm51bGwsIndvcmtzcGFjZV9pbnB1dF9kaWdlc3QiOiJzaGEyNTY6OGNhMDk1ZmRiZTk0NzFjNTU3ZGY0YjFjNGM5ZTM5MTRiZmFlYzQ2ZmRhY2QwNTI5MTgzZTM2Nzk1YTYxYzYwZCIsIndvcmtzcGFjZV9vdXRwdXRfZGlnZXN0IjpudWxsfQ=="

EXPECTED_DOMAINS = {
    10: (
        "sha256:be06f9eff5303db4f808b61dcf7da98d8a76a574a469f4bec474a8de95bff1df",
        "sha256:97a9aa721a2c0d16eb80cf8a03be05ea944b86d18a3c48be58876f7b79dc6057",
    ),
    11: (
        "sha256:72cc8eb4d076fe2d25fa8aabdbc23b4a69b865aaa492f30a6849be6f72d4c0b0",
        "sha256:5ea824fbcae24ee3b4ad6ccedd3c5f51167c7628dc7278509ef6aecf44a88259",
    ),
    12: (
        "sha256:056d49742d72366cdc630651563846aa15f3eee00d961bbbc3c98c9e9bc5f0a3",
        "sha256:18a15e9166a2848b4cab24cd04f710268d581c2c973718c2f31de4babe19c687",
    ),
}


def _historical_root(tmp_path: Path, attempt: int) -> Path:
    root = tmp_path / f"attempt-{attempt}"
    artifact = root / CALL_1 / CALL_1
    artifact.mkdir(parents=True)
    manifest = base64.b64decode(MANIFEST_12 if attempt == 12 else MANIFEST_10)
    if attempt == 11:
        manifest = manifest.replace(b"90277", b"90405")
    (artifact / "manifest.json").write_bytes(manifest)
    receipt = base64.b64decode(RECEIPTS[attempt]).replace(b'"failing_cal_id"', b'"failing_call_id"')
    (root / "smoke-execution.json").write_bytes(receipt)
    return root


@pytest.mark.parametrize("attempt", (10, 11, 12))
def test_historical_evidence_summary_derives_exact_digest_domains(
    tmp_path: Path, attempt: int
) -> None:
    root = _historical_root(tmp_path, attempt)
    before = digest_tree(root)
    summary = summarize_smoke_evidence(root)
    expected_receipt, expected_artifact = EXPECTED_DOMAINS[attempt]

    assert summary.receipt_digest_domain == "RAW_FILE_SHA256"
    assert summary.receipt_digest == expected_receipt
    assert summary.calls[0].evidence_digest_domain == "ARTIFACT_TREE_DIGEST"
    assert summary.calls[0].evidence_digest == expected_artifact
    history = json.loads(
        (ROOT / f"release/history/core-real-v2-attempt-{attempt}.json").read_text()
    )
    verify_history_against_summary(history, summary)
    assert digest_tree(root) == before


def _runtime() -> RuntimeIdentities:
    return RuntimeIdentities(
        codex_image=ImageIdentity(reference=CODEX_IMAGE, image_id="sha256:" + "1" * 64),
        claude_image=ImageIdentity(reference=CLAUDE_IMAGE, image_id="sha256:" + "2" * 64),
        deepseek_image=ImageIdentity(reference=DEEPSEEK_IMAGE, image_id="sha256:" + "3" * 64),
        egress_proxy_image=ImageIdentity(
            reference=EGRESS_PROXY_IMAGE, image_id="sha256:" + "4" * 64
        ),
        deepseek_config_digest="sha256:" + "5" * 64,
    )


def _environment() -> dict[str, str]:
    return {
        "HARNESSLAB_GPT56_RELAY_BASE_URL": "https://matrix-test.invalid",
        "HARNESSLAB_GPT56_RELAY_API_KEY": "fake-relay-reference",
        "HARNESSLAB_OPENCODE_GO_API_KEY": "fake-opencode-reference",
        "DEEPSEEK_API_KEY": "fake-deepseek-reference",
    }


def test_real_matrix_preflight_is_exact_keyless_and_frozen() -> None:
    receipt = MatrixControlPlane.load(ROOT).preflight(_runtime())

    assert (receipt.cells, receipt.tasks, receipt.repeats, receipt.logical_runs) == (7, 18, 5, 630)
    assert receipt.real_calls == 0
    assert receipt.max_runs_required_for_execution
    assert {item.cell_id for item in receipt.cells_detail} == {
        "model-gpt56-relay-responses",
        "model-qwen38-opencode-go-messages",
        "model-deepseek-v4pro-chat",
        "harness-codex-gpt56-medium",
        "harness-codex-gpt56-high",
        "harness-claude-qwen38-opencode-go",
        "harness-deepseek-v4flash",
    }


@pytest.mark.asyncio
async def test_real_matrix_has_no_implicit_full_launch_default(tmp_path: Path) -> None:
    with pytest.raises(MatrixControlPlaneError, match="--allow-real-matrix"):
        await execute_real_matrix(
            ROOT,
            allow_real_matrix=False,
            max_runs=1,
            artifact_root=tmp_path / "artifacts",
            runtime_root=tmp_path / "runtime",
        )
    with pytest.raises(MatrixControlPlaneError, match="--max-runs"):
        await execute_real_matrix(
            ROOT,
            allow_real_matrix=True,
            max_runs=None,
            artifact_root=tmp_path / "artifacts",
            runtime_root=tmp_path / "runtime",
        )


class _DiagnosticInvoker:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls: list[str] = []

    async def invoke(self, binding: object) -> SmokeCallResult:
        call_id = binding.frozen.call.call_id  # type: ignore[attr-defined]
        self.calls.append(call_id)
        artifact = self.root / call_id / call_id
        artifact.mkdir(parents=True)
        (artifact / "manifest.json").write_text(
            json.dumps(
                {
                    "requested_model": binding.frozen.call.requested_model,  # type: ignore[attr-defined]
                    "observed_model": None,
                    "outcome": "provider_error"
                    if call_id == EXPECTED_CALL_IDS[4]
                    else "verified_pass",
                    "provider_failure": "timeout" if call_id == EXPECTED_CALL_IDS[4] else None,
                    "workspace_input_digest": "sha256:" + "6" * 64,
                    "workspace_output_digest": "sha256:" + "6" * 64,
                    "verifier_passed": call_id != EXPECTED_CALL_IDS[4],
                    "verifier_score": 1.0 if call_id != EXPECTED_CALL_IDS[4] else None,
                    "duration_ms": 10,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        result = SmokeCallResult(
            call_id=call_id,
            evidence_references=(str(artifact),),
            evidence_digests=(digest_tree(artifact),),
        )
        if call_id == EXPECTED_CALL_IDS[4]:
            raise SmokeCallFailure(SmokeFailureCategory.PROVIDER_FAILURE, "fake", result)
        return result


@pytest.mark.asyncio
async def test_diagnostic_sweep_skips_attempted_continues_and_is_non_promotable(
    tmp_path: Path,
) -> None:
    control = SmokeControlPlane.load(ROOT)
    receipt = SmokeExecutionReceipt(
        plan_id=control.smoke_plan.plan_id,
        smoke_plan_digest=control.smoke_plan_digest,
        release_plan_digest=control.release_plan.digest,
        status=SmokeExecutionStatus.ABORTED,
        attempted_top_level_launches=2,
        failing_call_id=EXPECTED_CALL_IDS[1],
        failure_category=SmokeFailureCategory.PROVIDER_FAILURE,
        results=(),
    )
    receipt_path = tmp_path / "attempt-13.json"
    receipt_path.write_text(receipt.canonical_json() + "\n", encoding="utf-8")
    output = tmp_path / "diagnostic"
    invoker = _DiagnosticInvoker(output)
    report = await execute_component_diagnostics(
        control,
        control.resolve_real_bindings(_environment(), _runtime()),
        invoker,
        attempt_receipt_path=receipt_path,
        artifact_root=output,
    )

    assert invoker.calls == list(EXPECTED_CALL_IDS[2:])
    assert report.evidence_class == "DIAGNOSTIC_ONLY"
    assert report.release_promotable is False
    assert report.diagnostic_top_level_launches == 6
    assert len(report.results) == 6
    assert report.results[2].failure_category is SmokeFailureCategory.PROVIDER_FAILURE
    with pytest.raises(ValidationError, match="never release-promotable"):
        EvidenceBinding(
            state=EvidenceState.VERIFIED,
            identity="DIAGNOSTIC_ONLY:component-report",
            digest="sha256:" + "7" * 64,
        )


def test_telemetry_reports_observed_values_and_requires_price_input(tmp_path: Path) -> None:
    root = tmp_path / "complete"
    results: list[SmokeCallResult] = []
    for index, call_id in enumerate(EXPECTED_CALL_IDS, start=1):
        artifact = root / call_id / call_id
        artifact.mkdir(parents=True)
        (artifact / "manifest.json").write_text(
            json.dumps(
                {
                    "requested_model": f"model-{index}",
                    "observed_model": f"model-{index}",
                    "outcome": "verified_pass",
                    "duration_ms": index * 100,
                    "usage": {
                        "input_tokens": index,
                        "output_tokens": index * 2,
                        "total_tokens": index * 3,
                    },
                    "generation_settings": {"attempt_count": 1},
                    "trace_event_count": index,
                    "trace_coverage": "FULL_STREAM",
                    "workspace_input_digest": "sha256:" + "8" * 64,
                    "workspace_output_digest": "sha256:" + "9" * 64,
                    "verifier_passed": True,
                    "verifier_score": 1.0,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        results.append(
            SmokeCallResult(
                call_id=call_id,
                evidence_references=(str(artifact),),
                evidence_digests=(digest_tree(artifact),),
            )
        )
    receipt = SmokeExecutionReceipt(
        plan_id="core-real-smoke-v2",
        smoke_plan_digest=SMOKE_DIGEST,
        release_plan_digest=RELEASE_DIGEST,
        status=SmokeExecutionStatus.SUCCEEDED,
        attempted_top_level_launches=8,
        results=tuple(results),
    )
    (root / "smoke-execution.json").write_text(receipt.canonical_json() + "\n")

    summary = summarize_smoke_telemetry(root)
    assert summary.telemetry_status == "PASS"
    assert summary.total_smoke_duration_ms == 3600
    assert summary.available_total_tokens == 108
    assert summary.observable_provider_request_count == 8
    assert summary.matrix_logical_run_count == 630
    assert summary.judge_calibration_count == 63
    assert summary.cost_estimate == "PRICE_INPUT_REQUIRED"
    assert summary.wall_clock_scenarios_ms is not None
