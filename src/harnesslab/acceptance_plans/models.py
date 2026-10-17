from typing import Annotated, Literal

from pydantic import Field

from harnesslab.registry.models import RegistryModel

Identity = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Digest = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
RequestID = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{16,80}$")]
Text = Annotated[str, Field(min_length=1, max_length=2000)]
Decision = Literal["PENDING", "APPROVED", "REJECTED"]


class CreatePlan(RegistryModel):
    request_id: RequestID
    snapshot_identity: Identity
    snapshot_content_digest: Digest
    original_prompt: str = Field(min_length=1, max_length=16000)


class ChangePlan(RegistryModel):
    request_id: RequestID
    expected_digest: Digest
    action: Literal["REVIEW", "ADD", "CONFIRM", "FREEZE", "REVISE"]
    reason: Text
    clause_id: str | None = Field(default=None, max_length=64)
    text: Text | None = None
    decision: Decision | None = None
    acknowledgement: Literal["SCOPE_ONLY_NO_EXECUTION"] | None = None
