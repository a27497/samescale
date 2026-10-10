"""SIWC contract double, NOT an OAuth client or OpenAI JWT verifier.

Only locally issued, explicitly synthetic credentials are accepted. No network,
browser, development auth-file reader or live token import exists in this module.
The controller may use these private objects; Subject receives neither tokens nor
OAuth messages. Official registration/lifecycle semantics are exercised offline.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

APP_NAME = "SameScale"
RESOURCE = "https://api.openai.com/v1"
ISSUER = "https://auth.openai.com"
SCOPES = frozenset(
    {"openid", "profile", "email", "offline_access", "resource.invoke", "chatgpt.tokens.use.direct"}
)
UNSUPPORTED_FIELDS = frozenset(
    {
        "background",
        "conversation",
        "max_output_tokens",
        "max_tool_calls",
        "metadata",
        "moderation",
        "multi_agent",
        "prompt",
        "prompt_cache_retention",
        "safety_identifier",
        "temperature",
        "top_logprobs",
        "top_p",
        "truncation",
        "user",
        "previous_response_id",
    }
)


class SiwcDenied(ValueError):
    """Bounded machine codes only; never interpolate OAuth or upstream values."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise SiwcDenied(code)


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


def _client(value: str) -> bool:
    return bool(re.fullmatch(r"oaiapp_[A-Za-z0-9_-]{1,100}", value))


def _private_root(root: Path) -> None:
    _require(root.is_absolute(), "PRIVATE_STORAGE_DENIED")
    for p in (root, *root.parents):
        _require(
            not p.is_symlink() and p.name not in {".codex", "workspace", "verifier"},
            "PRIVATE_STORAGE_DENIED",
        )
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    s = root.stat()
    _require(s.st_uid == os.getuid() and s.st_mode & 0o077 == 0, "PRIVATE_STORAGE_DENIED")


def host_id(root: Path) -> str:
    """Persist an app-defined, non-secret UUID host ID; never inspect CLI storage."""
    _private_root(root)
    path = root / "host-id"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as stream:
            value = stream.read(100)
        stat = path.stat()
        _require(stat.st_uid == os.getuid() and stat.st_mode & 0o077 == 0, "HOST_ID_DENIED")
    else:
        value = "urn:uuid:" + str(uuid4())
        with os.fdopen(fd, "w") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
    try:
        parsed = UUID(value.removeprefix("urn:uuid:"))
        _require(value == "urn:uuid:" + str(parsed) and parsed.version == 4, "HOST_ID_DENIED")
    except ValueError:
        raise SiwcDenied("HOST_ID_DENIED") from None
    return value


@dataclass(repr=False)
class PendingAuthorization:
    parameters: dict[str, str]
    verifier: str
    selected_subject: str | None
    consumed: bool = False


@dataclass(repr=False)
class SyntheticGrant:
    client_id: str
    subject: str
    access_token: str
    refresh_token: str
    id_token: str
    claims: dict[str, Any]
    signature: str
    scope: str
    expires_in: int
    saved_at: int
    earliest_refresh_at: int
    refresh_expires_at: int
    generation: int = 1
    source: str = "OFFLINE_OAUTH_STUB"


class OfflineOAuthIssuer:
    """In-memory OAuth/JWKS stand-in. HMAC is synthetic, never OpenAI signature proof."""

    def __init__(self) -> None:
        self._key = secrets.token_bytes(32)
        self._codes: dict[str, dict[str, str]] = {}
        self._refreshes: dict[str, SyntheticGrant] = {}
        self.exchanges = self.refreshes = self.revocations = 0

    def authorize(self, pending: PendingAuthorization) -> dict[str, str]:
        code = "offline-siwc-code-" + secrets.token_hex(24)
        params = dict(pending.parameters)
        if params["client_id"] == "dynamic_agent_client":
            params["client_id"] = "oaiapp_offline_" + secrets.token_hex(12)
        self._codes[code] = params
        return {"code": code, "state": params["state"], "client_id": params["client_id"]}

    def _sign(self, claims: dict[str, Any]) -> str:
        return hmac.new(
            self._key, json.dumps(claims, sort_keys=True).encode(), "sha256"
        ).hexdigest()

    def _issue(
        self, client: str, nonce: str, subject: str, now: int, generation: int = 1
    ) -> SyntheticGrant:
        claims = {"iss": ISSUER, "aud": client, "sub": subject, "nonce": nonce, "exp": now + 3600}
        grant = SyntheticGrant(
            client,
            subject,
            "offline-siwc-access-" + secrets.token_hex(24),
            "offline-siwc-refresh-" + secrets.token_hex(24),
            "offline-siwc-id-" + secrets.token_hex(24),
            claims,
            self._sign(claims),
            " ".join(sorted(SCOPES)),
            3600,
            now,
            now + 3000,
            now + 30 * 86400,
            generation,
        )
        self._refreshes[grant.refresh_token] = grant
        return grant

    def exchange(
        self, callback: dict[str, str], pending: PendingAuthorization, now: int
    ) -> SyntheticGrant:
        params = self._codes.pop(callback["code"], None)
        _require(params is not None, "INVALID_GRANT")
        assert params is not None
        _require(
            params["client_id"] == callback["client_id"]
            and params["redirect_uri"] == pending.parameters["redirect_uri"]
            and params["resource"] == RESOURCE
            and params["code_challenge"] == _challenge(pending.verifier),
            "CODE_EXCHANGE_DENIED",
        )
        self.exchanges += 1
        return self._issue(
            callback["client_id"],
            params["nonce"],
            pending.selected_subject or "offline-subject",
            now,
        )

    def validate(self, grant: SyntheticGrant, pending: PendingAuthorization, now: int) -> None:
        c = grant.claims
        _require(
            grant.source == "OFFLINE_OAUTH_STUB"
            and all(
                v.startswith("offline-siwc-")
                for v in (grant.access_token, grant.refresh_token, grant.id_token)
            ),
            "NON_SYNTHETIC_CREDENTIAL_DENIED",
        )
        _require(hmac.compare_digest(grant.signature, self._sign(c)), "ID_SIGNATURE_DENIED")
        _require(
            c.get("iss") == ISSUER
            and c.get("aud") == grant.client_id
            and c.get("nonce") == pending.parameters["nonce"]
            and type(c.get("exp")) is int
            and c["exp"] > now
            and c.get("sub") == grant.subject
            and bool(grant.subject),
            "ID_CLAIMS_DENIED",
        )
        _require(
            pending.selected_subject is None or pending.selected_subject == grant.subject,
            "ACCOUNT_MISMATCH",
        )
        _require(set(grant.scope.split()) >= SCOPES, "PLAN_SCOPE_DENIED")
        _require(
            type(grant.expires_in) is int
            and 0 < grant.expires_in <= 3600
            and grant.saved_at <= now < grant.saved_at + grant.expires_in
            and grant.earliest_refresh_at >= grant.saved_at
            and grant.refresh_expires_at > now,
            "TOKEN_LIFETIME_DENIED",
        )

    def refresh(self, grant: SyntheticGrant, now: int) -> SyntheticGrant:
        _require(_client(grant.client_id) and now >= grant.earliest_refresh_at, "REFRESH_TOO_EARLY")
        previous = self._refreshes.pop(grant.refresh_token, None)
        _require(previous is grant and now < grant.refresh_expires_at, "INVALID_REFRESH_GRANT")
        self.refreshes += 1
        return self._issue(
            grant.client_id, grant.claims["nonce"], grant.subject, now, grant.generation + 1
        )

    def revoke(self, grant: SyntheticGrant) -> None:
        self._refreshes.pop(grant.refresh_token, None)
        self.revocations += 1


class OfflineSiwcSession:
    def __init__(self, host: str, issuer: OfflineOAuthIssuer) -> None:
        _require(host.startswith("urn:uuid:") and UUID(host[9:]).version == 4, "HOST_ID_DENIED")
        self.host = host
        self._issuer = issuer
        self._grant: SyntheticGrant | None = None
        self._pending: PendingAuthorization | None = None
        self._pinned = False
        self._closed = False
        self._credentials: dict[tuple[str, str], SyntheticGrant] = {}
        self._registrations: set[tuple[str, str]] = set()
        self._lifecycle_lock = threading.Lock()

    def begin(
        self,
        *,
        client: str | None = None,
        subject: str | None = None,
        redirect: str = "http://127.0.0.1:1455/auth/callback",
    ) -> PendingAuthorization:
        _require(not self._pinned, "AUTH_LIFECYCLE_FROZEN")
        u = urlsplit(redirect)
        _require(
            u.scheme == "http"
            and u.hostname == "127.0.0.1"
            and u.path == "/auth/callback"
            and u.port is not None
            and not u.username
            and not u.password
            and not u.query
            and not u.fragment,
            "CALLBACK_URI_DENIED",
        )
        _require(
            client is None or (_client(client) and (subject, client) in self._registrations),
            "CLIENT_MAPPING_DENIED",
        )
        verifier = secrets.token_urlsafe(48)
        params = {
            "client_id": client or "dynamic_agent_client",
            "ext_agent_host_id": self.host,
            "response_type": "code",
            "redirect_uri": redirect,
            "scope": " ".join(sorted(SCOPES)),
            "resource": RESOURCE,
            "state": secrets.token_urlsafe(32),
            "nonce": secrets.token_urlsafe(32),
            "code_challenge_method": "S256",
            "code_challenge": _challenge(verifier),
        }
        if client is None:
            params["agent_name_hint"] = APP_NAME
        self._pending = PendingAuthorization(params, verifier, subject)
        return self._pending

    def complete(
        self, callback: dict[str, str], now: int, *, grant: SyntheticGrant | None = None
    ) -> None:
        p = self._pending
        _require(p is not None and not p.consumed, "AUTH_ATTEMPT_CONSUMED")
        assert p is not None
        p.consumed = True  # Even a failed callback cannot be replayed.
        _require(
            hmac.compare_digest(callback.get("state", ""), p.parameters["state"]),
            "OAUTH_STATE_DENIED",
        )
        _require("error" not in callback, "OAUTH_CONSENT_DENIED")
        client = callback.get("client_id", p.parameters["client_id"])
        _require(_client(client), "ISSUED_CLIENT_REQUIRED")
        _require(
            p.parameters["client_id"] in {"dynamic_agent_client", client}, "CLIENT_MAPPING_DENIED"
        )
        callback = {**callback, "client_id": client}
        _require(bool(callback.get("code")), "AUTH_CODE_REQUIRED")
        selected = grant or self._issuer.exchange(callback, p, now)
        _require(selected.client_id == client, "CLIENT_MAPPING_DENIED")
        self._issuer.validate(selected, p, now)
        self._credentials[(selected.subject, client)] = selected
        self._registrations.add((selected.subject, client))
        self._grant = selected
        self._closed = False

    def pin(self, now: int, *, seconds: int) -> None:
        _require(
            self._grant is not None and not self._pinned and not self._closed, "AUTH_NOT_AVAILABLE"
        )
        assert self._grant is not None
        _require(
            now + seconds < self._grant.saved_at + self._grant.expires_in,
            "AUTH_EXPIRES_DURING_ATTEMPT",
        )
        _require(set(self._grant.scope.split()) >= SCOPES, "PLAN_SCOPE_DENIED")
        self._pinned = True

    def headers_for_double(self, now: int) -> dict[str, str]:
        _require(
            self._pinned and not self._closed and self._grant is not None, "AUTH_NOT_AVAILABLE"
        )
        assert self._grant is not None
        _require(now < self._grant.saved_at + self._grant.expires_in, "AUTH_EXPIRED")
        return {"Authorization": "Bearer " + self._grant.access_token, "originator": APP_NAME}

    def stop(self) -> None:
        self._closed = True  # Never refresh/retry within or after this attempt.

    def renew_between_authorizations(self, now: int) -> None:
        with self._lifecycle_lock:
            _require(not self._pinned and self._grant is not None, "AUTH_LIFECYCLE_FROZEN")
            assert self._grant is not None
            previous = self._grant
            try:
                replacement = self._issuer.refresh(previous, now)
            except SiwcDenied as exc:
                if str(exc) == "INVALID_REFRESH_GRANT":
                    self._credentials.pop((previous.subject, previous.client_id), None)
                    self._grant = None
                raise
            self._credentials[(replacement.subject, replacement.client_id)] = replacement
            self._grant = replacement

    def sign_out(self) -> None:
        _require(not self._pinned, "AUTH_LIFECYCLE_FROZEN")
        if self._grant is not None:
            self._issuer.revoke(self._grant)
            self._credentials.pop((self._grant.subject, self._grant.client_id), None)
        self._grant = None
        self._closed = True

    def import_synthetic_registration(self, grant: SyntheticGrant, now: int) -> None:
        """Model VM transfer in memory; keep this VM's previously persisted host ID."""
        _require(not self._pinned, "AUTH_LIFECYCLE_FROZEN")
        p = PendingAuthorization({"nonce": grant.claims["nonce"]}, "", grant.subject)
        _require(_client(grant.client_id), "ISSUED_CLIENT_REQUIRED")
        self._issuer.validate(grant, p, now)
        self._credentials[(grant.subject, grant.client_id)] = grant
        self._registrations.add((grant.subject, grant.client_id))
        self._grant = grant

    def reject_credential_reflection(self, payload: object) -> None:
        encoded = json.dumps(payload)
        _require(
            not any(
                token in encoded
                for g in self._credentials.values()
                for token in (g.access_token, g.refresh_token, g.id_token)
            ),
            "CREDENTIAL_REFLECTION_DENIED",
        )

    def safe_receipt(self) -> dict[str, Any]:
        return {
            "source": "OFFLINE_OAUTH_STUB",
            "app_name": APP_NAME,
            "host_id_present": True,
            "identity_validation": "SYNTHETIC_SIGNATURE_ONLY_NOT_OPENAI_JWKS",
            "scope_validation": "SYNTHETIC_GRANTED" if self._grant else "NOT_VALIDATED",
            "credential_location": "CONTROLLER_MEMORY_ONLY",
            "authorization_code_exchanges": self._issuer.exchanges,
            "refreshes": self._issuer.refreshes,
            "revocations": self._issuer.revocations,
            "live_oauth_calls": 0,
            "request_normalization": "OMIT_NATIVE_CLIENT_METADATA_USE_TRUSTED_ORIGINATOR",
        }


def validate_responses(request: dict[str, Any], model: str) -> None:
    _require(
        request.get("model") == model
        and request.get("store") is False
        and request.get("stream") is True
        and isinstance(request.get("input"), list),
        "SIWC_RESPONSES_DENIED",
    )
    _require(not UNSUPPORTED_FIELDS.intersection(request), "SIWC_UNSUPPORTED_FIELDS")
    _require(
        set(request)
        <= {
            "model",
            "store",
            "stream",
            "input",
            "instructions",
            "tools",
            "tool_choice",
            "parallel_tool_calls",
            "reasoning",
            "text",
            "include",
            "prompt_cache_key",
            "service_tier",
        },
        "SIWC_UNSUPPORTED_FIELDS",
    )
    declared = request.get("tools", [])
    _require(isinstance(declared, list), "SIWC_TOOLS_DENIED")
    for t in declared:
        _require(
            isinstance(t, dict) and t.get("type") in {"namespace", "web_search"},
            "SIWC_TOOLS_DENIED",
        )
        if t.get("type") == "namespace":
            _require(
                isinstance(t.get("tools"), list)
                and all(
                    isinstance(n, dict) and n.get("type") in {"function", "custom"}
                    for n in t["tools"]
                ),
                "SIWC_TOOLS_DENIED",
            )
    for item in request["input"]:
        _require(isinstance(item, dict) and item.get("role") != "system", "SIWC_INPUT_DENIED")
        if item.get("type") == "additional_tools":
            _require(
                isinstance(item.get("tools"), list)
                and all(
                    isinstance(t, dict) and t.get("type") in {"namespace", "function", "custom"}
                    for t in item["tools"]
                ),
                "SIWC_TOOLS_DENIED",
            )
            for t in item["tools"]:
                if t.get("type") == "namespace":
                    _require(
                        isinstance(t.get("tools"), list)
                        and all(
                            isinstance(n, dict) and n.get("type") in {"function", "custom"}
                            for n in t["tools"]
                        ),
                        "SIWC_TOOLS_DENIED",
                    )
        _require(item.get("type") not in {"input_audio", "input_video"}, "SIWC_INPUT_DENIED")


def prepare_responses(request: dict[str, Any], model: str) -> dict[str, Any]:
    """Explicit adaptation of frozen CLI attribution; no context/limits/tool rewriting.

    client_metadata is native CLI attribution, absent from the cited SIWC contract.
    Do not forward or trust it. The controller supplies its fixed originator instead.
    Every other unsupported/unknown field remains a denial, including metadata.
    """
    public = dict(request)
    if "client_metadata" in public:
        _require(isinstance(public["client_metadata"], dict), "SIWC_UNSUPPORTED_FIELDS")
        public.pop("client_metadata")
    validate_responses(public, model)
    return public


@dataclass
class AppServerConversation:
    """Offline JSONL protocol sequencing; no subprocess or RPC transport."""

    initialized: bool = False
    acknowledged: bool = False
    turn_consumed: bool = False
    terminal: str | None = None
    thread_id: str | None = None
    _initialize_sent: bool = field(default=False, repr=False)

    def initialize(self) -> dict[str, Any]:
        _require(not self._initialize_sent, "INITIALIZE_ONCE")
        self._initialize_sent = True
        return {
            "method": "initialize",
            "id": 1,
            "params": {
                "clientInfo": {"name": APP_NAME, "title": APP_NAME, "version": "phase26-offline"}
            },
        }

    def acknowledge(self, result: dict[str, Any]) -> dict[str, str]:
        _require(
            self._initialize_sent
            and not self.acknowledged
            and result.get("id") == 1
            and isinstance(result.get("result"), dict)
            and "error" not in result,
            "INITIALIZE_FAILED",
        )
        self.initialized = self.acknowledged = True
        return {"method": "initialized"}

    def start_turn(self, thread: str, text: str) -> dict[str, Any]:
        _require(self.acknowledged and not self.turn_consumed and bool(thread), "TURN_ONCE")
        self.thread_id, self.turn_consumed = thread, True
        return {
            "method": "turn/start",
            "id": 2,
            "params": {"threadId": thread, "input": [{"type": "text", "text": text}]},
        }

    def interrupt(self, turn_id: str) -> dict[str, Any]:
        _require(self.turn_consumed and self.terminal is None and bool(turn_id), "TURN_NOT_ACTIVE")
        self.terminal = "interrupted"
        return {
            "method": "turn/interrupt",
            "id": 3,
            "params": {"threadId": self.thread_id, "turnId": turn_id},
        }

    def complete(self, status: str) -> bool:
        _require(
            self.turn_consumed
            and self.terminal is None
            and status in {"completed", "failed", "interrupted"},
            "TURN_COMPLETION_DENIED",
        )
        self.terminal = status
        return status == "completed"
