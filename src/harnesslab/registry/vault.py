"""Local, owner-only secret files; no secret material belongs in database JSON."""

from __future__ import annotations

import json
import os
import re
import stat
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.productization.assets import distribution_root


class CredentialVault:
    def __init__(self, root: Path | None) -> None:
        self.root = root

    @classmethod
    def from_environment(cls) -> CredentialVault:
        value = os.environ.get("HARNESSLAB_CREDENTIAL_STORE")
        return cls(Path(value) if value else None)

    def _directory(self, *, create: bool = False) -> int:
        try:
            root = self.root
            artifact_paths = json.loads(
                os.environ.get(
                    "HARNESSLAB_WORKBENCH_ARTIFACT_ROOTS", '["artifacts", "harnesslab-artifacts"]'
                )
            )
            if not isinstance(artifact_paths, list) or not all(
                isinstance(p, str) for p in artifact_paths
            ):
                raise ValueError("invalid artifact roots")
            if (
                root is None
                or not root.is_absolute()
                or root == Path("/")
                or root.resolve() != root
                or root.is_relative_to(distribution_root().resolve())
                or any(
                    root.is_relative_to(Path(p).resolve()) or Path(p).resolve().is_relative_to(root)
                    for p in artifact_paths
                )
            ):
                raise ValueError("invalid vault directory")
            if create:
                root.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            info = os.fstat(fd)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                os.close(fd)
                raise ValueError("vault must be owned by this process user with mode 0700")
            return fd
        except (OSError, ValueError):
            raise WorkbenchAPIError(
                503,
                "CREDENTIAL_STORE_UNAVAILABLE",
                "Configure private HARNESSLAB_CREDENTIAL_STORE outside source and artifacts.",
            ) from None

    def put(self, value: str) -> str:
        data = value.encode("utf-8")
        if not data or len(data) > 8192:
            raise WorkbenchAPIError(422, "INVALID_SECRET", "Secret size is invalid.")
        directory = self._directory(create=True)
        reference = uuid4().hex
        created = False
        try:
            fd = os.open(
                reference,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory,
            )
            created = True
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(directory)
        except OSError:
            if created:
                with suppress(OSError):
                    os.unlink(reference, dir_fd=directory)
            raise WorkbenchAPIError(
                503, "CREDENTIAL_STORE_UNAVAILABLE", "Secret was not saved."
            ) from None
        finally:
            os.close(directory)
        return reference

    def read(self, reference: str) -> str:
        if re.fullmatch(r"[a-f0-9]{32}", reference) is None:
            raise WorkbenchAPIError(409, "INVALID_SECRET_REFERENCE", "Secret reference is invalid.")
        directory = self._directory()
        try:
            fd = os.open(reference, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_nlink != 1
                ):
                    raise ValueError("invalid secret permissions")
                value = stream.read(8193)
                if not value or len(value) > 8192:
                    raise ValueError("invalid secret size")
                return value.decode("utf-8")
        except (OSError, ValueError):
            raise WorkbenchAPIError(
                503, "CREDENTIAL_STORE_UNAVAILABLE", "Secret is unavailable."
            ) from None
        finally:
            os.close(directory)

    def present(self, reference: str | None) -> bool:
        if reference is None:
            return False
        try:
            self.read(reference)
            return True
        except WorkbenchAPIError:
            return False

    def discard(self, reference: str) -> None:
        """Remove only an uncommitted file created by this request."""
        if re.fullmatch(r"[a-f0-9]{32}", reference) is None:
            return
        directory = self._directory()
        try:
            os.unlink(reference, dir_fd=directory)
        finally:
            os.close(directory)
