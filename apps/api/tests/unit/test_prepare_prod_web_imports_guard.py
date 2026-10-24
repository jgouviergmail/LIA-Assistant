"""The web bundle must carry every module its type-checked TypeScript imports.

``scripts/deploy/prepare-prod.ps1`` stages ``apps/web`` from **hand-kept lists**:
three directories, a handful of root files, the scripts the build command runs.
The web image then runs ``next build``, which type-checks every file
``tsconfig.json`` includes -- the tests under ``src/`` among them. A relative
import that leaves the staged directories therefore needs its target staged too,
and CI cannot see the omission: its own type check runs against the whole
repository.

That is how the deployment of 2026-10-24 broke: two guard tests under
``src/__tests__`` imported ``coverage-exclusions.mjs`` and
``scripts/{decision-points,double-cast}.mjs``, every gate was green, and
``next build`` on the production host answered ``TS2307: Cannot find module``
232 s into the build.

As ``test_prepare_prod_build_context_guard.py`` derives the root paths from the
Dockerfiles, this guard derives the modules from the imports, and refuses an
entry no import needs any more.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
PREPARE_SCRIPT = REPO_ROOT / "scripts" / "deploy" / "prepare-prod.ps1"
WEB_ROOT = REPO_ROOT / "apps" / "web"
TSCONFIG = WEB_ROOT / "tsconfig.json"

# What tsconfig.json hands the type check under src/: "src/**/*.ts", "src/**/*.tsx".
_TYPE_CHECKED_GLOBS = ('"src/**/*.ts"', '"src/**/*.tsx"')
_TYPE_CHECKED_SUFFIXES = (".ts", ".tsx")
# A static, side-effect, re-export, dynamic or type-level import of a RELATIVE path.
_RELATIVE_IMPORT = re.compile(
    r"""(?:\bfrom\s+|\bimport\s*\(\s*|\bimport\s+)(['"])(?P<spec>\.\.?/[^'"]+)\1"""
)
# How the bundler resolution of tsconfig.json completes an extensionless specifier.
_RESOLUTION_SUFFIXES = (
    "",
    ".ts",
    ".tsx",
    ".d.ts",
    ".js",
    ".mjs",
    ".json",
    "/index.ts",
    "/index.tsx",
)


def _staged_list(name: str) -> list[str]:
    """The quoted entries of ``$<name> = @(...)`` in prepare-prod.ps1 (empty when absent)."""
    source = PREPARE_SCRIPT.read_text(encoding="utf-8")
    match = re.search(rf"^\${name} = @\((?P<body>.*?)\)\s*$", source, re.MULTILINE | re.DOTALL)
    return re.findall(r'"([^"]+)"', match["body"]) if match else []


def _staged_paths() -> set[str]:
    """Every file path under apps/web that the bundle stages outside its directories."""
    return (
        set(_staged_list("webFiles"))
        | {f"scripts/{name}" for name in _staged_list("webScripts")}
        | set(_staged_list("webImportedModules"))
    )


def _type_checked_files() -> list[Path]:
    """The bundle's TypeScript that ``next build`` type-checks."""
    files = sorted(
        path
        for path in (WEB_ROOT / "src").rglob("*")
        if path.suffix in _TYPE_CHECKED_SUFFIXES and path.is_file()
    )
    files += [
        WEB_ROOT / name
        for name in sorted(_staged_list("webFiles"))
        if name.endswith(_TYPE_CHECKED_SUFFIXES) and (WEB_ROOT / name).is_file()
    ]
    return files


def _relative_imports() -> list[tuple[str, str]]:
    """(importer, target) for every relative import, both relative to apps/web, posix."""
    found: list[tuple[str, str]] = []
    for file in _type_checked_files():
        importer = file.relative_to(WEB_ROOT).as_posix()
        for match in _RELATIVE_IMPORT.finditer(file.read_text(encoding="utf-8")):
            target = os.path.normpath(file.parent / match["spec"])
            found.append((importer, Path(os.path.relpath(target, WEB_ROOT)).as_posix()))
    return found


def _is_staged(target: str, staged_dirs: set[str], staged_paths: set[str]) -> bool:
    if target.split("/", 1)[0] in staged_dirs:
        return True
    return any(target + suffix in staged_paths for suffix in _RESOLUTION_SUFFIXES)


@pytest.mark.unit
def test_the_scan_still_finds_both_sides() -> None:
    """Guard against the guard rotting into a vacuous pass."""
    assert "src" in _staged_list("webDirs"), "$webDirs no longer parses from prepare-prod.ps1"
    assert "package.json" in _staged_list("webFiles"), "$webFiles no longer parses"
    assert "copy-ort-runtime.mjs" in _staged_list("webScripts"), "$webScripts no longer parses"
    tsconfig = TSCONFIG.read_text(encoding="utf-8")
    for glob in _TYPE_CHECKED_GLOBS:
        assert glob in tsconfig, f"tsconfig.json no longer includes {glob}: re-derive the scan"
    assert len(_type_checked_files()) > 100, "suspiciously few type-checked files"
    # The locales are imported from src/ by many tests: proof the resolution runs.
    assert any(target.startswith("locales/") for _, target in _relative_imports())


@pytest.mark.unit
def test_every_module_a_type_checked_file_imports_is_staged() -> None:
    staged_dirs = set(_staged_list("webDirs"))
    staged_paths = _staged_paths()
    offenders = sorted(
        {
            f"{target} <- {importer}"
            for importer, target in _relative_imports()
            if not _is_staged(target, staged_dirs, staged_paths)
        }
    )

    assert offenders == [], (
        "these modules are imported by TypeScript that `next build` type-checks, but the "
        f"bundle leaves them out, so the web image's build fails on the production host: "
        f"{offenders}. Add each one to $webImportedModules in prepare-prod.ps1."
    )


@pytest.mark.unit
def test_every_staged_module_is_still_imported() -> None:
    """An entry no type-checked file imports any more is a list that no longer follows the code."""
    imported = {
        target + suffix for _, target in _relative_imports() for suffix in _RESOLUTION_SUFFIXES
    }
    stale = [module for module in _staged_list("webImportedModules") if module not in imported]

    assert stale == [], f"$webImportedModules stages modules nothing imports any more: {stale}"
