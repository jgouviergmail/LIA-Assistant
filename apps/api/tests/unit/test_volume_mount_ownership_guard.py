"""A named volume mounted on a path the image does not create is owned by root.

Docker only copies ownership from the image into a *new* named volume when the
mount destination already exists in that image. When it does not, Docker
fabricates the mount point itself — owned by ``root:root``, mode 755 — and a
container running as a non-root user can never write there. Worse, the volume
keeps that ownership for its entire life: rebuilding the image afterwards
changes nothing, because the copy only ever happens at volume creation.

Measured in production on 2026-07-27 (three cases, image ``lia-api:local``):

===========================================================  ==================
Case                                                         Resulting owner
===========================================================  ==================
New volume, destination exists in image as ``appuser``       ``appuser:appuser``
New volume, destination absent from image                    ``root:root``
Pre-existing root-owned volume, remounted                    ``root:root``
===========================================================  ==================

That is exactly how ``skills_data`` broke: ``Dockerfile.prod`` created
``/app/data/attachments`` (so attachments worked) but never
``/app/data/skills/users``, and ``.gitignore`` keeps the latter out of the build
context. Every user-skill import — from the agent tool *and* from the settings
UI — failed with ``PermissionError: [Errno 13]`` from 2026-03-13 until it was
found, silently, because the only symptom was a tool error inside a chat reply.

This guard makes the next occurrence a red build instead of a silent outage.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
COMPOSE_PROD = REPO_ROOT / "docker-compose.prod.yml"

# `mkdir` invocations we can attribute a path to. Matches `mkdir -p /a/b` and
# `mkdir /a/b`, including inside a chained `RUN a && mkdir -p /x` line.
_MKDIR_RE = re.compile(r"\bmkdir\b([^&|;\n]*)")


def _compose() -> dict[str, Any]:
    """Parse the production compose file.

    Returns:
        The parsed compose document.
    """
    return yaml.safe_load(COMPOSE_PROD.read_text(encoding="utf-8"))


def _named_volumes() -> set[str]:
    """Names declared in the top-level ``volumes:`` block.

    Returns:
        Declared named-volume identifiers.
    """
    return set((_compose().get("volumes") or {}).keys())


def _locally_built_services() -> list[tuple[str, Path]]:
    """Services built from a Dockerfile in this repository.

    Only these can be fixed by adding a ``mkdir``: a third-party image's
    contents are not ours to change.

    Returns:
        ``(service_name, dockerfile_path)`` pairs, sorted by service name.
    """
    out: list[tuple[str, Path]] = []
    for name, service in sorted(_compose()["services"].items()):
        build = service.get("build")
        if not isinstance(build, dict):
            continue
        context = build.get("context")
        dockerfile = build.get("dockerfile")
        if not context or not dockerfile:
            continue
        out.append((name, REPO_ROOT / context / dockerfile))
    return out


def _named_volume_destinations(service_name: str) -> list[str]:
    """Destination paths of every *named* volume mounted on a service.

    Bind mounts (``./host:/container``) are excluded: the host directory
    supplies its own ownership, so they do not exhibit this failure mode.

    Args:
        service_name: Service to inspect.

    Returns:
        Absolute in-container destination paths, sorted.
    """
    named = _named_volumes()
    service = _compose()["services"][service_name]
    destinations: list[str] = []
    for mount in service.get("volumes") or []:
        if not isinstance(mount, str):
            continue
        parts = mount.split(":")
        if len(parts) < 2 or parts[0] not in named:
            continue
        destinations.append(parts[1])
    return sorted(destinations)


def _runs_as_non_root(dockerfile: Path) -> bool:
    """Whether the image ends up running as a non-root user.

    A root process writes anywhere, so the ownership trap does not apply.

    Args:
        dockerfile: Dockerfile to inspect.

    Returns:
        True when the final ``USER`` instruction is not root.
    """
    users = re.findall(r"^\s*USER\s+(\S+)", dockerfile.read_text(encoding="utf-8"), re.MULTILINE)
    return bool(users) and users[-1] not in {"root", "0"}


def _created_directories(dockerfile: Path) -> set[str]:
    """Absolute paths the Dockerfile creates with ``mkdir``.

    Args:
        dockerfile: Dockerfile to inspect.

    Returns:
        Normalised absolute paths (no trailing slash).
    """
    created: set[str] = set()
    for args in _MKDIR_RE.findall(dockerfile.read_text(encoding="utf-8")):
        for token in args.split():
            if token.startswith("/"):
                created.add(token.rstrip("/"))
    return created


@pytest.mark.parametrize(
    ("service_name", "dockerfile"),
    _locally_built_services(),
    ids=[name for name, _ in _locally_built_services()],
)
def test_named_volume_destinations_are_created_by_the_image(
    service_name: str, dockerfile: Path
) -> None:
    """Every named-volume destination must pre-exist in the image.

    Otherwise Docker creates it as ``root:root`` and the non-root runtime user
    cannot write into the volume — permanently, since ownership is only ever
    seeded at volume creation.

    Args:
        service_name: Service under test.
        dockerfile: Its Dockerfile.
    """
    assert dockerfile.is_file(), f"{service_name}: {dockerfile} does not exist"

    if not _runs_as_non_root(dockerfile):
        pytest.skip(f"{service_name} runs as root — the ownership trap does not apply")

    created = _created_directories(dockerfile)
    missing = [dest for dest in _named_volume_destinations(service_name) if dest not in created]

    assert not missing, (
        f"{service_name}: {dockerfile.name} never creates {missing}, but "
        f"docker-compose.prod.yml mounts a named volume there. Docker will "
        f"create the mount point as root:root and the non-root runtime user "
        f"will get PermissionError on every write. Add `mkdir -p` for these "
        f"paths BEFORE the `chown -R` that precedes the USER switch."
    )
