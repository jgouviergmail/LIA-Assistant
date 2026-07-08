"""Guard: verify the compiled Python lockfiles are consistent with their manifests.

Fails (exit 1) when ``apps/api/requirements.txt`` or ``requirements-dev.txt``
changed without regenerating the lockfiles via ``task deps:lock``:

1. every manifest requirement must be pinned in its lockfile;
2. the pinned version must satisfy the manifest specifier (a bumped or
   tightened pin without regeneration fails here);
3. every pin of ``requirements.lock.txt`` must appear with the same version in
   ``requirements-dev.lock.txt`` (layering invariant: the dev lock is compiled
   with ``-c requirements.lock.txt``, so a stale dev lock fails here).

The check is fully offline and deterministic: it never queries an index, so
new upstream releases can never make it flaky. Requires only ``packaging``.

Usage: ``python scripts/check_requirements_lock.py`` (repo root or anywhere).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

API_DIR = Path(__file__).resolve().parent.parent / "apps" / "api"

# Pinned line of a compiled lockfile: `name[extras]==version [; marker] [\]`
_LOCK_PIN_RE = re.compile(r"^([A-Za-z0-9_.\-]+)(?:\[[^\]]+\])?==([^ ;\\]+)")
# Inline comment: `#` preceded by whitespace (pip requirements syntax)
_INLINE_COMMENT_RE = re.compile(r"\s+#.*$")


def parse_manifest(path: Path) -> list[Requirement]:
    """Parse a requirements manifest into requirement objects.

    Args:
        path: Manifest file (may contain comments, blank lines, ``-r`` lines).

    Returns:
        Parsed requirements, in file order. Option lines (``-r``, ``-c``,
        ``--hash``, ...) and comments are skipped.
    """
    requirements: list[Requirement] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = _INLINE_COMMENT_RE.sub("", raw).strip()
        if not line or line.startswith(("#", "-")):
            continue
        try:
            requirements.append(Requirement(line))
        except InvalidRequirement as exc:
            print(f"::error file={path}::unparseable requirement {line!r}: {exc}")
            sys.exit(1)
    return requirements


def parse_lock(path: Path) -> dict[str, set[str]]:
    """Parse a compiled lockfile into ``{canonical name: {versions}}``.

    A name can map to several versions when universal resolution forks a
    package across disjoint environment markers.
    """
    pins: dict[str, set[str]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        match = _LOCK_PIN_RE.match(raw)
        if match:
            pins.setdefault(canonicalize_name(match.group(1)), set()).add(match.group(2))
    return pins


def check_manifest_against_lock(manifests: list[Path], lock_path: Path, errors: list[str]) -> None:
    """Ensure every manifest requirement is satisfied by a pin of the lock."""
    pins = parse_lock(lock_path)
    for manifest in manifests:
        for req in parse_manifest(manifest):
            name = canonicalize_name(req.name)
            versions = pins.get(name)
            if not versions:
                errors.append(
                    f"{manifest.name}: '{req}' is missing from {lock_path.name} "
                    f"— run 'task deps:lock'"
                )
                continue
            if not any(req.specifier.contains(v, prereleases=True) for v in versions):
                errors.append(
                    f"{manifest.name}: '{req}' is not satisfied by "
                    f"{lock_path.name} ({name}=={', '.join(sorted(versions))}) "
                    f"— run 'task deps:lock'"
                )


def check_layering(runtime_lock: Path, dev_lock: Path, errors: list[str]) -> None:
    """Ensure every runtime pin appears identically in the dev lock."""
    runtime_pins = parse_lock(runtime_lock)
    dev_pins = parse_lock(dev_lock)
    for name, versions in sorted(runtime_pins.items()):
        missing = versions - dev_pins.get(name, set())
        if missing:
            errors.append(
                f"{dev_lock.name}: {name}=={', '.join(sorted(missing))} "
                f"(pinned in {runtime_lock.name}) is absent or diverges "
                f"— run 'task deps:lock'"
            )


def main() -> int:
    """Run all lockfile consistency checks and report GitHub-style errors."""
    runtime_manifest = API_DIR / "requirements.txt"
    dev_manifest = API_DIR / "requirements-dev.txt"
    runtime_lock = API_DIR / "requirements.lock.txt"
    dev_lock = API_DIR / "requirements-dev.lock.txt"

    for path in (runtime_manifest, dev_manifest, runtime_lock, dev_lock):
        if not path.exists():
            print(f"::error::{path} not found")
            return 1

    errors: list[str] = []
    check_manifest_against_lock([runtime_manifest], runtime_lock, errors)
    # requirements-dev.txt starts with `-r requirements.txt`, so the dev lock
    # must satisfy both manifests.
    check_manifest_against_lock([runtime_manifest, dev_manifest], dev_lock, errors)
    check_layering(runtime_lock, dev_lock, errors)

    if errors:
        for error in errors:
            print(f"::error::{error}")
        return 1

    print(f"Lockfiles are in sync with their manifests " f"({runtime_lock.name}, {dev_lock.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
