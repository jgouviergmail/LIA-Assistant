#!/usr/bin/env python3
"""``CLAUDE.md`` is read whole at every session, so its size is a stated budget.

Why
---
The file opens every Claude Code session and is mirrored into ``AGENTS.md``: each
line costs every session, and a long entry buries the rule it carries. The instruction
to keep additions short lived in prose and did not hold: about 250,000 characters on
2026-09-27, 281,464 bytes on 2026-11-03, one bullet of 12,415 characters, and Codex
reading only the first 32,768 bytes (measured on its session logs, 2026-10-31).

Contract
--------
Three checks, read from ``scripts/audit/claude_md_budget.json``:

* the file stays under ``max_bytes``;
* no block exceeds ``block_max_chars``, unless ``long_blocks`` admits it with a written
  reason and at no more than its recorded length. A block is a list item with its
  continuation lines, or a paragraph; code fences, tables and headings are not blocks;
* ``default_window.heading`` starts within ``default_window.bytes``: what Codex reads
  on a default configuration holds the commands, the conduct and the principles.
  The check is on the order, so a repair moves a section rather than cuts one.

The first two stop silent growth, never a justified addition. Lifting either takes one
command and one sentence, and the sentence stays in the baseline for the reviewer:

    task docs:budget -- --raise "<why this addition earns its place>"
    task docs:budget -- --allow "<start of the block>" "<why it cannot be shorter>"

``--update`` is the other direction: it lowers the ceiling to the measured size plus
``headroom_bytes``, lowers each recorded length and removes the entries that no longer
apply. It never raises anything.

Usage (from the repository root):
    python scripts/audit/claude_md_budget.py [REPO_ROOT]
        [--update | --raise REASON | --allow START REASON]

Standard library only. Imports its sibling ``doc_audit`` by name: run from
``scripts/audit/`` as a script, Python puts that directory first on the path.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from doc_audit import blank_fenced_blocks

__all__ = [
    "BASELINE_REL",
    "SOURCE",
    "Block",
    "Outcome",
    "allow_block",
    "blocks_of",
    "check",
    "load_budget",
    "raise_ceiling",
    "update",
]

SOURCE = "CLAUDE.md"
BASELINE_REL = "scripts/audit/claude_md_budget.json"

#: Characters of a block's text that identify it in ``long_blocks``.
START_CHARS = 60
#: A reason is a sentence for a reviewer, never a token typed to get past the check.
MIN_REASON_CHARS = 20

_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")


@dataclass(frozen=True)
class Block:
    """A list item with its continuation lines, or a paragraph."""

    line: int
    text: str

    @property
    def start(self) -> str:
        """The opening that identifies the block."""
        return self.text[:START_CHARS]


@dataclass(frozen=True)
class Outcome:
    """What the check found."""

    size: int
    ceiling: int
    problems: tuple[str, ...]


def blocks_of(text: str) -> list[Block]:
    """Split a Markdown document into its blocks.

    Args:
        text: The document.

    Returns:
        Every list item and paragraph, in order, with single spaces at line joins.
    """
    found: list[Block] = []
    current: list[str] = []
    start = 0

    def flush() -> None:
        nonlocal current
        if current:
            found.append(Block(start, " ".join(part.strip() for part in current)))
            current = []

    for number, line in enumerate(blank_fenced_blocks(text).split("\n"), 1):
        if not line.strip() or line.startswith("#") or line.lstrip().startswith("|"):
            flush()
        elif _LIST_ITEM.match(line):
            flush()
            start, current = number, [line]
        else:
            if not current:
                start = number
            current.append(line)
    flush()
    return found


def load_budget(root: Path) -> dict[str, Any]:
    """Read the baseline.

    Args:
        root: Repository root.

    Returns:
        The baseline.

    Raises:
        OSError: If the baseline cannot be read.
        ValueError: If it is not the expected JSON shape.
    """
    data: object = json.loads((root / BASELINE_REL).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{BASELINE_REL} must hold a JSON object")
    for key, kind in (
        ("max_bytes", int),
        ("block_max_chars", int),
        ("headroom_bytes", int),
        ("raises", list),
        ("long_blocks", list),
    ):
        if not isinstance(data.get(key), kind):
            raise ValueError(f"{BASELINE_REL}: '{key}' must be a {kind.__name__}")
    return data


def _write_budget(root: Path, budget: dict[str, Any]) -> None:
    path = root / BASELINE_REL
    path.write_text(
        json.dumps(budget, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _measure(root: Path) -> tuple[int, list[Block]]:
    raw = (root / SOURCE).read_bytes()
    return len(raw), blocks_of(raw.decode("utf-8"))


def check(root: Path) -> Outcome:
    """Compare ``CLAUDE.md`` with its budget.

    Args:
        root: Repository root.

    Returns:
        The size, the ceiling, and one sentence per problem, each naming its repair.
    """
    budget = load_budget(root)
    size, blocks = _measure(root)
    cap = budget["block_max_chars"]
    problems: list[str] = []
    if size > budget["max_bytes"]:
        problems.append(
            f"{SOURCE} is {size} bytes, over its ceiling of {budget['max_bytes']}. Move the "
            "detail to its ADR; if the addition earns its place: "
            'task docs:budget -- --raise "<why>"'
        )
    admitted = {entry["starts"]: entry for entry in budget["long_blocks"]}
    long_starts = set()
    for block in blocks:
        if len(block.text) <= cap:
            continue
        long_starts.add(block.start)
        entry = admitted.get(block.start)
        if entry is None:
            problems.append(
                f"{SOURCE}:{block.line} is a block of {len(block.text)} characters (cap {cap}): "
                f"«{block.start}…». Keep the rule, what enforces it and the ADR; if it cannot "
                'be shorter: task docs:budget -- --allow "<start>" "<why>"'
            )
        elif len(block.text) > entry["chars"]:
            problems.append(
                f"{SOURCE}:{block.line} grew to {len(block.text)} characters, past the "
                f"{entry['chars']} admitted: «{block.start}…». Condense it, or state why: "
                'task docs:budget -- --allow "<start>" "<why>"'
            )
    for start in sorted(set(admitted) - long_starts):
        problems.append(
            f"long_blocks entry no longer applies: «{start}…». "
            "Lock the gain: task docs:budget -- --update"
        )
    problems.extend(_window_problems(root, budget))
    return Outcome(size, budget["max_bytes"], tuple(problems))


def _window_problems(root: Path, budget: dict[str, Any]) -> list[str]:
    """Say whether the heading a default Codex must reach starts inside its window."""
    window = budget.get("default_window")
    if window is None:
        return []
    raw = (root / SOURCE).read_bytes()
    offset = raw.find(f"\n{window['heading']}\n".encode())
    if offset == -1:
        return [
            f"default_window names «{window['heading']}», absent from {SOURCE}: "
            f"name the heading a default Codex must reach in {BASELINE_REL}"
        ]
    if offset > window["bytes"]:
        return [
            f"«{window['heading']}» starts at byte {offset}, past the {window['bytes']} a "
            "default Codex reads. Move it up, or shorten what precedes it."
        ]
    return []


def update(root: Path) -> list[str]:
    """Tighten the budget to what was measured; never loosen it.

    Args:
        root: Repository root.

    Returns:
        One line per change.
    """
    budget = load_budget(root)
    size, blocks = _measure(root)
    cap = budget["block_max_chars"]
    changes: list[str] = []
    ceiling = min(budget["max_bytes"], size + budget["headroom_bytes"])
    if ceiling < budget["max_bytes"]:
        changes.append(f"ceiling {budget['max_bytes']} -> {ceiling}")
        budget["max_bytes"] = ceiling
    lengths = {block.start: len(block.text) for block in blocks if len(block.text) > cap}
    kept = []
    for entry in budget["long_blocks"]:
        measured = lengths.get(entry["starts"])
        if measured is None:
            changes.append(f"removed «{entry['starts']}…»")
            continue
        if measured < entry["chars"]:
            changes.append(f"«{entry['starts']}…» {entry['chars']} -> {measured}")
            entry["chars"] = measured
        kept.append(entry)
    budget["long_blocks"] = kept
    _write_budget(root, budget)
    return changes


def _require_reason(reason: str) -> None:
    if len(reason.strip()) < MIN_REASON_CHARS:
        raise ValueError(f"a reason is a sentence of at least {MIN_REASON_CHARS} characters")


def raise_ceiling(root: Path, reason: str) -> int:
    """Lift the ceiling for a justified addition, recording why.

    Args:
        root: Repository root.
        reason: Why the addition earns its place.

    Returns:
        The new ceiling.

    Raises:
        ValueError: If the reason is too short, or the ceiling already leaves the headroom.
    """
    _require_reason(reason)
    budget = load_budget(root)
    size, _ = _measure(root)
    ceiling: int = size + budget["headroom_bytes"]
    if ceiling <= budget["max_bytes"]:
        raise ValueError(
            f"nothing to raise: {size} bytes against a ceiling of {budget['max_bytes']}"
        )
    budget["raises"].append(
        {
            "date": datetime.now(UTC).date().isoformat(),
            "from": budget["max_bytes"],
            "to": ceiling,
            "reason": reason.strip(),
        }
    )
    budget["max_bytes"] = ceiling
    _write_budget(root, budget)
    return ceiling


def allow_block(root: Path, start: str, reason: str) -> Block:
    """Admit a long block at its current length, recording why.

    Args:
        root: Repository root.
        start: The opening of the block.
        reason: Why it cannot be shorter.

    Returns:
        The admitted block.

    Raises:
        ValueError: If the reason is too short, or no block over the cap opens that way.
    """
    _require_reason(reason)
    budget = load_budget(root)
    _, blocks = _measure(root)
    cap = budget["block_max_chars"]
    matches = [b for b in blocks if len(b.text) > cap and b.text.startswith(start)]
    if len(matches) != 1:
        raise ValueError(f"{len(matches)} blocks over the cap open with «{start}»; expected one")
    block = matches[0]
    kept = [entry for entry in budget["long_blocks"] if entry["starts"] != block.start]
    kept.append({"starts": block.start, "chars": len(block.text), "reason": reason.strip()})
    budget["long_blocks"] = kept
    _write_budget(root, budget)
    return block


def main(argv: list[str]) -> int:
    """Check the budget, or apply one of its three transitions."""
    # A message quotes the file, and a Windows console's code page cannot carry
    # every character of it: an arrow would end the run on an encoding error.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("root", nargs="?", default=".", help="repository root")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--update", action="store_true", help="tighten; never loosens")
    action.add_argument("--raise", dest="raise_reason", metavar="REASON", help="lift the ceiling")
    action.add_argument("--allow", nargs=2, metavar=("START", "REASON"), help="admit a long block")
    args = parser.parse_args(argv[1:])
    root = Path(args.root).resolve()

    try:
        if args.update:
            changes = update(root)
            print("\n".join(changes) if changes else "claude_md_budget: nothing to tighten")
            return 0
        if args.raise_reason is not None:
            print(f"claude_md_budget: ceiling now {raise_ceiling(root, args.raise_reason)} bytes")
            return 0
        if args.allow is not None:
            block = allow_block(root, args.allow[0], args.allow[1])
            print(
                f"claude_md_budget: admitted {SOURCE}:{block.line} at {len(block.text)} characters"
            )
            return 0
        outcome = check(root)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(f"claude_md_budget: {outcome.size} of {outcome.ceiling} bytes")
    if outcome.problems:
        for problem in outcome.problems:
            print(f"error: {problem}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
