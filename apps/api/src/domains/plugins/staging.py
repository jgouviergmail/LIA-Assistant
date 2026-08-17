"""Plugin package zip detection and staging (ADR-225).

Mirrors the skills pipeline S3 hardening (zip bomb, member count, zip-slip)
with two plugin-specific behaviors:

- the package root is located by ``plugin.json`` (§5.1) — at the archive root
  or under a single wrapper directory — and re-anchored on extraction;
- all prefix matching happens on raw zip member names (always ``/``-separated
  per the zip format), never through ``pathlib`` string conversion — the
  skills ``_stage_zip`` derived its prefix via ``Path.parent``, which yields
  backslashes on Windows and silently matched nothing (ADR-225 finding).
"""

import shutil
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from src.domains.plugins.exceptions import raise_plugin_invalid_package
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

_MANIFEST_NAME = "plugin.json"
_STAGED_ROOT_DIRNAME = "__plugin__"


def _manifest_prefix(names: list[str]) -> str | None:
    """Locate the plugin root inside the archive from its ``plugin.json``.

    Args:
        names: Non-directory member names (raw zip paths, ``/``-separated).

    Returns:
        The member-name prefix of the plugin root (``""`` for a flat archive,
        ``"wrapper/"`` for a single wrapper directory), or None when the
        archive is not a plugin package.
    """
    if _MANIFEST_NAME in names:
        return ""
    candidates = [
        name for name in names if name.endswith("/" + _MANIFEST_NAME) and name.count("/") == 1
    ]
    if len(candidates) == 1:
        return candidates[0][: -len(_MANIFEST_NAME)]
    return None


def zip_contains_plugin_manifest(content: bytes) -> bool:
    """Cheap detection: does this archive look like an Agent Plugins package?

    Args:
        content: Raw uploaded bytes.

    Returns:
        True when a ``plugin.json`` sits at the archive root or under a
        single wrapper directory (§5.1 plugin root). False for anything
        else, including bytes that are not a zip archive.
    """
    try:
        with zipfile.ZipFile(BytesIO(content)) as zf:
            names = [i.filename for i in zf.infolist() if not i.is_dir()]
    except zipfile.BadZipFile:
        return False
    return _manifest_prefix(names) is not None


def stage_plugin_zip(content: bytes, staging: Path, settings: Any) -> Path:
    """Extract a plugin package into a staging directory with S3 guards.

    Args:
        content: Raw uploaded bytes.
        staging: Temp directory owned by the caller.
        settings: Application settings (``plugins_zip_max_files``,
            ``plugins_zip_max_decompressed_kb``).

    Returns:
        The staged plugin root directory.

    Raises:
        ValidationError: on zip bombs, zip-slip, missing manifest or a
            malformed archive.
    """
    try:
        with zipfile.ZipFile(BytesIO(content)) as zf:
            infos = [i for i in zf.infolist() if not i.is_dir()]
            _enforce_zip_budgets(infos, settings)

            prefix = _manifest_prefix([i.filename for i in infos])
            if prefix is None:
                raise_plugin_invalid_package("no plugin.json at the package root")

            plugin_root = (staging / _STAGED_ROOT_DIRNAME).resolve()
            plugin_root.mkdir(parents=True)
            _extract_members(zf, infos, prefix, plugin_root)
    except zipfile.BadZipFile:
        raise_plugin_invalid_package("invalid zip file")
    return plugin_root


def _enforce_zip_budgets(infos: list[zipfile.ZipInfo], settings: Any) -> None:
    """S3 zip-bomb guards: member count + total decompressed size."""
    if len(infos) > settings.plugins_zip_max_files:
        raise_plugin_invalid_package(f"too many files (max {settings.plugins_zip_max_files})")
    total = sum(i.file_size for i in infos)
    if total > settings.plugins_zip_max_decompressed_kb * 1024:
        raise_plugin_invalid_package(
            f"decompressed size exceeds {settings.plugins_zip_max_decompressed_kb}KB"
        )


def _extract_members(
    zf: zipfile.ZipFile, infos: list[zipfile.ZipInfo], prefix: str, plugin_root: Path
) -> None:
    """Extract the plugin-root subtree, re-anchored, with a zip-slip guard.

    Members outside the plugin root (multi-root archives) are dropped with a
    warning, mirroring the skills pipeline behavior — visible, never silent.
    """
    skipped: list[str] = []
    for info in infos:
        if prefix and not info.filename.startswith(prefix):
            skipped.append(info.filename)
            continue
        rel = info.filename[len(prefix) :]
        if not rel:
            continue
        dest = (plugin_root / rel).resolve()
        try:
            dest.relative_to(plugin_root)
        except ValueError:
            raise_plugin_invalid_package("archive contains path traversal entries")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)
    if skipped:
        logger.warning(
            "plugin_zip_members_outside_root_skipped",
            skipped_count=len(skipped),
            sample=skipped[:5],
        )
