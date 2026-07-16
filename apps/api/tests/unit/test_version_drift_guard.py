"""Systemic guard against release-version drift across manifests (audit F030).

The application version has a single source of truth: the root ``package.json``
(``apps/web/src/lib/version.ts`` re-exports ``pkg.version``). The backend's
``apps/api/pyproject.toml`` must carry the *same* version — the 2026-07 audit
found it stranded at 1.21.9 while the shipped version was already 1.23.13+,
because ``pyproject.toml`` was not on the release-bump surface list and nothing
enforced parity.

This guard fails the build whenever the three manifests disagree, so a release
that bumps ``package.json`` without ``pyproject.toml`` (or vice versa) cannot
merge. Paths are resolved from ``__file__`` so the check is CWD-independent
(lesson from F023). Keep ``pyproject.toml`` in the release surfaces.
"""

import json
import tomllib
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

API_ROOT = Path(__file__).parents[2]  # apps/api (tests/unit/<file> → api)
REPO_ROOT = repo_root_or_skip()  # repo root (api → apps → repo)

PYPROJECT = API_ROOT / "pyproject.toml"
ROOT_PACKAGE_JSON = REPO_ROOT / "package.json"
WEB_PACKAGE_JSON = REPO_ROOT / "apps" / "web" / "package.json"


def _pyproject_version() -> str:
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def _package_json_version(path: Path) -> str:
    return json.loads(path.read_text(encoding="utf-8"))["version"]


def test_version_is_consistent_across_manifests():
    """pyproject.toml and both package.json files must declare the same version."""
    versions = {
        "apps/api/pyproject.toml": _pyproject_version(),
        "package.json": _package_json_version(ROOT_PACKAGE_JSON),
        "apps/web/package.json": _package_json_version(WEB_PACKAGE_JSON),
    }
    unique = set(versions.values())
    assert len(unique) == 1, (
        "Release-version drift across manifests (F030). All must match "
        "the single source of truth (root package.json):\n"
        + "\n".join(f"  {name}: {ver}" for name, ver in versions.items())
    )


def test_version_is_semver_like():
    """The canonical version is a dotted numeric string (defensive sanity check)."""
    version = _package_json_version(ROOT_PACKAGE_JSON)
    parts = version.split(".")
    assert len(parts) == 3 and all(
        p.isdigit() for p in parts
    ), f"Unexpected version format in root package.json: {version!r}"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
