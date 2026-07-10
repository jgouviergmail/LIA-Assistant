#!/usr/bin/env python3
"""Ratchet the file-size baseline DOWN — never up.

The CI guard ``apps/api/tests/unit/test_file_size_ratchet_guard.py`` freezes
every logical source file at its baseline cap
(``apps/api/tests/unit/file_size_baseline.json``): files that exceeded the
global ceiling when the baseline was created are grandfathered at their audited
logical SLOC +2% margin; every other file — including every NEW file — must
stay under the global ceiling. This script is the only sanctioned way to update
the baseline, and it can only shrink it:

- lower a frozen cap to the file's current logical SLOC +2% margin;
- drop a frozen entry whose file fell back under the global ceiling;
- drop a frozen entry whose file no longer exists.

It never raises a cap and never adds an entry — a new file that outgrows the
global ceiling must be split, not frozen. Raising a cap by hand in the JSON is
an explicit, reviewable decision that requires justification in the PR.

Usage (from apps/api/, via ``task ratchet:update``):
    python ../../scripts/audit/update_file_size_baseline.py [SRC_DIR] [BASELINE_JSON]

Defaults to ./src and ./tests/unit/file_size_baseline.json. Standard library
only — no dependencies. SLOC semantics come from measure_sloc.py (single
source of truth shared with the audit protocol and the CI guard).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from measure_sloc import code_lines

# Slack over the current size, absorbing incidental diffs on frozen files
# (a bugfix adding a handful of lines, formatting shifts) without authorizing
# real growth. Must match the margin used when the baseline was created.
CAP_MARGIN = 1.02

DEFAULT_BASELINE = "tests/unit/file_size_baseline.json"


def compute_sloc(path: Path) -> int | None:
    """Logical SLOC of one file, or None when it cannot be parsed."""
    result = code_lines(path.read_text(encoding="utf-8", errors="replace"))
    return None if result is None else len(result[0])


def main(src_dir: str = "src", baseline_file: str = DEFAULT_BASELINE) -> int:
    """Lower the frozen caps of ``baseline_file`` to current sizes in ``src_dir``."""
    root = Path(src_dir)
    baseline_path = Path(baseline_file)
    if not root.is_dir():
        print(f"ERROR: source directory not found: {root.resolve()}", file=sys.stderr)
        return 1
    if not baseline_path.is_file():
        print(f"ERROR: baseline not found: {baseline_path.resolve()}", file=sys.stderr)
        return 1

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    global_max: int = baseline["global_max_sloc"]
    frozen: dict[str, int] = baseline["frozen"]

    new_frozen: dict[str, int] = {}
    lowered: list[str] = []
    dropped: list[str] = []
    for rel, cap in sorted(frozen.items()):
        path = root / rel
        if not path.is_file():
            dropped.append(f"{rel} (file deleted — cap {cap} removed)")
            continue
        sloc = compute_sloc(path)
        if sloc is None:
            print(f"WARNING: unparsable file, cap kept: {rel}", file=sys.stderr)
            new_frozen[rel] = cap
            continue
        if sloc <= global_max:
            dropped.append(
                f"{rel} (now {sloc} SLOC <= global ceiling {global_max} — entry removed)"
            )
            continue
        new_cap = min(cap, math.ceil(sloc * CAP_MARGIN))  # ratchet: caps only go down
        if new_cap < cap:
            lowered.append(f"{rel}: {cap} -> {new_cap} (current {sloc} SLOC)")
        new_frozen[rel] = new_cap

    if new_frozen == frozen:
        print(f"baseline unchanged ({len(frozen)} frozen files)")
        return 0

    baseline["frozen"] = dict(sorted(new_frozen.items()))
    baseline_path.write_text(
        json.dumps(baseline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    for line in lowered:
        print(f"lowered  {line}")
    for line in dropped:
        print(f"dropped  {line}")
    print(
        f"baseline updated: {len(lowered)} cap(s) lowered, {len(dropped)} entry(ies) "
        f"dropped, {len(new_frozen)} frozen file(s) remain"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
