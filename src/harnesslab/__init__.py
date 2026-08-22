"""HarnessLab AI package."""

import asyncio
import sys
from importlib.metadata import PackageNotFoundError, version

if sys.platform == "win32":
    # psycopg async connections require a selector-based loop on Windows.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

try:
    __version__ = version("harnesslab-ai")
except PackageNotFoundError:
    __version__ = "0.0.0+uninstalled"

__all__ = ["__version__"]
