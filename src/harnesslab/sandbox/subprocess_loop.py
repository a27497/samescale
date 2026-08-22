from __future__ import annotations

import asyncio
import concurrent.futures
import importlib
import sys
import threading
from collections.abc import Coroutine
from typing import cast


class _WindowsSubprocessLoop:
    """Run Docker subprocess work away from HarnessLab's psycopg selector loop."""

    def __init__(self) -> None:
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread = threading.Thread(target=self._run, daemon=True, name="harnesslab-docker")
        self._thread.start()
        if not self._ready.wait(timeout=10):
            raise RuntimeError("Docker subprocess event loop failed to start")

    def _run(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Proactor loop is available only on Windows")
        windows_events = importlib.import_module("asyncio.windows_events")
        loop_type = cast(type[asyncio.AbstractEventLoop], vars(windows_events)["ProactorEventLoop"])
        self._loop = loop_type()
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            raise RuntimeError("Docker subprocess event loop is unavailable")
        return self._loop


_WINDOWS_LOOP: _WindowsSubprocessLoop | None = None
_WINDOWS_LOOP_LOCK = threading.Lock()


def _windows_loop() -> _WindowsSubprocessLoop:
    global _WINDOWS_LOOP
    with _WINDOWS_LOOP_LOCK:
        if _WINDOWS_LOOP is None:
            _WINDOWS_LOOP = _WindowsSubprocessLoop()
        return _WINDOWS_LOOP


async def run_on_subprocess_loop[T](coroutine: Coroutine[object, object, T]) -> T:
    if sys.platform != "win32":
        return await coroutine

    completed = threading.Event()

    async def tracked() -> T:
        try:
            return await coroutine
        finally:
            completed.set()

    future: concurrent.futures.Future[T] = asyncio.run_coroutine_threadsafe(
        tracked(), _windows_loop().loop
    )
    try:
        return await asyncio.wrap_future(future)
    except asyncio.CancelledError:
        future.cancel()
        await asyncio.to_thread(completed.wait)
        raise
