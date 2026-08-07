"""Bounded rollback (B14).

Before ANY acquisition can overwrite the mutable ``lia-*:local`` tags, an
existing local install's running image IDs are captured and re-tagged under
project-scoped aliases; prebuilt installs keep their immutable digests and
need no alias. A first install may only STOP its own project's containers —
never remove volumes, generated backups, state, or logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from pathlib import Path

from scripts.install.deploy import Runner, StepFailed
from scripts.install.model import ComposeInvocation, InstallMode
from scripts.install.state import InstallState

_LOCAL_TAGS = {"api": "lia-api:local", "web": "lia-web:local"}


@dataclass(frozen=True)
class RollbackPoint:
    """Everything a bounded restore needs."""

    previous_images: Mapping[str, str]
    rollback_aliases: Mapping[str, str]
    config_backups: Mapping[Path, Path]
    first_install: bool


def _running_image_ids(
    invocation: ComposeInvocation, runner: Runner
) -> dict[str, str]:
    result = runner(
        invocation.prefix()
        + ["images", "--format", "{{.Service}} {{.ID}}", "api", "web"],
    )
    if result.returncode != 0:
        raise StepFailed("rollback_capture_failed")
    images: dict[str, str] = {}
    for line in result.stdout.strip().splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in ("api", "web"):
            images[parts[0]] = parts[1]
    if set(images) != {"api", "web"}:
        raise StepFailed("rollback_capture_failed")
    return images


def capture_rollback_point(
    invocation: ComposeInvocation,
    state: InstallState | None,
    runner: Runner,
) -> RollbackPoint:
    """Capture the restore target BEFORE anything mutable can change.

    First install: nothing to preserve (quiesce-only path). Existing local:
    resolve both running image IDs and alias them (a later ``build`` will
    overwrite the ``lia-*:local`` tags, the aliases survive). Existing
    prebuilt: the prior manifest digests are already immutable.
    """
    if state is None:
        return RollbackPoint(
            previous_images={},
            rollback_aliases={},
            config_backups={},
            first_install=True,
        )
    if state.mode is InstallMode.PREBUILT:
        return RollbackPoint(
            previous_images=dict(state.image_digests),
            rollback_aliases={},
            config_backups={},
            first_install=False,
        )
    images = _running_image_ids(invocation, runner)
    attempt = sum(state.attempts.values()) + 1
    project = state.project_name
    aliases: dict[str, str] = {}
    for service, image_id in images.items():
        alias = f"lia-installer-rollback-{project}-{service}:{attempt}"
        result = runner(["docker", "tag", image_id, alias])
        if result.returncode != 0:
            raise StepFailed("rollback_alias_failed")
        aliases[service] = alias
    return RollbackPoint(
        previous_images=images,
        rollback_aliases=aliases,
        config_backups={},
        first_install=False,
    )


def restore_or_quiesce(
    point: RollbackPoint, invocation: ComposeInvocation, runner: Runner
) -> None:
    """Bounded failure handling.

    First install: stop ONLY this project's containers (volumes, ``.env``,
    backups, state, and logs stay for a later ``--resume``). Existing
    install: restore backed-up config files, restore the exact previous
    images (retag aliases over the local tags), and recreate with
    ``--no-build``. The caller re-checks ``/ready`` before reporting
    rollback success.
    """
    for target, backup in point.config_backups.items():
        target.write_bytes(backup.read_bytes())
    if point.first_install:
        result = runner(invocation.prefix() + ["stop"])
        if result.returncode != 0:
            raise StepFailed("quiesce_failed")
        return
    for service, alias in point.rollback_aliases.items():
        result = runner(["docker", "tag", alias, _LOCAL_TAGS[service]])
        if result.returncode != 0:
            raise StepFailed("rollback_retag_failed")
    result = runner(
        invocation.prefix()
        + ["up", "-d", "--no-build", "--force-recreate", "api", "web"]
    )
    if result.returncode != 0:
        raise StepFailed("rollback_restore_failed")
