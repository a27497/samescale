from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field

Identifier = Annotated[
    str, Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
]
Sha256Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class EvaluationLane(StrEnum):
    MODEL = "M"
    HARNESS = "H"
    PRODUCT = "P"
    JUDGE = "J"


class NetworkPolicy(StrEnum):
    DENY = "deny"
    ALLOWLIST = "allowlist"
    UNRESTRICTED = "unrestricted"


class Protocol(StrEnum):
    RESPONSES = "responses"
    CHAT_COMPLETIONS = "chat_completions"
    MESSAGES = "messages"
    CUSTOM = "custom"
