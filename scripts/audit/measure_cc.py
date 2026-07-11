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

Usage (from apps/api/):
    python ../../scripts/audit/measure_cc.py [SRC_DIR] [THRESHOLD]

Defaults to ./src and threshold 15. Standard library only — no dependencies.
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


def main(src_dir: str = "src", threshold: int = DEFAULT_THRESHOLD) -> int:
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


if __name__ == "__main__":
    src_arg = sys.argv[1] if len(sys.argv) > 1 else "src"
    threshold_arg = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_THRESHOLD
    sys.exit(main(src_arg, threshold_arg))
