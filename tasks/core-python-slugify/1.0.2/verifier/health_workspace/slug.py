def schedule(jobs: list[dict[str, object]]) -> list[dict[str, object]]:
    for job in jobs:
        priority = job.get("priority")
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError("priority must be an integer")
    return sorted(jobs, key=lambda job: -job["priority"])
