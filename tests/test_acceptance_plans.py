"""Synthetic scope-only tests: no subject, verifier, provider, DB or runtime execution."""

# ruff: noqa: RUF001
from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from harnesslab.acceptance_plans import service
from harnesslab.api.app import create_app
from harnesslab.code_snapshots import service as snapshots
from harnesslab.external_evidence.models import EvidencePolicy
from tests.local_plan_helpers import HEADERS
from tests.test_code_snapshots import policy as policy
from tests.test_code_snapshots import zipped

PREFIX = "/api/acceptance-plans"
PROMPT = "给我做一个轻量电商系统\uff0c命名为 MiniShop"


@pytest.fixture
async def client(
    policy: EvidencePolicy, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("HARNESSLAB_ACCEPTANCE_PLAN_STORE", str(tmp_path / "scopes"))
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://localhost", headers=HEADERS
    ) as value:
        yield value


@pytest.fixture
def snapshot(policy: EvidencePolicy) -> dict[str, Any]:
    data = zipped([("example.txt", b"synthetic opaque source: never execute")])
    preview = snapshots.preview(data, "unknown")
    return snapshots.confirm(
        policy,
        data,
        "unknown",
        consent=snapshots.CONSENT,
        archive_sha256=preview["manifest"]["archive_sha256"],
        manifest_sha256=preview["manifest_sha256"],
        signature=preview["review_signature"],
    )


def creation(snapshot: dict[str, Any], prompt: str = PROMPT) -> dict[str, Any]:
    return {
        "request_id": uuid4().hex,
        "snapshot_identity": snapshot["identity"],
        "snapshot_content_digest": snapshot["manifest"]["content_digest"],
        "original_prompt": prompt,
    }


async def create(
    client: AsyncClient, snapshot: dict[str, Any], prompt: str = PROMPT
) -> dict[str, Any]:
    response = await client.post(PREFIX, json=creation(snapshot, prompt))
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def mutation(event: dict[str, Any], action: str, **kwargs: Any) -> dict[str, Any]:
    return {
        "request_id": uuid4().hex,
        "expected_digest": event["digest"],
        "action": action,
        "reason": "Synthetic operator review",
        **kwargs,
    }


async def change(
    client: AsyncClient, event: dict[str, Any], action: str, **kwargs: Any
) -> dict[str, Any]:
    response = await client.post(
        f"{PREFIX}/{event['state']['plan_id']}/changes", json=mutation(event, action, **kwargs)
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


async def approve(
    client: AsyncClient, event: dict[str, Any], clause_id: str = "c1", text: str | None = None
) -> dict[str, Any]:
    item = next(c for c in event["state"]["clauses"] if c["id"] == clause_id)
    return await change(
        client, event, "REVIEW", clause_id=clause_id, text=text or item["text"], decision="APPROVED"
    )


async def test_minishop_sources_and_unconfirmed_suggestions(
    client: AsyncClient, snapshot: dict[str, Any]
) -> None:
    event = await create(client, snapshot)
    state = event["state"]
    assert state["status"] == "DRAFT"
    assert state["original_prompt"] == PROMPT
    assert [c["source"] for c in state["clauses"]] == ["EXPLICIT_IN_PROMPT"] * 2 + ["AMBIGUOUS"] + [
        "SUGGESTED_ONLY"
    ] * 5
    assert all(c["decision"] == "PENDING" for c in state["clauses"])
    for item in state["clauses"][:3]:
        assert item["origin"]["quote"] in PROMPT
    assert state["uncovered"] and all(state[k] == v for k, v in service.BOUNDARY.items())
    response = await client.post(
        f"{PREFIX}/{state['plan_id']}/changes",
        json=mutation(event, "CONFIRM", acknowledgement="SCOPE_ONLY_NO_EXECUTION"),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ACCEPTANCE_EMPTY_SCOPE"


@pytest.mark.parametrize(
    "prompt",
    [
        "做个系统",
        "不要做电商系统，命名为 MiniShop",
        "系统必须支持商品查询和库存不足时拒绝订单。",
        PROMPT + "，但不要购物车",
        "<script>alert('x')</script>",
    ],
)
async def test_unknown_explicit_or_ambiguous_requires_manual_review(
    client: AsyncClient, snapshot: dict[str, Any], prompt: str
) -> None:
    event = await create(client, snapshot, prompt)
    assert event["state"]["original_prompt"] == prompt
    assert [c["source"] for c in event["state"]["clauses"]] == ["AMBIGUOUS"]
    assert event["state"]["clauses"][0]["origin"]["quote"] == prompt


async def test_approval_edit_reject_and_pending_keep_original_sources(
    client: AsyncClient, snapshot: dict[str, Any]
) -> None:
    first = await create(client, snapshot)
    edited = await approve(client, first, "c4", "商品列表展示已发布商品的名称")
    item = edited["state"]["clauses"][3]
    assert item["source"] == "USER_APPROVED_ADDITION"
    assert item["origin"] == first["state"]["clauses"][3]["origin"]
    assert item["reviewed_at"] and item["review_reason"]
    edited = await approve(client, edited, "c1", "系统名称和页眉都使用 MiniShop")
    assert edited["state"]["clauses"][0]["source"] == "USER_APPROVED_ADDITION"
    assert edited["state"]["clauses"][0]["origin"]["source"] == "EXPLICIT_IN_PROMPT"
    rejected = await change(
        client, edited, "REVIEW", clause_id="c5", text="无需购物车", decision="REJECTED"
    )
    confirmed = await change(client, rejected, "CONFIRM", acknowledgement="SCOPE_ONLY_NO_EXECUTION")
    assert confirmed["state"]["status"] == "CONFIRMED" and confirmed["state"]["confirmed_at"]
    assert [c["decision"] for c in confirmed["state"]["clauses"]].count("APPROVED") == 2
    history = (await client.get(f"{PREFIX}/{first['state']['plan_id']}")).json()["history"]
    assert history[0] == first
    assert history[1]["state"]["clauses"][3]["text"] == "商品列表展示已发布商品的名称"


async def test_manual_clause_requires_separate_approval(
    client: AsyncClient, snapshot: dict[str, Any]
) -> None:
    event = await create(client, snapshot, "明确要求：按名称搜索商品")
    event = await change(
        client, event, "ADD", text="按名称搜索商品，返回匹配商品", reason="人工依据原文编写"
    )
    assert event["state"]["clauses"][1]["source"] == "SUGGESTED_ONLY"
    event = await approve(client, event, "c2")
    assert event["state"]["clauses"][1]["source"] == "USER_APPROVED_ADDITION"
    assert event["state"]["clauses"][1]["origin"]["kind"] == "manual:operator"


async def test_freeze_revision_restart_and_immutable_history(
    client: AsyncClient, snapshot: dict[str, Any]
) -> None:
    first = await create(client, snapshot)
    event = await approve(client, first)
    event = await change(client, event, "CONFIRM", acknowledgement="SCOPE_ONLY_NO_EXECUTION")
    url = f"{PREFIX}/{event['state']['plan_id']}"
    for status in ("CONFIRMED", "FROZEN"):
        assert event["state"]["status"] == status
        rejected = await client.post(
            url + "/changes",
            json=mutation(event, "REVIEW", clause_id="c1", text="overwrite", decision="APPROVED"),
        )
        assert rejected.status_code == 409
        if status == "CONFIRMED":
            event = await change(client, event, "FREEZE", acknowledgement="SCOPE_ONLY_NO_EXECUTION")
    frozen = event
    root = service.root_path() / event["state"]["plan_id"]
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    revised = await change(client, event, "REVISE", acknowledgement="SCOPE_ONLY_NO_EXECUTION")
    assert revised["state"]["version"] == 2 and revised["state"]["status"] == "DRAFT"
    assert revised["state"]["parent_frozen_digest"] == frozen["digest"]
    assert all(c["decision"] == "PENDING" for c in revised["state"]["clauses"])
    assert revised["state"]["original_prompt"] == first["state"]["original_prompt"]
    assert all((root / name).read_bytes() == data for name, data in before.items())
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://localhost", headers=HEADERS
    ) as restarted:
        result = await restarted.get(url)
    assert result.json()["current"] == revised
    assert frozen in result.json()["history"]
    assert result.headers["cache-control"] == "no-store"


async def test_idempotency_and_concurrent_writers(
    client: AsyncClient, snapshot: dict[str, Any]
) -> None:
    payload = creation(snapshot)
    responses = await asyncio.gather(*(client.post(PREFIX, json=payload) for _ in range(3)))
    assert all(r.status_code == 200 for r in responses)
    assert responses[0].json() == responses[1].json() == responses[2].json()
    event = responses[0].json()
    conflict = await client.post(PREFIX, json={**payload, "original_prompt": "Different"})
    assert conflict.status_code == 409
    event = await approve(client, event)
    url = f"{PREFIX}/{event['state']['plan_id']}/changes"
    confirm = mutation(event, "CONFIRM", acknowledgement="SCOPE_ONLY_NO_EXECUTION")
    responses = await asyncio.gather(*(client.post(url, json=confirm) for _ in range(4)))
    assert all(r.status_code == 200 for r in responses)
    assert all(r.json() == responses[0].json() for r in responses)
    assert (await client.post(url, json={**confirm, "reason": "changed"})).status_code == 409
    frozen = await change(
        client, responses[0].json(), "FREEZE", acknowledgement="SCOPE_ONLY_NO_EXECUTION"
    )
    requests = [
        mutation(frozen, "REVISE", acknowledgement="SCOPE_ONLY_NO_EXECUTION") for _ in range(2)
    ]
    responses = await asyncio.gather(*(client.post(url, json=r) for r in requests))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert (
        next(r for r in responses if r.status_code == 409).json()["error"]["code"]
        == "ACCEPTANCE_STALE"
    )


@pytest.mark.parametrize("defect", ["missing", "identity", "bytes", "rights", "symlink"])
async def test_snapshot_binding_rejected(
    client: AsyncClient,
    snapshot: dict[str, Any],
    policy: EvidencePolicy,
    defect: str,
    tmp_path: Path,
) -> None:
    payload = creation(snapshot)
    path = snapshots.storage(policy) / snapshot["identity"] / "snapshot.json"
    if defect == "missing":
        payload["snapshot_identity"] = "f" * 64
    elif defect == "identity":
        payload["snapshot_content_digest"] = "sha256:" + "f" * 64
    elif defect == "bytes":
        path.chmod(0o600)
        path.write_bytes(b"{}")
        path.chmod(0o400)
    elif defect == "rights":
        path.chmod(0o600)
    else:
        target = tmp_path / "synthetic-copy.json"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
    response = await client.post(PREFIX, json=payload)
    assert response.status_code == 409
    assert not (tmp_path / "scopes").exists()


async def test_later_snapshot_corruption_keeps_history_readable(
    client: AsyncClient, snapshot: dict[str, Any], policy: EvidencePolicy
) -> None:
    event = await create(client, snapshot)
    path = snapshots.storage(policy) / snapshot["identity"] / "snapshot.json"
    path.chmod(0o600)
    path.write_bytes(b"{}")
    path.chmod(0o400)
    url = f"{PREFIX}/{event['state']['plan_id']}"
    result = (await client.get(url)).json()
    assert result["current"] == event and result["snapshot_binding"] == "UNAVAILABLE_OR_CHANGED"
    assert (
        await client.post(url + "/changes", json=mutation(event, "ADD", text="New"))
    ).status_code == 409


async def test_journal_tamper_rejected(client: AsyncClient, snapshot: dict[str, Any]) -> None:
    event = await create(client, snapshot)
    path = next((service.root_path() / event["state"]["plan_id"]).iterdir())
    data = json.loads(path.read_bytes())
    data["state"]["original_prompt"] = "changed"
    path.chmod(0o600)
    path.write_text(json.dumps(data))
    path.chmod(0o400)
    response = await client.get(f"{PREFIX}/{event['state']['plan_id']}")
    assert response.status_code == 409 and "changed" not in response.text


@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Bearer invalid"},
        {"Origin": "http://foreign.example"},
        {"Host": "attacker.example"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
async def test_permissions_and_no_execution(
    client: AsyncClient, snapshot: dict[str, Any], headers: dict[str, str]
) -> None:
    response = await client.post(PREFIX, json=creation(snapshot), headers=headers)
    assert response.status_code == 403 and response.headers["cache-control"] == "no-store"
    assert PROMPT not in response.text
    assert (await client.get(PREFIX, headers=headers)).status_code == 403


async def test_public_demo_and_execution_never_authorized(
    client: AsyncClient, snapshot: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    event = await create(client, snapshot)
    url = f"{PREFIX}/{event['state']['plan_id']}"
    assert (await client.post(url + "/execute", json={})).json()["error"][
        "code"
    ] == "ACCEPTANCE_EXECUTION_DISABLED"
    monkeypatch.setenv("HARNESSLAB_PUBLIC_DEMO_MANIFEST", str(tmp_path / "unused.json"))
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://localhost", headers=HEADERS
    ) as public:
        assert (await public.get(url)).status_code == 403
        assert (await public.post(PREFIX, json=creation(snapshot))).status_code == 403
        assert (await public.get(PREFIX + "/status")).json()["enabled"] is False


@pytest.mark.parametrize(
    "extra",
    [
        {"source": "EXPLICIT_IN_PROMPT"},
        {"original_prompt": ""},
        {"original_prompt": " "},
        {"original_prompt": "x" * 16001},
        {"original_prompt": "api_key='abcdefghijklmno'"},
    ],
)
async def test_invalid_or_secret_input_not_reflected(
    client: AsyncClient, snapshot: dict[str, Any], extra: dict[str, Any]
) -> None:
    response = await client.post(PREFIX, json=creation(snapshot) | extra)
    assert response.status_code in {409, 422}
    assert "abcdefghijklmno" not in response.text


async def test_body_limit_and_scope_store_overlap(
    client: AsyncClient,
    snapshot: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    policy: EvidencePolicy,
) -> None:
    response = await client.post(
        PREFIX, content=b"x" * 96001, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    monkeypatch.setenv("HARNESSLAB_ACCEPTANCE_PLAN_STORE", str(policy.store / "scopes"))
    assert (await client.post(PREFIX, json=creation(snapshot))).status_code == 409
    assert not (policy.store / "scopes").exists()


async def test_read_only_snapshot_and_no_receipt_or_admission(
    client: AsyncClient, snapshot: dict[str, Any], policy: EvidencePolicy
) -> None:
    before = {
        p.relative_to(policy.store): p.read_bytes() for p in policy.store.rglob("*") if p.is_file()
    }
    assert (await client.get(PREFIX + "/snapshots")).json()["items"][0]["identity"] == snapshot[
        "identity"
    ]
    event = await create(client, snapshot)
    event = await approve(client, event)
    event = await change(client, event, "CONFIRM", acknowledgement="SCOPE_ONLY_NO_EXECUTION")
    event = await change(client, event, "FREEZE", acknowledgement="SCOPE_ONLY_NO_EXECUTION")
    assert all(event["state"][k] == v for k, v in service.BOUNDARY.items())
    assert (await client.get(PREFIX)).json()["items"][0]["status"] == "FROZEN"
    after = {
        p.relative_to(policy.store): p.read_bytes() for p in policy.store.rglob("*") if p.is_file()
    }
    assert before == after


async def test_interrupted_publication_can_retry_without_partial_plan(
    client: AsyncClient, snapshot: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = creation(snapshot)
    original = os.rename

    def interrupted(*args: Any, **kwargs: Any) -> None:
        raise OSError("synthetic publication interruption")

    with monkeypatch.context() as context:
        context.setattr(os, "rename", interrupted)
        assert (await client.post(PREFIX, json=payload)).status_code == 409
    assert os.rename is original
    assert (await client.get(PREFIX)).json() == {"items": []}
    recovered = await client.post(PREFIX, json=payload)
    assert recovered.status_code == 200
    event = recovered.json()
    with monkeypatch.context() as context:
        context.setattr(os, "rename", interrupted)
        assert (
            await client.post(
                f"{PREFIX}/{event['state']['plan_id']}/changes",
                json=mutation(event, "ADD", text="Synthetic next candidate"),
            )
        ).status_code == 409
    current = (await client.get(f"{PREFIX}/{event['state']['plan_id']}")).json()
    assert current["current"] == event and len(current["history"]) == 1


async def test_confirmation_and_client_source_forgery_refused(
    client: AsyncClient, snapshot: dict[str, Any]
) -> None:
    event = await approve(client, await create(client, snapshot))
    url = f"{PREFIX}/{event['state']['plan_id']}/changes"
    assert (await client.post(url, json=mutation(event, "CONFIRM"))).status_code == 409
    forged = mutation(event, "REVIEW", clause_id="c4", text="invented", decision="APPROVED")
    forged["source"] = "EXPLICIT_IN_PROMPT"
    assert (await client.post(url, json=forged)).status_code == 422
    assert (
        await client.post(
            url,
            json=mutation(
                event, "REVIEW", clause_id="c4", text="invented", decision="APPROVED", reason=" "
            ),
        )
    ).status_code == 409
