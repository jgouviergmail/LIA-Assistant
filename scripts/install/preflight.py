"""Preflight gates (B01/B05).

Mode resolution consumes ONLY the adjacent manifest file — never a parent
directory, never a symlink, never a mutable image reference (the manifest
schema already rejects tags). Runtime daemon/port checks belong to a real
install; ``--dry-run``/``--check-only`` stay read-only.
"""

from __future__ import annotations

from pathlib import Path

from scripts.install.manifest import ManifestError, load_manifest
from scripts.install.model import InstallMode

MANIFEST_NAME = "lia-self-host-manifest.json"

#: LAN port lists use Compose ``!override`` (supported from 2.24.4).
MIN_COMPOSE_VERSION = (2, 24, 4)


class PreflightError(ValueError):
    """A precondition failed (stable value-free code)."""


def resolve_install_mode(
    *,
    requested: InstallMode | None,
    bundle_root: Path,
) -> tuple[InstallMode, Path | None]:
    """Resolve the effective install mode and its manifest path.

    An explicit LOCAL request always wins. An explicit PREBUILT request
    requires the adjacent manifest to load as ``qualification="passed"``.
    With no request, an adjacent valid passed manifest selects prebuilt;
    anything else (absent, candidate, invalid, symlink) selects local.

    Raises:
        PreflightError: ``prebuilt_requires_passed_manifest`` when prebuilt
            is explicitly requested without a valid passed manifest.
    """
    if requested is InstallMode.LOCAL:
        return InstallMode.LOCAL, None
    manifest_path = bundle_root / MANIFEST_NAME
    loadable = manifest_path.is_file() and not manifest_path.is_symlink()
    if requested is InstallMode.PREBUILT:
        if not loadable:
            raise PreflightError("prebuilt_requires_passed_manifest")
        try:
            load_manifest(manifest_path, required_qualification="passed")
        except ManifestError as exc:
            raise PreflightError("prebuilt_requires_passed_manifest") from exc
        return InstallMode.PREBUILT, manifest_path
    if not loadable:
        return InstallMode.LOCAL, None
    try:
        load_manifest(manifest_path, required_qualification="passed")
    except ManifestError:
        return InstallMode.LOCAL, None
    return InstallMode.PREBUILT, manifest_path


def check_compose_version(version: str) -> None:
    """Reject Docker Compose older than ``MIN_COMPOSE_VERSION``.

    Raises:
        PreflightError: ``compose_version_too_old`` or
            ``compose_version_unparsable``.
    """
    parts = version.strip().lstrip("v").split(".")
    try:
        numbers = tuple(int(part) for part in parts[:3])
    except ValueError as exc:
        raise PreflightError("compose_version_unparsable") from exc
    if len(numbers) < 3 or numbers < MIN_COMPOSE_VERSION:
        raise PreflightError("compose_version_too_old")
