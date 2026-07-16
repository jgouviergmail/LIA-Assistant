#!/usr/bin/env python3
"""Measure and ratchet the MyPy exemption surface (audit F020).

The backend runs MyPy in near-strict mode, but ``[[tool.mypy.overrides]]``
blocks with ``disable_error_code`` silently suppress ~860 real type errors
across ~280 files (34.8 % of ``src`` at the 2026-07 audit). Nothing stopped
the exemption surface from *growing*: a new module could be appended to a
disable block, or a new error code added, and no gate would notice.

This tool freezes that surface and ratchets it downward:

* the **enforced** metric is the set of ``(module, error_code)`` exemption
  pairs declared in the ``disable_error_code`` overrides. It is parsed purely
  from ``pyproject.toml`` — 100 % deterministic, identical on the Windows host
  pre-commit hook and the Linux CI runner (no MyPy run, so no host/Docker
  divergence). ``--check`` fails when a pair is present that is absent from the
  baseline (a *new* exemption); removing pairs is always allowed and the
  baseline is lowered with ``--update``.
* the **informational** metric is the actual number of MyPy errors currently
  suppressed, obtained with ``--measure-errors`` (runs MyPy with the
  ``disable_error_code`` lists stripped). It is reported and stored for
  visibility but never gates CI, precisely because absolute MyPy counts can
  drift by a unit between environments.

Third-party ``ignore_missing_imports`` overrides (unstubbed libraries) are NOT
counted — they are legitimate and unrelated to the internal typing debt.

Usage (from anywhere — paths resolve from ``__file__``):
    python scripts/audit/measure_mypy_debt.py            # report surface
    python scripts/audit/measure_mypy_debt.py --check    # ratchet gate (CI)
    python scripts/audit/measure_mypy_debt.py --update   # lower the baseline
    python scripts/audit/measure_mypy_debt.py --measure-errors  # + run MyPy

Standard library only (Python 3.11+ for ``tomllib``); ``--measure-errors``
additionally requires the ``apps/api`` virtualenv MyPy on PATH.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "apps" / "api"
PYPROJECT = API_DIR / "pyproject.toml"
BASELINE = API_DIR / ".mypy-debt-baseline.json"

Pair = tuple[str, str]


def _load_overrides() -> list[dict]:
    """Return the ``[[tool.mypy.overrides]]`` blocks from pyproject.toml."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    overrides = data.get("tool", {}).get("mypy", {}).get("overrides", [])
    return list(overrides)


def exemption_pairs() -> set[Pair]:
    """The set of ``(module, error_code)`` exemptions (the enforced metric)."""
    pairs: set[Pair] = set()
    for override in _load_overrides():
        codes = override.get("disable_error_code")
        if not codes:
            continue
        modules = override["module"]
        modules = [modules] if isinstance(modules, str) else modules
        for module in modules:
            for code in codes:
                pairs.add((module, code))
    return pairs


def exempted_modules() -> set[str]:
    """Distinct modules carrying at least one ``disable_error_code``."""
    return {module for module, _code in exemption_pairs()}


def _pairs_to_json(pairs: set[Pair]) -> list[list[str]]:
    return [list(p) for p in sorted(pairs)]


def _json_to_pairs(raw: list[list[str]]) -> set[Pair]:
    return {(m, c) for m, c in raw}


def _files_for_module(module: str) -> set[str]:
    """Resolve a mypy module pattern to the ``src`` files it covers (for reporting).

    Handles both a trailing ``.*`` (package + all submodules, recursive) and a
    mid-pattern ``*`` segment (``src.domains.*.models`` — a single package
    level), by translating the dotted pattern to filesystem globs.
    """
    parts = module.split(".")
    recursive = parts[-1] == "*"
    if recursive:
        parts = parts[:-1]
    stem = "/".join(parts)
    results: set[str] = set()
    if recursive:
        # Package and all its submodules.
        globs = [f"{stem}.py", f"{stem}/**/*.py"]
    else:
        # A single module: either a flat file or a package directory.
        globs = [f"{stem}.py", f"{stem}/**/*.py"]
    for pattern in globs:
        for file in API_DIR.glob(pattern):
            if file.is_file():
                results.add(file.relative_to(API_DIR).as_posix())
    return results


def _measure_suppressed_errors() -> tuple[int, dict[str, int], dict[int, list[str]]]:
    """Run MyPy with ``disable_error_code`` stripped; count suppressed errors.

    Returns ``(total, by_code, unused_codes_per_block)`` where the last maps a
    block index to the disabled codes that never actually fire (safe to drop).
    """
    import re
    import tempfile

    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    mypy = data["tool"]["mypy"]
    lines = ["[mypy]"]
    for key, value in mypy.items():
        if key in ("overrides", "plugins") or isinstance(value, (list, dict)):
            continue
        lines.append(
            f"{key} = {str(value).lower() if isinstance(value, bool) else value}"
        )
    lines.append("plugins = pydantic.mypy")
    for override in mypy["overrides"]:
        modules = override["module"]
        modules = [modules] if isinstance(modules, str) else modules
        for module in modules:
            lines.append(f"[mypy-{module}]")
            for key, value in override.items():
                if key in ("module", "disable_error_code"):
                    continue
                if isinstance(value, bool):
                    lines.append(f"{key} = {str(value).lower()}")
                elif isinstance(value, str):
                    lines.append(f"{key} = {value}")

    mypy_exe = (
        API_DIR
        / ".venv"
        / ("Scripts/mypy.exe" if sys.platform == "win32" else "bin/mypy")
    )
    with tempfile.NamedTemporaryFile(
        "w", suffix=".ini", delete=False, dir=API_DIR, encoding="utf-8"
    ) as handle:
        handle.write("\n".join(lines))
        cfg_path = Path(handle.name)
    try:
        proc = subprocess.run(
            [
                str(mypy_exe),
                "src",
                "--config-file",
                str(cfg_path),
                "--no-error-summary",
            ],
            cwd=str(API_DIR),
            capture_output=True,
            text=True,
        )
    finally:
        cfg_path.unlink(missing_ok=True)

    line_re = re.compile(r"^(src[\\/][^:]+):\d+: error:.*\[([a-z-]+)\]\s*$")
    per_file: dict[str, set[str]] = defaultdict(set)
    by_code: dict[str, int] = defaultdict(int)
    total = 0
    for out_line in proc.stdout.splitlines():
        match = line_re.match(out_line)
        if not match:
            continue
        total += 1
        per_file[match.group(1).replace("\\", "/")].add(match.group(2))
        by_code[match.group(2)] += 1

    unused: dict[int, list[str]] = {}
    for index, override in enumerate(mypy["overrides"]):
        codes = override.get("disable_error_code")
        if not codes:
            continue
        modules = override["module"]
        modules = [modules] if isinstance(modules, str) else modules
        used: set[str] = set()
        for module in modules:
            for file in _files_for_module(module):
                used |= per_file.get(file, set())
        never = [c for c in codes if c not in used]
        if never:
            unused[index] = never
    return total, dict(by_code), unused


def _report(measure_errors: bool) -> None:
    pairs = exemption_pairs()
    modules = exempted_modules()
    files = set().union(*(_files_for_module(m) for m in modules)) if modules else set()
    print(f"mypy exemption surface: {len(pairs)} (module, code) pairs")
    print(f"  exempted modules = {len(modules)}")
    print(f"  covered src files = {len(files)}")
    if measure_errors:
        total, by_code, unused = _measure_suppressed_errors()
        print(f"  suppressed errors (informational) = {total}")
        print(f"  by code = {dict(sorted(by_code.items(), key=lambda kv: -kv[1]))}")
        if unused:
            print("  UNUSED disabled codes (0 errors — safe to remove):")
            for index, codes in unused.items():
                print(f"    block #{index}: {codes}")


def _check() -> int:
    if not BASELINE.exists():
        print(
            f"error: baseline missing ({BASELINE}); run --update first", file=sys.stderr
        )
        return 2
    baseline = _json_to_pairs(json.loads(BASELINE.read_text(encoding="utf-8"))["pairs"])
    current = exemption_pairs()
    added = current - baseline
    if added:
        print(
            f"::error::MyPy exemption ratchet: {len(added)} NEW exemption(s) added (F020):"
        )
        for module, code in sorted(added):
            print(f"  + [{module}] disables '{code}'")
        print("New MyPy exemptions are forbidden. Fix the type errors instead, or")
        print("if an exemption was legitimately removed elsewhere, run:")
        print("  python scripts/audit/measure_mypy_debt.py --update")
        return 1
    removed = baseline - current
    if removed:
        print(
            f"MyPy exemption surface shrank by {len(removed)} pair(s) — lower the baseline:"
        )
        print("  python scripts/audit/measure_mypy_debt.py --update")
    print(f"OK: {len(current)} exemption pairs, all within baseline ({len(baseline)}).")
    return 0


def _update() -> int:
    pairs = exemption_pairs()
    total_errors = None
    if "--measure-errors" in sys.argv:
        total_errors, _, _ = _measure_suppressed_errors()
    payload = {
        "_comment": (
            "MyPy exemption ratchet baseline (audit F020). Shrink-only: "
            "measure_mypy_debt.py --check fails on any NEW (module, code) pair. "
            "Regenerate with --update ONLY after removing exemptions."
        ),
        "exempted_modules": len(exempted_modules()),
        "suppressed_errors_informational": total_errors,
        "pairs": _pairs_to_json(pairs),
    }
    if total_errors is None:
        # Preserve any previously recorded informational count.
        if BASELINE.exists():
            prior = json.loads(BASELINE.read_text(encoding="utf-8"))
            payload["suppressed_errors_informational"] = prior.get(
                "suppressed_errors_informational"
            )
    BASELINE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"baseline written: {len(pairs)} pairs, {payload['exempted_modules']} modules"
    )
    return 0


def main(argv: list[str]) -> int:
    """CLI entry point."""
    if "--update" in argv:
        return _update()
    if "--check" in argv:
        return _check()
    _report(measure_errors="--measure-errors" in argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
