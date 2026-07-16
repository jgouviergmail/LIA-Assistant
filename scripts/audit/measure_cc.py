#!/usr/bin/env python3
"""Reproducible cyclomatic-complexity metrics for the 360° technical audit.

Counts per-function cyclomatic complexity via AST with the STRICTEST rule set
(deliberately over-counting vs radon/lizard, so a function passing a threshold
here passes under any standard counter):

    +1 base per function
    +1 per if/elif, ternary (IfExp), for/while (incl. async), except handler,
       with/async with, assert, match case, nested def/lambda
    +1 per plain ``else:`` block (an ``elif`` is already counted as an If)
    +n-1 per boolean operator chain (``a and b or c`` = +2)
    +1 per comprehension ``for`` clause and +1 per comprehension ``if``

History note: the cycle-3 audit (2026-07-10) published CC figures from an
ad-hoc instrument that was not committed; no single mechanical rule set
reproduces all five of its reference figures exactly (this counter measures
~6% below on the calibration set, with identical ranking). This script is the
committed instrument going forward — figures from different instruments must
not be compared across cycles.

Usage (from any directory):
    python scripts/audit/measure_cc.py [SRC_DIR] [THRESHOLD]

Defaults to apps/api/src (resolved from this file's location, so the script is
CWD-independent — F023) and threshold 15. Standard library only — no dependencies.
Exit code 1 when any function meets or exceeds the threshold (usable as a
local gate for decomposition work; not wired as a CI guard).
"""

from __future__ import annotations

import ast
import statistics
import sys
from pathlib import Path

TOP_N = 15
DEFAULT_THRESHOLD = 15

# Default target resolved from this file (scripts/audit/ -> repo root -> src),
# so the script works identically from any working directory (F023).
DEFAULT_SRC_DIR: Path = Path(__file__).resolve().parents[2] / "apps" / "api" / "src"


class StrictComplexityVisitor(ast.NodeVisitor):
    """Accumulate strict cyclomatic complexity over one function body."""

    def __init__(self) -> None:
        self.cc = 1

    def visit_If(self, node: ast.If) -> None:
        self.cc += 1
        # +1 for a plain `else:` block; an elif is a nested If in orelse and
        # is counted by its own visit.
        if node.orelse and not (
            len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If)
        ):
            self.cc += 1
        self.generic_visit(node)

    def _plus_one(self, node: ast.AST) -> None:
        self.cc += 1
        self.generic_visit(node)

    visit_For = _plus_one
    visit_AsyncFor = _plus_one
    visit_While = _plus_one
    visit_With = _plus_one
    visit_AsyncWith = _plus_one
    visit_ExceptHandler = _plus_one
    visit_IfExp = _plus_one
    visit_Assert = _plus_one
    visit_match_case = _plus_one
    visit_FunctionDef = _plus_one
    visit_AsyncFunctionDef = _plus_one
    visit_Lambda = _plus_one

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.cc += len(node.values) - 1
        self.generic_visit(node)

    def _comprehension(self, node: ast.AST) -> None:
        for generator in node.generators:  # type: ignore[attr-defined]
            self.cc += 1 + len(generator.ifs)
        self.generic_visit(node)

    visit_ListComp = _comprehension
    visit_SetComp = _comprehension
    visit_DictComp = _comprehension
    visit_GeneratorExp = _comprehension


def function_cc(fn_node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Strict cyclomatic complexity of one function, nested defs included."""
    visitor = StrictComplexityVisitor()
    visitor.generic_visit(fn_node)
    return visitor.cc


def main(
    src_dir: str | Path = DEFAULT_SRC_DIR, threshold: int = DEFAULT_THRESHOLD
) -> int:
    """Measure and print per-function CC for every Python file in ``src_dir``."""
    root = Path(src_dir)
    if not root.is_dir():
        print(f"ERROR: source directory not found: {root.resolve()}", file=sys.stderr)
        return 1

    functions: list[tuple[int, str, str]] = []  # (cc, path, qualified name)
    unparsable: list[str] = []

    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            unparsable.append(str(path))
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append((function_cc(node), str(path), node.name))

    if not functions:
        print("no functions found", file=sys.stderr)
        return 1

    values = sorted((cc for cc, _, _ in functions), reverse=True)
    over = [f for f in functions if f[0] >= threshold]

    print(f"functions={len(functions)} unparsable={len(unparsable)}")
    print(
        f"cc: median={statistics.median(values):.0f} "
        f"p90={values[len(values) // 10]} max={values[0]}"
    )
    print(f"functions >= CC {threshold}: {len(over)}")

    print(f"\ntop {TOP_N} functions (strict AST cyclomatic complexity):")
    for cc, path, name in sorted(functions, reverse=True)[:TOP_N]:
        print(f"  {cc:5d}  {path}::{name}")

    if unparsable:
        print("\nWARNING — unparsable files (excluded from metrics):", file=sys.stderr)
        for path in unparsable:
            print(f"  {path}", file=sys.stderr)

    return 1 if over else 0


def cc_stats(
    src_dir: str | Path = DEFAULT_SRC_DIR, threshold: int = DEFAULT_THRESHOLD
) -> dict:
    """Aggregate CC stats: ``{over, max, threshold}`` (over = count >= threshold)."""
    root = Path(src_dir)
    functions: list[int] = []
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(function_cc(node))
    over = sum(1 for c in functions if c >= threshold)
    return {
        "over": over,
        "max": max(functions) if functions else 0,
        "threshold": threshold,
    }


# Backend complexity ratchet (audit F011/F015): monotone-decreasing caps on the
# number of functions at/over the threshold AND on the single worst function.
CC_BASELINE: Path = (
    Path(__file__).resolve().parents[2] / "apps" / "api" / ".cc-baseline.json"
)


_RATCHET_KEYS = ("over", "max", "threshold")


def ratchet_verdict(cur: dict, base: dict) -> dict:
    """Single source of truth for the CC ratchet verdict (audit F046).

    Both the ``--check-ratchet`` CLI and the guard tests call THIS function, so
    the two entrypoints can never disagree on whether a given ``(cur, base)`` is
    conformant. The tolerant policy (F046, see ``test_cc_ratchet_guard``): only a
    **regression** blocks; an **improvement** is accepted with a non-blocking
    advisory to tighten the baseline.

    Args:
        cur: Current stats ``{"over", "max", "threshold"}`` (from ``cc_stats``).
        base: Frozen baseline with the same keys.

    Returns:
        ``{"status", "blocking", "problems", "advisories"}`` where ``status`` is
        one of ``"invalid"`` (baseline malformed), ``"regressed"`` (blocking),
        ``"improved"`` (advisory) or ``"within"`` (exact match).
    """
    for key in _RATCHET_KEYS:
        if key not in base or key not in cur:
            return {
                "status": "invalid",
                "blocking": True,
                "problems": [f"malformed ratchet data: missing key '{key}'"],
                "advisories": [],
            }

    problems: list[str] = []
    if cur["over"] > base["over"]:
        problems.append(
            f"functions >= CC {base['threshold']}: {cur['over']} > baseline {base['over']}"
        )
    if cur["max"] > base["max"]:
        problems.append(f"max CC: {cur['max']} > baseline {base['max']}")
    if problems:
        return {"status": "regressed", "blocking": True, "problems": problems, "advisories": []}

    advisories: list[str] = []
    if cur["over"] < base["over"]:
        advisories.append(f"functions >= CC {base['threshold']}: {cur['over']} < baseline {base['over']}")
    if cur["max"] < base["max"]:
        advisories.append(f"max CC: {cur['max']} < baseline {base['max']}")
    if advisories:
        return {"status": "improved", "blocking": False, "problems": [], "advisories": advisories}
    return {"status": "within", "blocking": False, "problems": [], "advisories": []}


def _check_ratchet() -> int:
    import json

    if not CC_BASELINE.exists():
        print(
            f"ERROR: baseline missing ({CC_BASELINE}); run --update-ratchet",
            file=sys.stderr,
        )
        return 2
    base = json.loads(CC_BASELINE.read_text(encoding="utf-8"))
    cur = cc_stats(threshold=base["threshold"])
    verdict = ratchet_verdict(cur, base)
    if verdict["blocking"]:
        print("::error::Cyclomatic-complexity ratchet regressed (F011/F015):")
        for p in verdict["problems"]:
            print(f"  - {p}")
        print("Decompose the offending function(s) — do not raise the caps. If you")
        print("genuinely lowered complexity, run: measure_cc.py --update-ratchet")
        return 1
    if verdict["status"] == "improved":
        # Tolerant policy (F046): improvement is accepted, not required. The
        # advisory nudges tightening the baseline during deliberate decomposition.
        print(
            f"CC improved ({'; '.join(verdict['advisories'])}) — advisory only; "
            "run measure_cc.py --update-ratchet to lock the gain in."
        )
    print(
        f"OK: {cur['over']} functions >= CC {base['threshold']}, max {cur['max']} (within baseline)."
    )
    return 0


def _update_ratchet() -> int:
    import json

    stats = cc_stats()
    stats["_comment"] = (
        "Backend cyclomatic-complexity ratchet (audit F011/F015). Shrink-only: "
        "measure_cc.py --check-ratchet fails if `over` or `max` grows. Regenerate "
        "with --update-ratchet ONLY after decomposing a hotspot."
    )
    CC_BASELINE.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(
        f"baseline written: over={stats['over']} max={stats['max']} threshold={stats['threshold']}"
    )
    return 0


if __name__ == "__main__":
    if "--update-ratchet" in sys.argv:
        sys.exit(_update_ratchet())
    if "--check-ratchet" in sys.argv:
        sys.exit(_check_ratchet())
    src_arg = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC_DIR
    threshold_arg = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_THRESHOLD
    sys.exit(main(src_arg, threshold_arg))
