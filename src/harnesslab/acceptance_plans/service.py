"""Bounded append-only journal, serialized across processes; snapshots are read-only inputs."""

# ruff: noqa: RUF001
from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harnesslab.acceptance_plans.models import ChangePlan, CreatePlan
from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.code_snapshots import service as snapshots
from harnesslab.episodes.hooks import encode
from harnesslab.external_evidence import service as evidence
from harnesslab.local_plans.tasks import bounded_files, fail, no_links
from harnesslab.registry.models import canonical_digest

MAX_EVENTS = 256
MAX_PLANS = 1000
MAX_STORE_BYTES = 128_000_000
MAX_EVENT_BYTES = 512_000
BOUNDARY = {
    "audit_context": "POST_DELIVERY_AUDIT",
    "verifier_status": "NO_QUALIFIED_BOUND_VERIFIER",
    "acceptance_result": "NOT_RUN",
    "execution_authorized": False,
    "taskstore_admitted": False,
}


def now() -> str:
    return datetime.now(UTC).isoformat()


def check(condition: bool, code: str = "ACCEPTANCE_INTEGRITY_ERROR") -> None:
    if not condition:
        raise fail(code, "Acceptance scope request or stored identity is invalid.", 409)


def checked_snapshot(identity: str, content_digest: str | None = None) -> dict[str, Any]:
    try:
        result = snapshots.read(evidence.load_policy(), identity)
        check(
            content_digest is None or result["manifest"]["content_digest"] == content_digest,
            "ACCEPTANCE_SNAPSHOT_MISMATCH",
        )
        return result
    except WorkbenchAPIError as exc:
        if exc.code == "ACCEPTANCE_SNAPSHOT_MISMATCH":
            raise
        raise fail(
            "ACCEPTANCE_SNAPSHOT_UNAVAILABLE", "Snapshot failed integrity checks.", 409
        ) from None
    except (OSError, ValueError, KeyError, TypeError):
        raise fail(
            "ACCEPTANCE_SNAPSHOT_UNAVAILABLE", "Snapshot failed integrity checks.", 409
        ) from None


def root_path() -> Path:
    configured = os.environ.get("HARNESSLAB_ACCEPTANCE_PLAN_STORE")
    if not configured:
        raise fail("ACCEPTANCE_DISABLED", "Configure a separate private acceptance store.", 403)
    root = Path(configured)
    evidence.safe_root(root)
    policy = evidence.load_policy()
    protected = snapshots.protected_roots(policy)
    protected.append(Path(os.environ["HARNESSLAB_EXTERNAL_EVIDENCE_POLICY"]))
    for env in ("HARNESSLAB_LOCAL_TASK_POLICY", "HARNESSLAB_LOCAL_EXECUTION_POLICY"):
        if os.environ.get(env):
            protected.append(Path(os.environ[env]))
    check(not any(evidence.overlap(root, path) for path in protected), "ACCEPTANCE_STORE_UNSAFE")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.stat()
    check(
        info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
        "ACCEPTANCE_STORE_UNSAFE",
    )
    return root


@contextmanager
def locked() -> Iterator[Path]:
    try:
        root = root_path()
        lock_path = root / ".lock"
        no_links(lock_path)
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a") as lock:
            check(os.fstat(lock.fileno()).st_nlink == 1, "ACCEPTANCE_STORE_UNSAFE")
            fcntl.flock(lock, fcntl.LOCK_EX)
            # Inventory scanning must share the publication lock: otherwise a
            # concurrent rename/removal of staging files can look like corruption.
            bounded_files(root, max_files=MAX_PLANS * MAX_EVENTS + 1, max_bytes=MAX_STORE_BYTES)
            yield root
    except (OSError, ValueError, KeyError, TypeError):
        raise fail(
            "ACCEPTANCE_INTEGRITY_ERROR", "Private scope storage is unavailable or changed.", 409
        ) from None


def history(root: Path, plan_id: str) -> list[dict[str, Any]]:
    check(bool(re.fullmatch(r"[a-f0-9]{64}", plan_id)), "ACCEPTANCE_NOT_FOUND")
    folder = root / plan_id
    if not folder.exists():
        raise fail("ACCEPTANCE_NOT_FOUND", "Acceptance plan does not exist.", 404)
    no_links(folder)
    paths = sorted(folder.iterdir())
    check(0 < len(paths) <= MAX_EVENTS)
    events: list[dict[str, Any]] = []
    previous: str | None = None
    for sequence, path in enumerate(paths, 1):
        no_links(path)
        info = path.stat()
        check(
            stat.S_ISREG(info.st_mode)
            and stat.S_IMODE(info.st_mode) == 0o400
            and info.st_uid == os.getuid()
            and info.st_nlink == 1
            and info.st_size <= MAX_EVENT_BYTES
        )
        payload = path.read_bytes()
        event = json.loads(payload)
        digest = canonical_digest(event)
        check(path.name == f"{sequence:04d}-{digest[7:]}.json" and encode(event) == payload)
        check(
            event["previous_digest"] == previous
            and event["sequence"] == sequence
            and event["state"]["plan_id"] == plan_id
        )
        check(all(event["state"].get(k) == v for k, v in BOUNDARY.items()))
        if events:
            check(
                event["state"]["original_prompt"] == events[0]["state"]["original_prompt"]
                and event["state"]["snapshot"] == events[0]["state"]["snapshot"]
            )
        events.append({**event, "digest": digest})
        previous = digest
    return events


def append(
    root: Path,
    state: dict[str, Any],
    events: list[dict[str, Any]],
    request: CreatePlan | ChangePlan,
    action: str,
) -> dict[str, Any]:
    check(len(events) < MAX_EVENTS, "ACCEPTANCE_HISTORY_LIMIT")
    event = {
        "schema": "acceptance-plan-event-v1",
        "sequence": len(events) + 1,
        "previous_digest": events[-1]["digest"] if events else None,
        "request_id": request.request_id,
        "request_digest": canonical_digest(request.model_dump(mode="json")),
        "action": action,
        "reason": getattr(request, "reason", "Original Prompt and snapshot binding"),
        "actor": "LOCAL_OPERATOR",
        "at": now(),
        "state": state,
    }
    payload = encode(event)
    check(len(payload) <= MAX_EVENT_BYTES, "ACCEPTANCE_SIZE_LIMIT")
    bounded_files(root, max_files=MAX_PLANS * MAX_EVENTS, max_bytes=MAX_STORE_BYTES - len(payload))
    folder = root / state["plan_id"]
    digest = canonical_digest(event)
    filename = f"{len(events) + 1:04d}-{digest[7:]}.json"
    # Publish the first directory atomically too: an interrupted create must not leave
    # an empty visible plan that prevents an identical request from recovering.
    with tempfile.TemporaryDirectory(prefix=".acceptance-", dir=root) as temporary:
        stage = Path(temporary) / "event"
        stage.mkdir(mode=0o700)
        staged_file = stage / filename
        with staged_file.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fchmod(stream.fileno(), 0o400)
            os.fsync(stream.fileno())
        if not events:
            check(not folder.exists())
            os.rename(stage, folder)
        else:
            destination = folder / filename
            check(not destination.exists())
            os.rename(staged_file, destination)
        for directory in (folder, root):
            directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    return {**event, "digest": digest}


def duplicate(
    events: list[dict[str, Any]], request: CreatePlan | ChangePlan
) -> dict[str, Any] | None:
    for event in events:
        if event["request_id"] == request.request_id:
            check(
                event["request_digest"] == canonical_digest(request.model_dump(mode="json")),
                "ACCEPTANCE_IDEMPOTENCY_CONFLICT",
            )
            return event
    return None


def clause(
    identifier: str, text: str, source: str, origin: str, quote: str | None = None
) -> dict[str, Any]:
    return {
        "id": identifier,
        "text": text,
        "source": source,
        "decision": "PENDING",
        "origin": {"kind": origin, "source": source, "text": text, "quote": quote},
        "reviewed_at": None,
        "review_reason": None,
    }


def draft(prompt: str) -> tuple[list[dict[str, Any]], list[str]]:
    # Intentionally narrow full-sentence grammar: negation, quotes, extra instructions and
    # unknown phrasing fall back to human review, never keyword-based mandatory features.
    match = re.fullmatch(
        r"给我做一个(轻量电商系统)[，,]命名为 ([A-Za-z][A-Za-z0-9_-]{0,63})[。.]?", prompt
    )
    clauses = []
    if match:
        direction, name = match.groups()
        clauses = [
            clause(
                "c1",
                f"系统命名为 {name}",
                "EXPLICIT_IN_PROMPT",
                "rule:minishop-sentence-v1",
                f"命名为 {name}",
            ),
            clause(
                "c2",
                "产品方向为轻量电商系统；具体能力范围需逐项约定",
                "EXPLICIT_IN_PROMPT",
                "rule:minishop-sentence-v1",
                direction,
            ),
            clause(
                "c3",
                "澄清“轻量”的规模、用户角色及交付界面",
                "AMBIGUOUS",
                "rule:minishop-sentence-v1",
                "轻量电商系统",
            ),
        ]
        for feature in ("商品列表", "购物车", "订单", "库存", "支付"):
            clauses.append(
                clause(
                    f"c{len(clauses) + 1}",
                    f"约定{feature}的可观察行为与边界",
                    "SUGGESTED_ONLY",
                    "template:commerce-v1",
                )
            )
    else:
        clauses = [
            clause(
                "c1",
                "请人工编写可观察的验收条件，并审查与原文的关系",
                "AMBIGUOUS",
                "manual-fallback-v1",
                prompt,
            )
        ]
    return clauses, [
        "未自动覆盖：具体交互、边界输入、异常处理、性能、安全及部署要求。",
        "确定性规则仅识别有限句式；原文其他含义需人工审查，未确认项不作为失败标准。",
    ]


def create(request: CreatePlan) -> dict[str, Any]:
    check(bool(request.original_prompt.strip()), "ACCEPTANCE_EMPTY_PROMPT")
    # Credential patterns reuse existing source intake safety; no Prompt is ever logged.
    evidence.safe_content(request.original_prompt.encode())
    snapshot = checked_snapshot(request.snapshot_identity, request.snapshot_content_digest)
    plan_id = canonical_digest({"kind": "acceptance-plan-v1", "request_id": request.request_id})[7:]
    with locked() as root:
        if (root / plan_id).exists():
            events = history(root, plan_id)
            found = duplicate(events, request)
            check(found is not None)
            assert found is not None
            return found
        check(sum(p.is_dir() for p in root.iterdir()) < MAX_PLANS, "ACCEPTANCE_STORE_LIMIT")
        clauses, uncovered = draft(request.original_prompt)
        state = {
            "plan_id": plan_id,
            "version": 1,
            "status": "DRAFT",
            **BOUNDARY,
            "original_prompt": request.original_prompt,
            "snapshot": {
                "identity": snapshot["identity"],
                "content_digest": snapshot["manifest"]["content_digest"],
            },
            "clauses": clauses,
            "uncovered": uncovered,
            "confirmed_at": None,
            "frozen_at": None,
            "parent_frozen_digest": None,
        }
        return append(root, state, [], request, "CREATE")


def change(plan_id: str, request: ChangePlan) -> dict[str, Any]:
    evidence.safe_content(encode(request.model_dump(mode="json")))
    check(bool(request.reason.strip()), "ACCEPTANCE_REASON_REQUIRED")
    with locked() as root:
        events = history(root, plan_id)
        state = json.loads(json.dumps(events[-1]["state"]))
        checked_snapshot(state["snapshot"]["identity"], state["snapshot"]["content_digest"])
        if found := duplicate(events, request):
            return found
        check(events[-1]["digest"] == request.expected_digest, "ACCEPTANCE_STALE")
        action = request.action
        check(
            (action in {"ADD", "REVIEW", "CONFIRM"} and state["status"] == "DRAFT")
            or (action == "FREEZE" and state["status"] == "CONFIRMED")
            or (action == "REVISE" and state["status"] == "FROZEN"),
            "ACCEPTANCE_STATE_CONFLICT",
        )
        if action in {"ADD", "REVIEW"}:
            check(
                request.text is not None and bool(request.text.strip()), "ACCEPTANCE_TEXT_REQUIRED"
            )
            check(request.acknowledgement is None, "ACCEPTANCE_ACTION_FIELDS")
            if action == "ADD":
                check(
                    request.clause_id is None and request.decision is None,
                    "ACCEPTANCE_ACTION_FIELDS",
                )
                check(len(state["clauses"]) < 64, "ACCEPTANCE_CLAUSE_LIMIT")
                state["clauses"].append(
                    clause(
                        f"c{len(state['clauses']) + 1}",
                        request.text or "",
                        "SUGGESTED_ONLY",
                        "manual:operator",
                    )
                )
            else:
                target = next((c for c in state["clauses"] if c["id"] == request.clause_id), None)
                check(
                    target is not None and request.decision is not None, "ACCEPTANCE_CLAUSE_INVALID"
                )
                assert target is not None
                unchanged_explicit = (
                    target["origin"]["source"] == "EXPLICIT_IN_PROMPT"
                    and request.text == target["origin"]["text"]
                )
                target.update(
                    text=request.text,
                    decision=request.decision,
                    reviewed_at=now(),
                    review_reason=request.reason,
                )
                target["source"] = (
                    "EXPLICIT_IN_PROMPT"
                    if unchanged_explicit
                    else "USER_APPROVED_ADDITION"
                    if request.decision == "APPROVED"
                    else "AMBIGUOUS"
                    if target["origin"]["source"] == "AMBIGUOUS"
                    else "SUGGESTED_ONLY"
                )
        else:
            check(
                request.clause_id is None and request.text is None and request.decision is None,
                "ACCEPTANCE_ACTION_FIELDS",
            )
            check(
                request.acknowledgement == "SCOPE_ONLY_NO_EXECUTION",
                "ACCEPTANCE_CONFIRMATION_REQUIRED",
            )
            if action == "CONFIRM":
                check(
                    any(c["decision"] == "APPROVED" for c in state["clauses"]),
                    "ACCEPTANCE_EMPTY_SCOPE",
                )
                state.update(status="CONFIRMED", confirmed_at=now())
            elif action == "FREEZE":
                state.update(status="FROZEN", frozen_at=now())
            else:
                state.update(
                    status="DRAFT",
                    version=state["version"] + 1,
                    confirmed_at=None,
                    frozen_at=None,
                    parent_frozen_digest=events[-1]["digest"],
                )
                for item in state["clauses"]:
                    item.update(decision="PENDING", reviewed_at=None, review_reason=None)
        return append(root, state, events, request, action)


def read(plan_id: str) -> dict[str, Any]:
    with locked() as root:
        events = history(root, plan_id)
        state = events[-1]["state"]
        # Historical scope is still readable if the separately stored snapshot later breaks.
        try:
            checked_snapshot(state["snapshot"]["identity"], state["snapshot"]["content_digest"])
            binding = "INTACT"
        except WorkbenchAPIError:
            binding = "UNAVAILABLE_OR_CHANGED"
        return {"current": events[-1], "history": events, "snapshot_binding": binding}


def listing() -> dict[str, Any]:
    with locked() as root:
        items = []
        for folder in sorted(root.iterdir()):
            if folder.name.startswith("."):
                continue
            events = history(root, folder.name)
            current = events[-1]
            items.append(
                {
                    "plan_id": folder.name,
                    "version": current["state"]["version"],
                    "status": current["state"]["status"],
                    "at": current["at"],
                    "snapshot_identity": current["state"]["snapshot"]["identity"],
                }
            )
        return {"items": items}
