#!/usr/bin/env python3
"""``AGENTS.md`` is a generated mirror of ``CLAUDE.md`` — never a second copy.

Why
---
Both files exist to tell a coding agent how to work in this repository; they
differ only in which tool reads them. Kept by hand, they drifted the way two
copies always do. Measured 2026-08-27:

* ``AGENTS.md`` held 22 sections against ``CLAUDE.md``'s 40 — a **strict
  subset**, with no content of its own;
* the 18 missing sections included the whole of **"Systemic Rules (hard-won)"**
  and **"Audit-Derived Quality Gates"** — the JSONB-mutation rule, the
  ``AsyncSession`` concurrency rule, timezone-aware UTC, the ``zh-CN`` backend
  canonical, the file-size ratchet, the empty-``except`` ban;
* it also stated a 43 % coverage floor against a real 67 %.

An agent reading the stale file does not merely lack context: it acts, and it
acts against rules the project enforces in CI. So the mirror is generated from
one source and verified, exactly as the release surfaces are.

Contract
--------
``AGENTS.md`` = a generated header + everything in ``CLAUDE.md`` from its first
``## `` heading onward, byte for byte. Only the header differs, because only the
addressed tool differs. Edit ``CLAUDE.md``; run ``task docs:sync-agents``.

Usage (from the repo root):
    python scripts/audit/agents_mirror.py [REPO_ROOT] [--fix]

Standard library only — no dependencies.
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["MirrorError", "SOURCE", "MIRROR", "render_mirror", "mirror_is_current", "write_mirror"]

SOURCE = "CLAUDE.md"
MIRROR = "AGENTS.md"

#: Header of the generated file. It names the source so a reader who opens the
#: mirror first is told where to edit, and it keeps the "check the available
#: skills" instruction the hand-written file opened with.
_HEADER = """# AGENTS.md

<!-- GENERATED FILE — do not edit.
     Source: CLAUDE.md. Regenerate with `task docs:sync-agents`.
     Verified by `task lint:docs`. -->

This file provides guidance to coding agents working in this repository. It is a
generated mirror of [CLAUDE.md](CLAUDE.md), which is the single source: the two
must never be edited separately.

Always check the available plugins/skills at session start and use the ones
relevant to the current task.
"""


class MirrorError(RuntimeError):
    """The source is missing or has no body to mirror."""


def _body(root: Path) -> str:
    """Return ``CLAUDE.md`` from its first ``## `` heading to the end.

    Copying the body VERBATIM is only correct because both files sit at the
    repository root: every relative link and code path in ``CLAUDE.md``
    resolves from the same base in ``AGENTS.md``. Moving either file out of the
    root would silently break every link in the mirror, which is why
    :data:`SOURCE` and :data:`MIRROR` are bare filenames and a guard asserts
    they stay that way.

    Args:
        root: Repository root.

    Returns:
        The mirrored body.

    Raises:
        MirrorError: If the source is absent or contains no ``## `` section —
            either would silently produce an empty mirror that "matches".
    """
    source = root / SOURCE
    if not source.is_file():
        raise MirrorError(f"source of truth missing: {SOURCE}")
    text = source.read_text(encoding="utf-8")
    # A document may open directly on a section; ``find("\n## ")`` would miss it.
    if text.startswith("## "):
        return text
    marker = text.find("\n## ")
    if marker == -1:
        raise MirrorError(f"{SOURCE} has no '## ' section: nothing to mirror")
    return text[marker + 1 :]


def render_mirror(root: Path) -> str:
    """Build the exact expected content of ``AGENTS.md``."""
    return _HEADER + "\n" + _body(root)


def mirror_is_current(root: Path) -> bool:
    """True when ``AGENTS.md`` on disk equals :func:`render_mirror`."""
    mirror = root / MIRROR
    if not mirror.is_file():
        return False
    return mirror.read_text(encoding="utf-8") == render_mirror(root)


def write_mirror(root: Path) -> None:
    """Regenerate ``AGENTS.md`` from ``CLAUDE.md``.

    Written with an explicit ``\\n`` newline so the file is byte-identical on
    Windows and Linux; a CRLF mirror would fail its own comparison in CI.
    """
    (root / MIRROR).write_text(render_mirror(root), encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    """Check (or regenerate) the mirror."""
    args = [arg for arg in argv[1:] if not arg.startswith("--")]
    root = Path(args[0]).resolve() if args else Path.cwd()

    try:
        if "--fix" in argv:
            write_mirror(root)
            print(f"{MIRROR} regenerated from {SOURCE}.")
            return 0
        if mirror_is_current(root):
            print(f"{MIRROR} is in sync with {SOURCE}.")
            return 0
    except MirrorError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(
        f"error: {MIRROR} has drifted from {SOURCE}. It is a GENERATED mirror — "
        f"edit {SOURCE}, then run `task docs:sync-agents`.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
