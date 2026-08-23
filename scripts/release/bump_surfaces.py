#!/usr/bin/env python3
"""Bump every mechanical release surface, and report the editorial remainder.

A LIA release touches two kinds of surfaces. The *mechanical* ones — the version
in six manifests and eighteen guide stamps, the ADR and CHANGELOG counts quoted
on public pages — are derivable and therefore belong to a tool. The *editorial*
ones — the CHANGELOG entry, the FAQ changelog, the README theme sentence, the
measured test count — carry meaning a machine cannot produce.

Historically both were done by hand from a checklist, and the mechanical half is
where every silent drift came from (``story.*`` at v1.21.17, ``GETTING_STARTED``
at v1.21.21, ``pyproject.toml`` at 1.21.9, ``LANDING_STATS.adrs`` at 183 for
five releases). This script owns that half and *names* the other, so what is
left to a human is explicit instead of remembered.

The surface table lives in :mod:`scripts.release.version_surfaces` and is shared
with the CI guard ``test_version_surface_consistency_guard.py``: what this
writes is exactly what CI verifies.

Usage::

    python scripts/release/bump_surfaces.py --check
    python scripts/release/bump_surfaces.py 1.32.0
    python scripts/release/bump_surfaces.py 1.32.0 --last-updated now
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.version_surfaces import (  # noqa: E402
    SurfaceError,
    UnknownStampError,
    bump_version_surfaces,
    canonical_version,
    count_occurrences,
    derived_counts,
    read_last_updated,
    set_last_updated,
    sync_derived_counts,
    version_occurrences,
)

#: Surfaces this tool deliberately does not write, named so the operator can
#: see what remains rather than trusting memory. Order = the order a release
#: naturally does them.
EDITORIAL_REMAINDER: tuple[str, ...] = (
    "CHANGELOG.md — the technical entry (Added/Changed/Fixed/Tests)",
    "FAQ changelog — faq.changelog.versions.vX_Y_Z in the 6 locales, plus the "
    "key wired in changelogVersionKeys",
    "README.md — the release theme sentence and its date (the version number "
    "itself is already bumped)",
    "LANDING_STATS.tests — a real measurement (pytest --collect-only + vitest "
    "list), never derived: a count shown to the user is exact or it does not "
    "exist",
    "Showcase surfaces (landing, why/how/story prose, docs/knowledge) — update "
    "only what actually drifted; they are not changelogs",
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse the command line.

    Args:
        argv: Argument vector without the program name.

    Returns:
        The parsed namespace.

    Raises:
        SystemExit: On an invalid or ambiguous invocation.
    """
    parser = argparse.ArgumentParser(
        prog="bump_surfaces",
        description="Bump every mechanical release surface (version + derived counts).",
    )
    parser.add_argument(
        "version",
        nargs="?",
        help="Target version, e.g. 1.32.0. Omit it with --check.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report drift and exit non-zero; write nothing.",
    )
    parser.add_argument(
        "--counts-only",
        action="store_true",
        help=(
            "Realign the derived counts (ADR files, latest ADR, CHANGELOG "
            "entries) with their source, leaving the version untouched."
        ),
    )
    parser.add_argument(
        "--last-updated",
        metavar="ISO|now",
        help=(
            "Landing hero timestamp (YYYY-MM-DDTHH:MM:SS), or 'now'. "
            "Left untouched when omitted."
        ),
    )
    parser.add_argument(
        "--allow-downgrade",
        action="store_true",
        help="Permit a target version lower than the current one (rollback).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root (defaults to the checkout this script lives in).",
    )
    args = parser.parse_args(argv)

    if args.check and args.version:
        parser.error("--check takes no version argument")
    if args.counts_only and args.version:
        parser.error("--counts-only takes no version argument")
    if args.check and args.counts_only:
        parser.error("--check and --counts-only are mutually exclusive")
    if not (args.check or args.counts_only) and not args.version:
        parser.error("a target version is required (or use --check / --counts-only)")
    return args


def _semver_tuple(version: str) -> tuple[int, int, int]:
    """Return the comparable form of a validated semver string."""
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def _report_drift(root: Path) -> list[str]:
    """Collect every misaligned surface as human-readable lines.

    An unclassified guide stamp is reported as drift, not as a tool failure:
    for the operator it means "this release is not ready", exactly like a stale
    stamp, and it is the same verdict the CI guard produces.

    Args:
        root: Repository root.

    Returns:
        One line per drifting surface; empty when everything is aligned.
    """
    canonical = canonical_version(root)
    lines: list[str] = []
    try:
        lines.extend(
            f"  {item.path}:{item.line} — {item.label} carries {item.version}, "
            f"canonical is {canonical}"
            for item in version_occurrences(root)
            if item.version != canonical
        )
    except UnknownStampError as error:
        lines.append(f"  {error}")

    counts = derived_counts(root)
    lines.extend(
        f"  {item.path}:{item.line} — {item.label} quotes {item.value}, "
        f"source {item.source} is {counts[item.source]}"
        for item in count_occurrences(root)
        if item.value != counts[item.source]
    )
    return lines


def _resolve_timestamp(value: str | None, now: str | None) -> str | None:
    """Resolve ``--last-updated`` to a literal timestamp.

    ``now`` is injectable so the tool stays deterministic under test; the clock
    is read only when the operator explicitly asks for it.

    Args:
        value: The raw flag value (``None``, an ISO string, or ``"now"``).
        now: Injected clock value used when ``value == "now"``.

    Returns:
        The timestamp to write, or ``None`` to leave the surface untouched.
    """
    if value is None:
        return None
    if value != "now":
        return value
    # Local wall-clock on purpose: this is the human-facing "last updated"
    # shown on the landing hero, not a stored instant.
    return now if now is not None else datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def main(argv: list[str] | None = None, *, now: str | None = None) -> int:
    """Run the bump or the check.

    Args:
        argv: Argument vector without the program name.
        now: Injected clock for ``--last-updated now`` (tests).

    Returns:
        ``0`` on success, ``1`` on detected drift (``--check``), ``2`` on a
        refused or impossible operation.
    """
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    root: Path = args.root

    try:
        if args.check:
            drift = _report_drift(root)
            if drift:
                print("Release surfaces are NOT aligned:")
                print("\n".join(drift))
                print("\nFix with: task release:bump -- <version>")
                return 1
            print(
                f"Release surfaces are aligned at {canonical_version(root)} "
                f"(landing timestamp: {read_last_updated(root)})."
            )
            return 0

        if args.counts_only:
            realigned = sync_derived_counts(root)
            if realigned:
                print("Derived counts realigned. Files written:")
                for path in realigned:
                    print(f"  {path}")
            else:
                print("Every quoted count already matches its source; nothing to write.")
            return 0

        target: str = args.version
        current = canonical_version(root)
        try:
            if _semver_tuple(target) < _semver_tuple(current):
                if not args.allow_downgrade:
                    print(
                        f"Refusing to downgrade {current} -> {target}. "
                        "Pass --allow-downgrade if this is a deliberate rollback."
                    )
                    return 2
        except ValueError:
            print(f"Not a semver-like version: {target!r} (expected X.Y.Z)")
            return 2

        # Validate BOTH halves before the first write: a bump that rewrote 25
        # version surfaces and then died on a malformed count surface leaves a
        # half-done release, which is harder to spot than one that never ran.
        count_occurrences(root)

        changed = bump_version_surfaces(root, target)
        changed.extend(path for path in sync_derived_counts(root) if path not in changed)

        timestamp = _resolve_timestamp(args.last_updated, now)
        if timestamp is not None and set_last_updated(root, timestamp):
            changed.append("apps/web/src/lib/version.ts")

    except (SurfaceError, FileNotFoundError, ValueError) as error:
        print(str(error))
        return 2

    if changed:
        print(f"Bumped to {target}. Files written:")
        for path in sorted(changed):
            print(f"  {path}")
    else:
        print(f"Every mechanical surface already carries {target}; nothing to write.")

    print("\nStill yours to write (this tool does not invent content):")
    for item in EDITORIAL_REMAINDER:
        print(f"  - {item}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
