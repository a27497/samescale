"""Retired: legacy QA identities must never be regenerated or overwritten."""

if __name__ == "__main__":
    raise SystemExit(
        "Legacy QA seeding is retired. Preserve its records and integrity failures; "
        "use scripts/seed_public_demo.py to create separately identified fixture evidence."
    )
