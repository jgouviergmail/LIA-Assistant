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

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
COMPOSE_PROD = REPO_ROOT / "docker-compose.prod.yml"

# `mkdir` invocations we can attribute a path to. Matches `mkdir -p /a/b` and
# `mkdir /a/b`, including inside a chained `RUN a && mkdir -p /x` line.
_MKDIR_RE = re.compile(r"\bmkdir\b([^&|;\n]*)")

# `chown` as a *command*. The lookbehind and the mandatory whitespace exclude
# `COPY --chown=user:group`, which grants ownership of copied files and says
# nothing about a directory that will host a volume.
_CHOWN_RE = re.compile(r"(?<![-\w])chown\s([^&|;\n]*)")


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


def _runtime_user(dockerfile: Path) -> str | None:
    """The user the image finally runs as.

    Args:
        dockerfile: Dockerfile to inspect.

    Returns:
        The last ``USER`` argument, or None when the file has none.
    """
    users = re.findall(r"^\s*USER\s+(\S+)", dockerfile.read_text(encoding="utf-8"), re.MULTILINE)
    return users[-1] if users else None


def _runs_as_non_root(dockerfile: Path) -> bool:
    """Whether the image ends up running as a non-root user.

    A root process writes anywhere, so the ownership trap does not apply.

    Args:
        dockerfile: Dockerfile to inspect.

    Returns:
        True when the final ``USER`` instruction is not root.
    """
    user = _runtime_user(dockerfile)
    return user is not None and user not in {"root", "0"}


def _absolute_path_tokens(args: str) -> list[str]:
    """Absolute paths among a command's arguments.

    Args:
        args: Raw argument string of a single shell command.

    Returns:
        Normalised absolute paths (no trailing slash), in order.
    """
    return [token.rstrip("/") for token in args.split() if token.startswith("/")]


def _mkdir_sites(dockerfile: Path) -> list[tuple[int, list[str]]]:
    """Every ``mkdir`` in the Dockerfile with the paths it creates.

    Args:
        dockerfile: Dockerfile to inspect.

    Returns:
        ``(character_offset, created_paths)`` pairs in file order.
    """
    text = dockerfile.read_text(encoding="utf-8")
    return [(m.start(), _absolute_path_tokens(m.group(1))) for m in _MKDIR_RE.finditer(text)]


def _chown_sites(dockerfile: Path) -> list[tuple[int, str, list[str]]]:
    """Every ``chown`` command in the Dockerfile with its owner and targets.

    Args:
        dockerfile: Dockerfile to inspect.

    Returns:
        ``(character_offset, user, target_paths)`` triples in file order. ``user``
        is the part before ``:`` of the owner spec.
    """
    text = dockerfile.read_text(encoding="utf-8")
    sites: list[tuple[int, str, list[str]]] = []
    for match in _CHOWN_RE.finditer(text):
        owner = ""
        targets: list[str] = []
        for token in match.group(1).split():
            if token.startswith("-"):
                continue
            if not owner:
                owner = token
                continue
            if token.startswith("/"):
                targets.append(token.rstrip("/"))
        sites.append((match.start(), owner.split(":", 1)[0], targets))
    return sites


def _covers(ancestor: str, path: str) -> bool:
    """Whether ``ancestor`` is ``path`` or one of its parents.

    Args:
        ancestor: Candidate directory.
        path: Path to test.

    Returns:
        True when an operation on ``ancestor`` reaches ``path``.
    """
    return path == ancestor or path.startswith(f"{ancestor}/")


def _created_directories(dockerfile: Path) -> set[str]:
    """Absolute paths the Dockerfile creates with ``mkdir``.

    ``mkdir -p /a/b/c`` also creates ``/a/b``, so a destination counts as created
    when a deeper path is created beneath it.

    Args:
        dockerfile: Dockerfile to inspect.

    Returns:
        Normalised absolute paths (no trailing slash).
    """
    created: set[str] = set()
    for _, paths in _mkdir_sites(dockerfile):
        for path in paths:
            created.add(path)
            # Pure string walk rather than pathlib: this suite runs on Windows
            # too, where PurePath would reinterpret these POSIX container paths.
            segments = path.split("/")
            for depth in range(2, len(segments)):
                created.add("/".join(segments[:depth]))
    return created


def _destinations_missing_creation(destinations: list[str], dockerfile: Path) -> list[str]:
    """Destinations the image never creates.

    Args:
        destinations: In-container mount destinations to check.
        dockerfile: Dockerfile to inspect.

    Returns:
        The subset absent from every ``mkdir``, in input order.
    """
    created = _created_directories(dockerfile)
    return [destination for destination in destinations if destination not in created]


def _destinations_missing_ownership(destinations: list[str], dockerfile: Path) -> list[str]:
    """Destinations created as root and never handed to the runtime user.

    A destination the image does not create at all is *not* reported here: that
    is the other guard's finding, and one cause should fail one test.

    Args:
        destinations: In-container mount destinations to check.
        dockerfile: Dockerfile to inspect.

    Returns:
        The subset created without a subsequent covering ``chown``, in input
        order. Empty when the image runs as root, where the trap cannot occur.
    """
    runtime_user = _runtime_user(dockerfile)
    if runtime_user is None or runtime_user in {"root", "0"}:
        return []

    mkdir_sites = _mkdir_sites(dockerfile)
    chown_sites = _chown_sites(dockerfile)

    unowned: list[str] = []
    for destination in destinations:
        # `mkdir -p a/b/c` creates the destination whether it names it exactly,
        # names an ancestor of it, or names something below it.
        creation_offsets = [
            offset
            for offset, paths in mkdir_sites
            if any(_covers(path, destination) or _covers(destination, path) for path in paths)
        ]
        earliest_creation = min(creation_offsets, default=None)
        if earliest_creation is None:
            continue
        if not any(
            offset > earliest_creation
            and user == runtime_user
            and any(_covers(target, destination) for target in targets)
            for offset, user, targets in chown_sites
        ):
            unowned.append(destination)
    return unowned


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

    missing = _destinations_missing_creation(_named_volume_destinations(service_name), dockerfile)

    assert not missing, (
        f"{service_name}: {dockerfile.name} never creates {missing}, but "
        f"docker-compose.prod.yml mounts a named volume there. Docker will "
        f"create the mount point as root:root and the non-root runtime user "
        f"will get PermissionError on every write. Add `mkdir -p` for these "
        f"paths BEFORE the `chown -R` that precedes the USER switch."
    )


@pytest.mark.parametrize(
    ("service_name", "dockerfile"),
    _locally_built_services(),
    ids=[name for name, _ in _locally_built_services()],
)
def test_named_volume_destinations_are_chowned_to_the_runtime_user(
    service_name: str, dockerfile: Path
) -> None:
    """Creating the mount point is only half of it — it must also be owned.

    ``mkdir`` in a ``RUN`` runs as root, so a destination created but never
    chowned is seeded into the volume as ``root:root`` and the failure is
    identical to never creating it at all. The companion test above only proves
    existence; on its own it would pass for a volume mounted outside the subtree
    the Dockerfile happens to ``chown -R``.

    Args:
        service_name: Service under test.
        dockerfile: Its Dockerfile.
    """
    runtime_user = _runtime_user(dockerfile)
    if runtime_user is None or runtime_user in {"root", "0"}:
        pytest.skip(f"{service_name} runs as root — the ownership trap does not apply")

    unowned = _destinations_missing_ownership(_named_volume_destinations(service_name), dockerfile)

    assert not unowned, (
        f"{service_name}: {dockerfile.name} creates {unowned} but never chowns "
        f"them to '{runtime_user}' after creating them. `mkdir` in a RUN layer "
        f"runs as root, Docker seeds the new volume with that ownership, and it "
        f"is permanent — rebuilding the image later changes nothing. Extend the "
        f"existing `chown -R {runtime_user}:{runtime_user}` to cover these paths."
    )


# ==========================================================================
# Falsification — a guard nobody has seen fail is a guard nobody can trust
# ==========================================================================


def _write_dockerfile(tmp_path: Path, body: str) -> Path:
    """Materialise a synthetic Dockerfile.

    Args:
        tmp_path: pytest temporary directory.
        body: Dockerfile content.

    Returns:
        Path to the written file.
    """
    path = tmp_path / "Dockerfile.synthetic"
    path.write_text(body, encoding="utf-8")
    return path


def test_creation_guard_catches_the_production_regression(tmp_path: Path) -> None:
    """The exact ``skills_data`` shape must be reported as missing.

    Args:
        tmp_path: pytest temporary directory.
    """
    dockerfile = _write_dockerfile(
        tmp_path,
        "FROM python\nRUN mkdir -p /app/data/attachments"
        " && chown -R appuser:appuser /app/data\nUSER appuser\n",
    )

    assert _destinations_missing_creation(
        ["/app/data/attachments", "/app/data/skills/users"], dockerfile
    ) == ["/app/data/skills/users"]


def test_ownership_guard_catches_a_volume_outside_the_chowned_subtree(tmp_path: Path) -> None:
    """A created-but-unowned destination is the failure the creation test misses.

    Args:
        tmp_path: pytest temporary directory.
    """
    dockerfile = _write_dockerfile(
        tmp_path,
        "FROM python\nRUN mkdir -p /app/data/attachments /var/lib/lia/cache"
        " && chown -R appuser:appuser /app/data\nUSER appuser\n",
    )

    assert _destinations_missing_creation(["/var/lib/lia/cache"], dockerfile) == []
    assert _destinations_missing_ownership(
        ["/app/data/attachments", "/var/lib/lia/cache"], dockerfile
    ) == ["/var/lib/lia/cache"]


def test_ownership_guard_rejects_a_chown_that_precedes_the_mkdir(tmp_path: Path) -> None:
    """Chowning before creating leaves the directory root-owned.

    Args:
        tmp_path: pytest temporary directory.
    """
    dockerfile = _write_dockerfile(
        tmp_path,
        "FROM python\nRUN chown -R appuser:appuser /app/data\n"
        "RUN mkdir -p /app/data/tool_cache\nUSER appuser\n",
    )

    assert _destinations_missing_ownership(["/app/data/tool_cache"], dockerfile) == [
        "/app/data/tool_cache"
    ]


def test_copy_chown_flag_is_not_mistaken_for_a_chown_command(tmp_path: Path) -> None:
    """``COPY --chown=`` grants ownership of copied files, not of a mount point.

    Args:
        tmp_path: pytest temporary directory.
    """
    dockerfile = _write_dockerfile(
        tmp_path,
        "FROM python\nRUN mkdir -p /app/data/tool_cache\n"
        "COPY --chown=appuser:appuser . /app/data\nUSER appuser\n",
    )

    assert _chown_sites(dockerfile) == []
    assert _destinations_missing_ownership(["/app/data/tool_cache"], dockerfile) == [
        "/app/data/tool_cache"
    ]


def test_root_image_is_exempt(tmp_path: Path) -> None:
    """A root process writes anywhere, so neither finding applies.

    Args:
        tmp_path: pytest temporary directory.
    """
    dockerfile = _write_dockerfile(tmp_path, "FROM python\nRUN mkdir -p /app/data\n")

    assert _destinations_missing_ownership(["/srv/whatever"], dockerfile) == []


def test_mkdir_p_covers_its_ancestors(tmp_path: Path) -> None:
    """``mkdir -p a/b/c`` really does create ``a/b``, and the guard knows it.

    Args:
        tmp_path: pytest temporary directory.
    """
    dockerfile = _write_dockerfile(
        tmp_path,
        "FROM python\nRUN mkdir -p /app/data/skills/users"
        " && chown -R appuser:appuser /app/data\nUSER appuser\n",
    )

    assert _destinations_missing_creation(["/app/data/skills"], dockerfile) == []
    assert _destinations_missing_ownership(["/app/data/skills"], dockerfile) == []
