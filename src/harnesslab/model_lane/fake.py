from __future__ import annotations

from harnesslab.model_lane.models import (
    ProviderFailureCategory,
    ProviderInvocationError,
    ProviderRequest,
    ProviderResult,
    ProviderUsage,
)


class FakeDirectProvider:
    """Deterministic no-network provider for Gate D only."""

    def __init__(
        self,
        public_output_text: str,
        *,
        observed_model: str | None = "fake-observed-model",
        failure: ProviderFailureCategory | None = None,
    ) -> None:
        self.public_output_text = public_output_text
        self.observed_model = observed_model
        self.failure = failure
        self.requests: list[ProviderRequest] = []

    async def invoke(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        if self.failure is not None:
            raise ProviderInvocationError(self.failure, f"fake provider {self.failure.value}")
        return ProviderResult(
            requested_model=request.profile.requested_model,
            observed_model=self.observed_model,
            provider=request.profile.provider,
            endpoint=f"{request.profile.base_url}{request.profile.route}",
            protocol=request.profile.protocol,
            request_id="fake-response-1",
            public_output_text=self.public_output_text,
            usage=ProviderUsage(input_tokens=100, output_tokens=25, total_tokens=125),
            stop_reason="stop",
            response_status="completed",
            latency_ms=0,
            attempt_count=1,
        )
