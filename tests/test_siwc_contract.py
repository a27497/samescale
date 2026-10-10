from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from harnesslab.local_execution.siwc_contract import (
    APP_NAME,
    RESOURCE,
    UNSUPPORTED_FIELDS,
    AppServerConversation,
    OfflineOAuthIssuer,
    OfflineSiwcSession,
    SiwcDenied,
    SyntheticGrant,
    host_id,
    prepare_responses,
    validate_responses,
)
from harnesslab.local_execution.subscription_protocol import OfflineSubscriptionController

NOW = 2_000_000_000


def session(tmp_path: Path) -> tuple[OfflineSiwcSession, OfflineOAuthIssuer]:
    issuer = OfflineOAuthIssuer()
    return OfflineSiwcSession(host_id(tmp_path / "private"), issuer), issuer


def login(s: OfflineSiwcSession, issuer: OfflineOAuthIssuer) -> SyntheticGrant:
    p = s.begin()
    cb = issuer.authorize(p)
    g = issuer.exchange(cb, p, NOW)
    s.complete(cb, NOW, grant=g)
    return g


def response(**changes: Any) -> dict[str, Any]:
    return {
        "model": "offline-model",
        "stream": True,
        "store": False,
        "input": [{"role": "user", "content": "offline task"}],
        "tools": [
            {
                "type": "namespace",
                "name": "functions",
                "tools": [{"type": "custom", "name": "apply_patch"}],
            }
        ],
        **changes,
    }


def test_registration_returning_account_and_host_are_separate(tmp_path: Path) -> None:
    s, issuer = session(tmp_path)
    first = s.begin()
    assert first.parameters["client_id"] == "dynamic_agent_client"
    assert first.parameters["agent_name_hint"] == APP_NAME
    assert first.parameters["resource"] == RESOURCE
    assert first.parameters["code_challenge_method"] == "S256"
    cb = issuer.authorize(first)
    s.complete(cb, NOW)
    client = cb["client_id"]
    p = s.begin(
        client=client, subject="offline-subject", redirect="http://127.0.0.1:54321/auth/callback"
    )
    assert p.parameters["client_id"] == client and "agent_name_hint" not in p.parameters
    assert p.parameters["ext_agent_host_id"] == first.parameters["ext_agent_host_id"]
    assert p.parameters["state"] != first.parameters["state"]
    assert p.parameters["nonce"] != first.parameters["nonce"]
    assert p.verifier != first.verifier
    cb = issuer.authorize(p)
    g = issuer.exchange(cb, p, NOW)
    cb.pop("client_id")  # Allowed only for a known returning registration.
    s.complete(cb, NOW, grant=g)
    assert issuer.exchanges == 2
    assert host_id(tmp_path / "private") == s.host


@pytest.mark.parametrize(
    "fault",
    ["state", "consent", "missing_client", "dynamic_client", "pkce", "redirect", "resource"],
)
def test_callback_failures_are_consumed_without_replay(tmp_path: Path, fault: str) -> None:
    s, issuer = session(tmp_path)
    p = s.begin()
    cb = issuer.authorize(p)
    if fault == "state":
        cb["state"] = "invalid"
    if fault == "consent":
        cb["error"] = "access_denied"
    if fault == "missing_client":
        cb.pop("client_id")
    if fault == "dynamic_client":
        cb["client_id"] = "dynamic_agent_client"
    if fault == "pkce":
        p.verifier = "wrong"
    if fault == "redirect":
        p.parameters["redirect_uri"] = "http://127.0.0.1:1456/auth/callback"
    if fault == "resource":
        issuer._codes[cb["code"]]["resource"] = "https://invalid.invalid"
    with pytest.raises(SiwcDenied):
        s.complete(cb, NOW)
    with pytest.raises(SiwcDenied, match="AUTH_ATTEMPT_CONSUMED"):
        s.complete(cb, NOW)
    with pytest.raises(SiwcDenied):
        s.pin(NOW, seconds=20)


@pytest.mark.parametrize(
    "uri",
    [
        "http://localhost:1455/auth/callback",
        "https://127.0.0.1:1455/auth/callback",
        "http://127.0.0.1:1455/callback",
        "http://user@127.0.0.1:1455/auth/callback",
        "http://127.0.0.1/auth/callback",
        "http://127.0.0.1:1455/auth/callback?token=x",
    ],
)
def test_only_exact_loopback_callback_contract(tmp_path: Path, uri: str) -> None:
    s, _ = session(tmp_path)
    with pytest.raises(SiwcDenied):
        s.begin(redirect=uri)


@pytest.mark.parametrize(
    "fault",
    [
        "signature",
        "issuer",
        "audience",
        "nonce",
        "expired",
        "subject",
        "scope",
        "expiry_bool",
        "credential_source",
        "non_synthetic",
    ],
)
def test_signed_identity_and_grant_must_both_validate(tmp_path: Path, fault: str) -> None:
    s, issuer = session(tmp_path)
    p = s.begin()
    cb = issuer.authorize(p)
    g = issuer.exchange(cb, p, NOW)
    if fault == "signature":
        g.signature = "invalid"
    if fault == "issuer":
        g.claims["iss"] = "https://invalid.invalid"
    if fault == "audience":
        g.claims["aud"] = "oaiapp_other"
    if fault == "nonce":
        g.claims["nonce"] = "wrong"
    if fault == "expired":
        g.claims["exp"] = NOW
    if fault == "subject":
        g.claims["sub"] = "another-account"
    if fault == "scope":
        g.scope = "openid profile email"
    if fault == "expiry_bool":
        g.expires_in = True
    if fault == "credential_source":
        g.source = "LIVE_OAUTH"
    if fault == "non_synthetic":
        g.access_token = "development-placeholder-not-accepted"
    if fault in {"issuer", "audience", "nonce", "expired", "subject"}:
        g.signature = issuer._sign(g.claims)
    with pytest.raises(SiwcDenied):
        s.complete(cb, NOW, grant=g)
    assert s.safe_receipt()["scope_validation"] == "NOT_VALIDATED"


def test_returning_identity_cannot_replace_active_registration(tmp_path: Path) -> None:
    s, issuer = session(tmp_path)
    good = login(s, issuer)
    p = s.begin(client=good.client_id, subject=good.subject)
    cb = issuer.authorize(p)
    bad = issuer.exchange(cb, p, NOW)
    bad.subject = bad.claims["sub"] = "other-subject"
    bad.signature = issuer._sign(bad.claims)
    with pytest.raises(SiwcDenied, match="ACCOUNT_MISMATCH"):
        s.complete(cb, NOW, grant=bad)
    s.pin(NOW, seconds=20)
    assert s.headers_for_double(NOW)["Authorization"].endswith(good.access_token)


def test_vm_import_keeps_distinct_stable_host_and_client(tmp_path: Path) -> None:
    s, issuer = session(tmp_path / "laptop")
    grant = login(s, issuer)
    vm_host = host_id(tmp_path / "vm")
    vm = OfflineSiwcSession(vm_host, issuer)
    vm.import_synthetic_registration(grant, NOW)
    assert vm.host != s.host and host_id(tmp_path / "vm") == vm_host
    p = vm.begin(client=grant.client_id, subject=grant.subject)
    assert p.parameters["ext_agent_host_id"] == vm_host
    assert p.parameters["client_id"] == grant.client_id
    assert s.host == host_id(tmp_path / "laptop/private")


def test_token_rotation_and_revocation_only_between_authorizations(tmp_path: Path) -> None:
    s, issuer = session(tmp_path)
    original = login(s, issuer)
    with pytest.raises(SiwcDenied, match="REFRESH_TOO_EARLY"):
        s.renew_between_authorizations(NOW + 1)
    s.renew_between_authorizations(NOW + 3000)
    assert issuer.refreshes == 1
    with pytest.raises(SiwcDenied, match="INVALID_REFRESH_GRANT"):
        issuer.refresh(original, NOW + 3000)
    s.sign_out()
    assert issuer.revocations == 1
    with pytest.raises(SiwcDenied):
        s.pin(NOW + 3000, seconds=20)
    returning = s.begin(client=original.client_id, subject=original.subject)
    assert returning.parameters["client_id"] == original.client_id
    assert "id_token_hint" not in returning.parameters


def test_refresh_serializes_rotating_grant(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    s, issuer = session(tmp_path)
    login(s, issuer)

    def renew(_: int) -> bool:
        try:
            s.renew_between_authorizations(NOW + 3000)
            return True
        except SiwcDenied:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(renew, range(2))) == 1
    assert issuer.refreshes == 1


def test_controller_rejects_upstream_credential_reflection_before_sse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = OfflineSubscriptionController(
        {
            "run_id": "offline",
            "authorization_digest": "sha256:" + "1" * 64,
            "model": "offline-model",
            "max_requests": 2,
            "wall_time_seconds": 20,
            "scenario": "solve",
            "siwc_stub": True,
            "siwc_host_id": host_id(tmp_path / "private"),
        },
        tmp_path / "receipt.json",
    )

    def reflect(item: object, headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
        return 200, {"error": headers["Authorization"]}

    monkeypatch.setattr(c, "_offline_transport", reflect)
    status, body = c.response(response())
    assert status == 403 and body == {"error": "SIWC_CREDENTIAL_REFLECTION_DENIED"}
    assert c.state["requests_consumed"] == 1
    assert "offline-siwc-access-" not in (tmp_path / "receipt.json").read_text()


def test_transient_refresh_preserves_registration_and_invalid_refresh_clears_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s, issuer = session(tmp_path)
    g = login(s, issuer)

    def transient(*args: object) -> SyntheticGrant:
        raise SiwcDenied("OFFLINE_TRANSIENT")

    with monkeypatch.context() as m:
        m.setattr(issuer, "refresh", transient)
        with pytest.raises(SiwcDenied):
            s.renew_between_authorizations(NOW + 3000)
    issuer.revoke(g)
    with pytest.raises(SiwcDenied, match="INVALID_REFRESH_GRANT"):
        s.renew_between_authorizations(NOW + 3000)
    assert s.safe_receipt()["scope_validation"] == "NOT_VALIDATED"


def test_attempt_pins_auth_without_refresh_switch_logout_or_retry(tmp_path: Path) -> None:
    s, issuer = session(tmp_path)
    g = login(s, issuer)
    s.pin(NOW, seconds=20)
    for action in (
        s.begin,
        s.sign_out,
        lambda: s.renew_between_authorizations(NOW + 3000),
        lambda: s.import_synthetic_registration(g, NOW),
    ):
        with pytest.raises(SiwcDenied, match="AUTH_LIFECYCLE_FROZEN"):
            action()
    with pytest.raises(SiwcDenied, match="AUTH_EXPIRED"):
        s.headers_for_double(NOW + 3600)
    s.stop()
    with pytest.raises(SiwcDenied):
        s.headers_for_double(NOW)
    assert issuer.refreshes == issuer.revocations == 0
    safe = json.dumps(s.safe_receipt()) + repr(s) + repr(g)
    assert all(t not in safe for t in (g.access_token, g.refresh_token, g.id_token))


def test_credentials_near_expiry_or_reflected_fail_closed(tmp_path: Path) -> None:
    s, issuer = session(tmp_path)
    g = login(s, issuer)
    with pytest.raises(SiwcDenied, match="AUTH_EXPIRES_DURING_ATTEMPT"):
        s.pin(NOW + 3590, seconds=20)
    for token in (g.access_token, g.refresh_token, g.id_token):
        with pytest.raises(SiwcDenied, match="CREDENTIAL_REFLECTION_DENIED"):
            s.reject_credential_reflection({"error": "upstream " + token})


def test_host_storage_never_reads_development_or_subject_credentials(tmp_path: Path) -> None:
    root = tmp_path / ".codex"
    root.mkdir()
    (root / "host-id").write_text("private-sentinel")
    with pytest.raises(SiwcDenied, match="PRIVATE_STORAGE_DENIED"):
        host_id(root)
    link = tmp_path / "link"
    link.symlink_to(root)
    with pytest.raises(SiwcDenied):
        host_id(link)
    private = tmp_path / "private"
    private.mkdir(mode=0o777)
    private.chmod(0o777)
    with pytest.raises(SiwcDenied):
        host_id(private)


@pytest.mark.parametrize("field", sorted(UNSUPPORTED_FIELDS))
def test_official_unsupported_responses_fields_are_denied(field: str) -> None:
    with pytest.raises(SiwcDenied, match="SIWC_UNSUPPORTED_FIELDS"):
        validate_responses(response(**{field: None}), "offline-model")


@pytest.mark.parametrize(
    "change",
    [
        {"store": True},
        {"stream": False},
        {"input": "missing context"},
        {"input": [{"type": "message", "role": "system"}]},
        {"tools": [{"type": "tool_search"}]},
        {"tools": [{"type": "programmatic_tool_calling"}]},
        {"tools": [{"type": "function", "name": "bare"}]},
        {
            "input": [
                {
                    "type": "additional_tools",
                    "tools": [{"type": "namespace", "tools": [{"type": "tool_search"}]}],
                }
            ]
        },
    ],
)
def test_responses_context_and_tools_do_not_bypass_preview_contract(change: dict[str, Any]) -> None:
    with pytest.raises(SiwcDenied):
        validate_responses(response(**change), "offline-model")


def test_offline_controller_binds_oauth_and_requests_without_export(tmp_path: Path) -> None:
    import time

    c = OfflineSubscriptionController(
        {
            "run_id": "offline",
            "authorization_digest": "sha256:" + "1" * 64,
            "model": "offline-model",
            "max_requests": 2,
            "wall_time_seconds": 20,
            "scenario": "solve",
            "siwc_stub": True,
            "siwc_host_id": host_id(tmp_path / "private"),
        },
        tmp_path / "receipt.json",
    )
    assert c.response(response())[0] == 200
    assert c.response(response())[0] == 200
    assert c.response(response())[0] == 403
    receipt = json.loads((tmp_path / "receipt.json").read_text())
    assert receipt["siwc"]["authorization_code_exchanges"] == 1
    assert receipt["siwc"]["refreshes"] == receipt["siwc"]["live_oauth_calls"] == 0
    assert receipt["requests_consumed"] == 2
    assert c.deadline > time.monotonic()
    assert "offline-siwc-access-" not in json.dumps(receipt)


def test_native_attribution_is_explicitly_omitted_without_context_or_limits_changes() -> None:
    original = response(client_metadata={"untrusted": "native attribution"})
    prepared = prepare_responses(original, "offline-model")
    assert prepared == {k: v for k, v in original.items() if k != "client_metadata"}
    assert original["client_metadata"] == {"untrusted": "native attribution"}
    assert prepared["input"] is original["input"] and prepared["tools"] is original["tools"]
    with pytest.raises(SiwcDenied):
        prepare_responses(response(client_metadata="invalid"), "offline-model")
    with pytest.raises(SiwcDenied):
        prepare_responses(response(client_metadata={}, max_output_tokens=100), "offline-model")


def test_same_subject_registrations_keep_their_client_boundaries(tmp_path: Path) -> None:
    s, issuer = session(tmp_path)
    first = login(s, issuer)
    second = login(s, issuer)
    assert first.subject == second.subject and first.client_id != second.client_id
    s.sign_out()
    assert (first.subject, first.client_id) in s._credentials
    assert (second.subject, second.client_id) not in s._credentials
    p = s.begin(client=first.client_id, subject=first.subject)
    cb = issuer.authorize(p)
    cb["client_id"] = second.client_id
    with pytest.raises(SiwcDenied, match="CLIENT_MAPPING_DENIED"):
        s.complete(cb, NOW)


@pytest.mark.parametrize("status", ["completed", "failed", "interrupted"])
def test_app_server_order_and_terminal_status_do_not_grant_another_turn(status: str) -> None:
    c = AppServerConversation()
    with pytest.raises(SiwcDenied):
        c.start_turn("t", "task")
    init = c.initialize()
    assert init["params"]["clientInfo"]["name"] == APP_NAME
    c.acknowledge({"id": 1, "result": {}})
    with pytest.raises(SiwcDenied):
        c.initialize()
    c.start_turn("thread-1", "task")
    assert c.complete(status) is (status == "completed")
    with pytest.raises(SiwcDenied):
        c.start_turn("thread-1", "retry")


def test_app_server_interrupt_keeps_single_turn() -> None:
    c = AppServerConversation()
    c.initialize()
    c.acknowledge({"id": 1, "result": {}})
    c.start_turn("thread", "task")
    assert c.interrupt("turn")["params"] == {"threadId": "thread", "turnId": "turn"}
    with pytest.raises(SiwcDenied):
        c.complete("completed")
    with pytest.raises(SiwcDenied):
        c.start_turn("thread", "retry")


@pytest.mark.parametrize(
    "payload", [b"{", b"[]", b'{"model":"offline-model","stream":true,"tools":[null]}']
)
def test_malformed_http_request_is_counted_once_even_after_controller_entry(
    tmp_path: Path, payload: bytes
) -> None:
    from io import BytesIO
    from types import SimpleNamespace

    from harnesslab.local_execution.subscription_protocol import _Handler

    c = OfflineSubscriptionController(
        {
            "run_id": "offline",
            "authorization_digest": "sha256:" + "1" * 64,
            "model": "offline-model",
            "max_requests": 2,
            "wall_time_seconds": 20,
            "scenario": "solve",
        },
        tmp_path / "receipt.json",
    )
    handler = _Handler.__new__(_Handler)
    handler.server = SimpleNamespace(controller=c)  # type: ignore[assignment]
    handler.headers = {"Content-Length": str(len(payload))}  # type: ignore[assignment]
    handler.path = "/v1/responses"
    handler.rfile, handler.wfile = BytesIO(payload), BytesIO()
    handler.send_response = lambda *args: None  # type: ignore[method-assign]
    handler.send_header = lambda *args: None  # type: ignore[method-assign]
    handler.end_headers = lambda: None  # type: ignore[method-assign]
    handler.do_POST()
    assert c.state["requests_received"] == c.state["requests_denied"] == 1
    assert json.loads(handler.wfile.getvalue()) == {"error": "MALFORMED_REQUEST"}
