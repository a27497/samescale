"""Create the fixed official Analyst smoke session without loading provider credentials."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from harnesslab.analyst.sessions import AnalystSessions, CreateInvestigation
from harnesslab.core.config import get_settings
from harnesslab.db.session import create_engine

ROOT = Path(__file__).resolve().parents[1]


async def prepare(output: Path, artifact_roots: tuple[Path, ...]) -> None:
    request = CreateInvestigation.model_validate_json(
        (ROOT / "profiles/analyst/core-real-matrix-v6-smoke.json").read_bytes()
    )
    engine = create_engine(get_settings())
    try:
        # An explicitly empty provider environment guarantees keyless preparation.
        # DB configuration is separate; provider credential values are never loaded here.
        service = AnalystSessions(
            engine,
            repository_root=ROOT,
            artifact_roots=artifact_roots,
            environment={},
            real_enabled=False,
        )
        value = await service.create(request)
        preflight = await service.preflight(value.session_id)
        assert preflight["status"] == "BLOCKED"
        assert preflight["credential_reference_status"] == "MISSING"
        assert preflight["reasons"] == ["CREDENTIAL_REFERENCE_MISSING"]
        assert not value.usage and value.state.tool_calls == 0
        output.mkdir(parents=True, exist_ok=True)
        (output / "session.json").write_text(
            json.dumps(value.public_view(), ensure_ascii=False, indent=2) + "\n"
        )
        (output / "preflight.json").write_text(
            json.dumps(preflight, ensure_ascii=False, indent=2) + "\n"
        )
        print(
            json.dumps(
                {
                    "session_id": value.session_id,
                    "preflight_digest": preflight["preflight_digest"],
                    "status": preflight["status"],
                    "credential_reference_status": "MISSING",
                    "provider_environment": "EXPLICIT_KEYLESS",
                    "provider_invocations": 0,
                }
            )
        )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, action="append", required=True)
    args = parser.parse_args()
    asyncio.run(prepare(args.output, tuple(args.artifact_root)))


if __name__ == "__main__":
    main()
