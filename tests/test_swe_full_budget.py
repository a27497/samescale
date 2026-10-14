from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture
def collector() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "evaluation/coding-agent/budget_collector.py"
    spec = importlib.util.spec_from_file_location("budget_collector", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_response_counts_discard_private_fields_and_keep_distinct_timestamps(
    collector: ModuleType,
) -> None:
    def payload(timestamp: str) -> dict[str, object]:
        values = {
            "event.name": "codex.sse_event",
            "event.kind": "response.completed",
            "event.timestamp": timestamp,
            "input_token_count": "1000",
            "cached_token_count": "200",
            "output_token_count": "100",
            "user.email": "PRIVATE_EMAIL",
            "tool.output": "PRIVATE_BODY",
        }
        return {
            "resourceLogs": [
                {
                    "scopeLogs": [
                        {
                            "logRecords": [
                                {
                                    "timeUnixNano": "0",
                                    "attributes": [
                                        {"key": k, "value": {"stringValue": v}}
                                        for k, v in values.items()
                                    ],
                                }
                            ]
                        }
                    ]
                }
            ]
        }

    first = next(collector.project(payload("T1")))
    duplicate = next(collector.project(payload("T1")))
    second = next(collector.project(payload("T2")))
    assert first == duplicate and first != second
    assert "PRIVATE" not in str(first)
    assert collector.charge(first) == pytest.approx(0.00262)
    # Cache-write subset and long-context multiplier must not silently undercount the stop ledger.
    usage = {
        "input_tokens": 300000,
        "cached_input_tokens": 100000,
        "cache_write_input_tokens": 1000,
        "output_tokens": 2000,
    }
    assert collector.charge(usage) == pytest.approx(0.851)
    with pytest.raises(ValueError):
        collector.charge({**usage, "cached_input_tokens": 400000})
