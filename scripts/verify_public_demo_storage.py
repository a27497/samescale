"""Deployment startup gate: verify configured bytes and all saved evidence references."""

from __future__ import annotations

import asyncio
import json

from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.core.config import get_settings
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.demo.service import public_demo


async def verify() -> bool:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        async with create_session_factory(engine)() as session:
            evidence = await public_demo(session, settings.workbench_artifact_roots)
        print(json.dumps({"PUBLIC_DEMO_STORAGE_READY": True, "demo_id": evidence["demo_id"]}))
        return True
    except WorkbenchAPIError as exc:
        print(json.dumps({"PUBLIC_DEMO_STORAGE_READY": False, "code": exc.code}))
        return False
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(verify()) else 1)
