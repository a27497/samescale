from __future__ import annotations

import os
from pathlib import Path

from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.local_execution.models import ExecutionPolicy
from harnesslab.local_plans.tasks import fail, load_policy, no_links, read_owned_json
from harnesslab.productization.assets import distribution_root
from harnesslab.registry.models import canonical_digest


def operator_identity() -> str:
    token = os.environ.get("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", "")
    if len(token) < 32:
        raise fail("LOCAL_OPERATOR_REQUIRED", "A local operator credential is required.", 403)
    return canonical_digest({"local_operator_credential": token})


def load_execution_policy() -> ExecutionPolicy:
    try:
        path = Path(os.environ["HARNESSLAB_LOCAL_EXECUTION_POLICY"])
        policy = ExecutionPolicy.model_validate(read_owned_json(path))
        task_policy = load_policy()
        protected = [
            distribution_root(),
            task_policy.managed_store,
            *task_policy.source_roots.values(),
        ]
        protected.extend(a.qualification_file for a in task_policy.admissions)
        protected.extend(a.validation_file for a in task_policy.admissions)
        roots = (policy.artifact_root, policy.runtime_root)
        for root in roots:
            no_links(root)
            if root == Path("/") or root == Path.home() or root == path or root in path.parents:
                raise ValueError("unsafe worker root")
            if any(root == p or root in p.parents or p in root.parents for p in protected):
                raise ValueError("worker storage overlaps protected assets")
        if roots[0] == roots[1] or roots[0] in roots[1].parents or roots[1] in roots[0].parents:
            raise ValueError("worker roots overlap")
        return policy
    except (KeyError, OSError, ValueError, WorkbenchAPIError):
        raise fail(
            "EXECUTION_DISABLED", "Configure separate owned worker policy and isolated roots.", 403
        ) from None
