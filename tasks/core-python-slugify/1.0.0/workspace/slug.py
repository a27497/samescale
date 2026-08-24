def schedule(jobs: list[dict[str, object]]) -> list[dict[str, object]]:
    jobs.sort(key=lambda job: job["priority"])
    return jobs
