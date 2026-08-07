"""Host-path preparation contract (B05).

Every bind source the selected Compose layers need must exist with the
right type and mode BEFORE Compose runs (a missing bind source becomes a
root-owned directory created by the daemon). A path of the wrong type
fails closed with a stable code.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from scripts.install.host_paths import (
    HostPathError,
    prepare_host_paths,
    required_host_paths,
)
from scripts.install.model import ComposeInvocation, InstallMode


def _invocation(root: Path, *, caddy: bool = False) -> ComposeInvocation:
    files = [root / "docker-compose.prod.yml", root / "docker-compose.install.yml"]
    return ComposeInvocation(files=tuple(files), mode=InstallMode.LOCAL, env={
        "LIA_INSTALL_CADDY": "1" if caddy else "",
    })


def test_required_paths_cover_config_backup_and_caddyfile(tmp_path: Path) -> None:
    requirements = required_host_paths(_invocation(tmp_path, caddy=True), root=tmp_path)
    in_root = {
        str(r.path.relative_to(tmp_path)).replace(os.sep, "/"): r
        for r in requirements
        if r.path.is_relative_to(tmp_path)
    }
    assert in_root["apps/api/config"].kind == "dir"
    assert in_root["apps/api/config"].mode == 0o700
    assert in_root["infrastructure/caddy/Caddyfile"].kind == "file"
    backup = next(r for r in requirements if "backup" in str(r.path))
    assert backup.kind == "dir" and backup.mode == 0o700
    # The backup dir resolves OUTSIDE the bundle root by default: a bundle
    # wipe/reinstall must never take the database dumps with it.
    assert not backup.path.is_relative_to(tmp_path)


def test_caddyfile_requirement_only_for_caddy(tmp_path: Path) -> None:
    requirements = required_host_paths(_invocation(tmp_path, caddy=False), root=tmp_path)
    assert not any("Caddyfile" in str(r.path) for r in requirements)


def test_prepare_creates_directories_with_modes(tmp_path: Path) -> None:
    requirements = required_host_paths(_invocation(tmp_path), root=tmp_path)
    prepare_host_paths([r for r in requirements if r.kind == "dir"])
    config_dir = tmp_path / "apps" / "api" / "config"
    assert config_dir.is_dir()
    if sys.platform != "win32":
        assert (config_dir.stat().st_mode & 0o777) == 0o700


def test_type_mismatch_fails_before_compose(tmp_path: Path) -> None:
    (tmp_path / "apps" / "api").mkdir(parents=True)
    (tmp_path / "apps" / "api" / "config").write_text("i am a file", encoding="utf-8")
    requirements = required_host_paths(_invocation(tmp_path), root=tmp_path)
    with pytest.raises(HostPathError) as excinfo:
        prepare_host_paths([r for r in requirements if r.kind == "dir"])
    assert str(excinfo.value).startswith("host_path_type_mismatch:")


def test_missing_required_file_fails_closed(tmp_path: Path) -> None:
    requirements = required_host_paths(_invocation(tmp_path, caddy=True), root=tmp_path)
    files_only = [r for r in requirements if r.kind == "file"]
    with pytest.raises(HostPathError) as excinfo:
        prepare_host_paths(files_only)
    assert str(excinfo.value).startswith("host_path_missing_file:")
