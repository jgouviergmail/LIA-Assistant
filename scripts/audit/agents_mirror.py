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

``--staged`` judges the pair the git index holds, for the pre-commit hook: what a
commit carries is not what the working copy says, and a mirror regenerated but not
staged would still leave stale. It never writes: a regeneration there would silently
erase an edit made to ``AGENTS.md`` by an agent that reads that file.

Usage (from the repo root):
    python scripts/audit/agents_mirror.py [REPO_ROOT] [--fix | --staged]

Standard library only — no dependencies.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

__all__ = [
    "MirrorError",
    "SOURCE",
    "MIRROR",
    "render_mirror",
    "mirror_is_current",
    "staged_mirror_is_current",
    "write_mirror",
]

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


def _render(source_text: str) -> str:
    """Build a mirror from a source: the header, then everything from its first section.

    Copying the body VERBATIM is only correct because both files sit at the
    repository root: every relative link and code path in ``CLAUDE.md``
    resolves from the same base in ``AGENTS.md``. Moving either file out of the
    root would silently break every link in the mirror, which is why
    :data:`SOURCE` and :data:`MIRROR` are bare filenames and a guard asserts
    they stay that way.

    Args:
        source_text: The content of ``CLAUDE.md``.

    Returns:
        The exact expected content of ``AGENTS.md``.

    Raises:
        MirrorError: If the source contains no ``## `` section, which would
            silently produce an empty mirror that "matches".
    """
    # A document may open directly on a section; ``find("\n## ")`` would miss it.
    if source_text.startswith("## "):
        return _HEADER + "\n" + source_text
    marker = source_text.find("\n## ")
    if marker == -1:
        raise MirrorError(f"{SOURCE} has no '## ' section: nothing to mirror")
    return _HEADER + "\n" + source_text[marker + 1 :]


def render_mirror(root: Path) -> str:
    """Build the exact expected content of ``AGENTS.md`` from the working copy.

    Args:
        root: Repository root.

    Returns:
        The render.

    Raises:
        MirrorError: If the source is absent or has no ``## `` section.
    """
    source = root / SOURCE
    if not source.is_file():
        raise MirrorError(f"source of truth missing: {SOURCE}")
    return _render(source.read_text(encoding="utf-8"))


def mirror_is_current(root: Path) -> bool:
    """True when ``AGENTS.md`` on disk equals :func:`render_mirror`."""
    mirror = root / MIRROR
    if not mirror.is_file():
        return False
    return mirror.read_text(encoding="utf-8") == render_mirror(root)


def _staged_text(root: Path, name: str) -> str:
    """Read a file as the git index holds it, which ``GIT_INDEX_FILE`` may redirect.

    Args:
        root: Repository root.
        name: The file, relative to the root.

    Returns:
        Its content in the index.

    Raises:
        MirrorError: If the index does not hold it.
    """
    shown = subprocess.run(["git", "show", f":{name}"], cwd=root, capture_output=True, check=False)
    if shown.returncode != 0:
        raise MirrorError(f"{name} is not in the git index")
    return shown.stdout.decode("utf-8")


def staged_mirror_is_current(root: Path) -> bool:
    """True when the index holds ``AGENTS.md`` as the render of its own ``CLAUDE.md``.

    Args:
        root: Repository root.

    Returns:
        Whether the pair a commit would carry agrees.

    Raises:
        MirrorError: If the index lacks either file, or the source has no section.
    """
    return _staged_text(root, MIRROR) == _render(_staged_text(root, SOURCE))


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
        if "--staged" in argv:
            if staged_mirror_is_current(root):
                print(f"The staged {MIRROR} is in sync with the staged {SOURCE}.")
                return 0
            print(
                f"error: the staged {MIRROR} is not the render of the staged {SOURCE}. "
                f"A rule changed in {SOURCE}: run `task docs:sync-agents`, then "
                f"`git add {MIRROR}`. {MIRROR} edited by hand: move the change into "
                f"{SOURCE} first, or the regeneration erases it.",
                file=sys.stderr,
            )
            return 1
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
