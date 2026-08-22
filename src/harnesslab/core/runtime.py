from __future__ import annotations

import asyncio


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    """Return the selector loop required by psycopg async connections on Windows."""

    return asyncio.SelectorEventLoop()
