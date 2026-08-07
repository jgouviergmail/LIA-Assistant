"""Host bind-source preparation (B05).

A bind source that does not exist when Compose starts is created by the
daemon as a root-owned directory — the wrong owner AND possibly the wrong
type. Every required source is therefore created (dirs) or asserted (files)
with explicit modes BEFORE any Compose command, and a type mismatch fails
closed with a stable code.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from scripts.install.model import ComposeInvocation, HostPathRequirement


class HostPathError(ValueError):
    """Host filesystem precondition failure (stable value-free code)."""


def required_host_paths(
    invocation: ComposeInvocation, *, root: Path
) -> tuple[HostPathRequirement, ...]:
    """The host paths the selected layers bind-mount or write into.

    Args:
        invocation: Selected Compose layers (env flag ``LIA_INSTALL_CADDY``
            marks the Caddy exposure, whose generated Caddyfile must exist).
        root: Bundle/checkout root the relative bind sources resolve from.

    Returns:
        Ordered requirements (directories first, then required files).
    """
    requirements: list[HostPathRequirement] = [
        # apps/api/config is bind-mounted read-only into the API container.
        HostPathRequirement(root / "apps" / "api" / "config", "dir", 0o700),
        # Default backup target resolves OUTSIDE the bundle root on purpose:
        # a bundle wipe/reinstall must never take the database dumps with it.
        HostPathRequirement(
            (root.parent / "lia-data" / "postgres-backups"), "dir", 0o700
        ),
    ]
    if invocation.env.get("LIA_INSTALL_CADDY"):
        requirements.append(
            HostPathRequirement(
                root / "infrastructure" / "caddy" / "Caddyfile", "file", None
            )
        )
    return tuple(requirements)


def prepare_host_paths(requirements: Sequence[HostPathRequirement]) -> None:
    """Create directories (with modes) and assert required files.

    Raises:
        HostPathError: ``host_path_type_mismatch:<path>`` when an expected
            directory is a file (or vice versa);
            ``host_path_missing_file:<path>`` for an absent required file.
    """
    for requirement in requirements:
        path = requirement.path
        if requirement.kind == "dir":
            if path.exists() and not path.is_dir():
                raise HostPathError(f"host_path_type_mismatch:{path}")
            path.mkdir(parents=True, exist_ok=True)
            if requirement.mode is not None and os.name == "posix":
                path.chmod(requirement.mode)
        elif requirement.kind == "file":
            if path.exists() and path.is_dir():
                raise HostPathError(f"host_path_type_mismatch:{path}")
            if not path.is_file():
                raise HostPathError(f"host_path_missing_file:{path}")
            if requirement.mode is not None and os.name == "posix":
                path.chmod(requirement.mode)
        else:  # pragma: no cover - guarded by the dataclass contract
            raise HostPathError(f"host_path_unknown_kind:{requirement.kind}")
