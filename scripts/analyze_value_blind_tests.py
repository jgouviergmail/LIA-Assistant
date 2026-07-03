"""Audit helper: find test functions whose assertions can barely fail.

Born from the 2026-07 codebase audit: the polyline encoder shipped broken for
months under 49 "passing" tests because none of them compared VALUES (only
structure, counts and types). This scanner inventories that bug class.

A test function is flagged when EVERY assert it contains is 'weak':
- ``isinstance(x, T)`` / ``hasattr(x, 'a')``
- ``x is None`` / ``x is not None``
- ``len(x) > 0`` / ``len(x) >= 0`` / ``len(x) != 0``
- bare truthiness (``assert x`` / ``assert not x``)

Exception — ``assert [not] <name>`` is treated as STRONG when ``<name>`` holds
a collection of violations in the function (assigned ``[]`` / a comprehension,
or grown via ``.append``/``.add``). That is the integrity-check pattern
(``violations = []; ...; assert not violations``), not weak truthiness.

Tests with zero asserts are flagged too (execute-only tests), unless they use
``pytest.raises`` or mock call-assertion helpers (strong checks).

Usage (from apps/api):
    .venv/Scripts/python ../../scripts/analyze_value_blind_tests.py [-v]

The output is an INVENTORY, not a verdict: registration smoke tests (metrics,
imports) legitimately assert existence only. Review before rewriting.

Two signals are reported:

1. Per-test candidates — every weak assertion, high false-positive rate. A
   single ``isinstance(result, T)`` test is flagged even when a sibling test
   asserts the actual value. Use only as a starting inventory.
2. **Fully value-blind FILES** (``--files``) — files where NOT ONE test makes
   a strong assertion. This is the actionable, low-false-positive signal: it
   is the shape of the 2026-07 polyline gap (a whole surface with no value
   check). Prioritize these for review.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "apps" / "api" / "tests"

WEAK_CALLS = {"isinstance", "hasattr", "len"}

STRONG_MOCK_HELPERS = {
    "raises",
    "fail",
    "assert_called_once_with",
    "assert_awaited_once_with",
    "assert_called_with",
    "assert_awaited_with",
}


def is_weak(test: ast.expr) -> bool:
    """Return True when the assert expression cannot catch a value regression."""
    if isinstance(test, (ast.Name, ast.Attribute)):
        return True
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return is_weak(test.operand)
    if isinstance(test, ast.Call):
        fn = test.func
        name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
        return name in WEAK_CALLS
    if isinstance(test, ast.Compare):
        # x is None / x is not None
        if all(isinstance(op, (ast.Is, ast.IsNot)) for op in test.ops):
            return all(isinstance(c, ast.Constant) and c.value is None for c in test.comparators)
        # len(x) > 0 / >= 0 / != 0
        if isinstance(test.left, ast.Call):
            fn = test.left.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            if name == "len" and all(
                isinstance(c, ast.Constant) and c.value == 0 for c in test.comparators
            ):
                return all(isinstance(op, (ast.Gt, ast.GtE, ast.NotEq)) for op in test.ops)
        return False
    return False


def _collection_names(node: ast.AST) -> set[str]:
    """Names that hold a COLLECTION of violations in this function.

    Assigned an empty list / list-comprehension, or grown via ``.append``.
    ``assert not violations`` / ``assert violations`` over such a name is a
    strong emptiness check (the semantic-integrity pattern), not weak
    truthiness — this removes that whole false-positive class.
    """
    names: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Assign):
            is_collection = isinstance(n.value, (ast.List, ast.ListComp, ast.SetComp, ast.Dict))
            if is_collection:
                for target in n.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if n.func.attr in ("append", "extend", "add", "update") and isinstance(
                n.func.value, ast.Name
            ):
                names.add(n.func.value.id)
    return names


def _assert_is_weak(test: ast.expr, collections: set[str]) -> bool:
    """is_weak, but ``[not] <collection>`` counts as a strong emptiness check."""
    target = test.operand if isinstance(test, ast.UnaryOp) else test
    if isinstance(target, ast.Name) and target.id in collections:
        return False
    return is_weak(test)


def _test_is_value_blind(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool | None:
    """Classify a single test function.

    Returns True if value-blind, False if it makes a strong assertion, or None
    if it should be excluded from the file-level ratio (uses pytest.raises /
    mock call-assertion helpers — those ARE strong checks, counted as strong).
    """
    has_strong_helper = any(
        isinstance(n, ast.Call) and getattr(n.func, "attr", "") in STRONG_MOCK_HELPERS
        for n in ast.walk(node)
    )
    if has_strong_helper:
        return False  # a strong check
    asserts = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
    if not asserts:
        return True  # execute-only
    collections = _collection_names(node)
    return all(_assert_is_weak(a.test, collections) for a in asserts)


def main() -> None:
    """Scan the backend test tree and print the value-blind inventory."""
    files_mode = "--files" in sys.argv
    verbose = "-v" in sys.argv

    flagged: list[tuple[str, str, int, int]] = []
    total_tests = 0
    # file -> [blind_count, total_count]
    file_stats: dict[str, list[int]] = {}

    for py in ROOT.rglob("test_*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = str(py.relative_to(ROOT))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            total_tests += 1
            stats = file_stats.setdefault(rel, [0, 0])
            stats[1] += 1

            blind = _test_is_value_blind(node)
            if blind:
                stats[0] += 1
                asserts = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
                flagged.append((rel, node.name, node.lineno, len(asserts)))

    print(f"Total test functions: {total_tests}")
    print(f"Value-blind candidates (per-test, high false-positive): {len(flagged)}")

    # File-level signal: files where EVERY test is value-blind (>= 3 tests to
    # exclude trivial 1-2 test files). This is the polyline-class risk shape.
    fully_blind = [(path, s[1]) for path, s in file_stats.items() if s[1] >= 3 and s[0] == s[1]]
    print(f"\nFully value-blind FILES (>=3 tests, 0 strong assertions): {len(fully_blind)}")
    for path, n in sorted(fully_blind, key=lambda kv: -kv[1]):
        print(f"  {n:3d} tests  {path}")

    if files_mode:
        return

    by_file: dict[str, list[tuple[str, int, int]]] = {}
    for file_path, name, line, assert_count in flagged:
        by_file.setdefault(file_path, []).append((name, line, assert_count))

    print("\nPer-test candidates by file (top 20):")
    for file_path, items in sorted(by_file.items(), key=lambda kv: -len(kv[1]))[:20]:
        print(f"{len(items):3d}  {file_path}")
        if verbose:
            for name, line, assert_count in items:
                print(f"      L{line} {name} ({assert_count} asserts)")


if __name__ == "__main__":
    main()
