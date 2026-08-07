"""Preflight contract (B01/B05).

- mode resolution: --local-build always wins; explicit prebuilt REQUIRES a
  passed manifest; with no flag, ONLY the adjacent manifest file decides
  (absent/candidate -> local, valid passed -> prebuilt); never a parent
  search, never through a symlink;
- Compose version gate: LAN output uses `!override`, so 2.24.3 is rejected
  and 2.24.4 accepted;
- --dry-run/--check-only never call daemon checks that mutate state.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.install.model import InstallMode
from scripts.install.preflight import (
    PreflightError,
    check_compose_version,
    resolve_install_mode,
)

_DIGEST = "ab" * 32
MANIFEST_NAME = "lia-self-host-manifest.json"


def _manifest_payload(qualification: str) -> dict:
    platforms = [
        {
            "platform": platform,
            "manifest_digest": f"sha256:{_DIGEST}",
            "config_digest": f"sha256:{_DIGEST}",
        }
        for platform in ("linux/amd64", "linux/arm64")
    ]
    services = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "scripts/release/self_host_dependencies.json"
        ).read_text(encoding="utf-8")
    )
    images = [
        {
            "service": entry["service"],
            "reference": f"ghcr.io/example/lia/{entry['service']}@sha256:{_DIGEST}",
            "platforms": platforms,
        }
        for entry in ({"service": "api"}, {"service": "web"}, *services)
    ]
    return {
        "schema_version": 1,
        "release_version": "v1.28.0",
        "source_sha": "0" * 40,
        "built_at": "2026-08-06T00:00:00Z",
        "bundle_archive_sha256": _DIGEST,
        "bundle_tree_sha256": _DIGEST,
        "source_context_archive_sha256": _DIGEST,
        "source_context_tree_sha256": _DIGEST,
        "images": images,
        "sboms": {"api": _DIGEST, "web": _DIGEST},
        "qualification": qualification,
    }


def _write_manifest(root: Path, qualification: str) -> Path:
    path = root / MANIFEST_NAME
    path.write_text(json.dumps(_manifest_payload(qualification)), encoding="utf-8")
    return path


def test_explicit_local_always_wins(tmp_path: Path) -> None:
    _write_manifest(tmp_path, "passed")
    mode, manifest = resolve_install_mode(
        requested=InstallMode.LOCAL, bundle_root=tmp_path
    )
    assert mode is InstallMode.LOCAL and manifest is None


def test_no_flag_without_manifest_is_local(tmp_path: Path) -> None:
    mode, manifest = resolve_install_mode(requested=None, bundle_root=tmp_path)
    assert mode is InstallMode.LOCAL and manifest is None


def test_no_flag_with_candidate_manifest_stays_local(tmp_path: Path) -> None:
    _write_manifest(tmp_path, "candidate")
    mode, manifest = resolve_install_mode(requested=None, bundle_root=tmp_path)
    assert mode is InstallMode.LOCAL and manifest is None


def test_no_flag_with_passed_manifest_is_prebuilt(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, "passed")
    mode, manifest = resolve_install_mode(requested=None, bundle_root=tmp_path)
    assert mode is InstallMode.PREBUILT and manifest == path


def test_explicit_prebuilt_requires_a_passed_manifest(tmp_path: Path) -> None:
    _write_manifest(tmp_path, "candidate")
    with pytest.raises(PreflightError) as excinfo:
        resolve_install_mode(requested=InstallMode.PREBUILT, bundle_root=tmp_path)
    assert str(excinfo.value) == "prebuilt_requires_passed_manifest"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_a_symlinked_manifest_is_never_followed(tmp_path: Path) -> None:
    real = tmp_path / "elsewhere.json"
    real.write_text(json.dumps(_manifest_payload("passed")), encoding="utf-8")
    (tmp_path / MANIFEST_NAME).symlink_to(real)
    mode, manifest = resolve_install_mode(requested=None, bundle_root=tmp_path)
    assert mode is InstallMode.LOCAL and manifest is None


@pytest.mark.parametrize(
    ("version", "ok"),
    [("2.24.3", False), ("2.24.4", True), ("2.30.1", True), ("2.9.9", False)],
)
def test_compose_version_gate(version: str, ok: bool) -> None:
    if ok:
        check_compose_version(version)
    else:
        with pytest.raises(PreflightError) as excinfo:
            check_compose_version(version)
        assert str(excinfo.value) == "compose_version_too_old"
