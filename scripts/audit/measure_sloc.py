#!/usr/bin/env python3
"""Reproducible size metrics for the 360° technical audit (logical SLOC).

Counts *logical* source lines — excluding docstrings, comments and blank
lines — via tokenize + AST, at file and function granularity. These are the
official size figures used by the audit protocol (docs/audit/AUDIT_PROTOCOL.md)
and published in the public report (docs/audit/README.md): raw line counts
overstate code size by ~40% in this repository because of its documentation
density, so they are never used for scoring.

Usage (from any directory):
    python scripts/audit/measure_sloc.py [SRC_DIR]

Defaults to apps/api/src, resolved from this file's location so the script is
CWD-independent (F023). Standard library only — no dependencies.
"""

from __future__ import annotations

import ast
import io
import statistics
import sys
import tokenize
from pathlib import Path

# Data modules are exempt from "god file" scoring: they are long by nature
# (translation tables, configuration defaults) and their remediation lever is
# a format change, not decomposition. Kept in sync with the audit protocol.
DATA_MODULE_PREFIXES: tuple[str, ...] = (
    "core/i18n_",
    "core/config/",
    "core/constants",
    "domains/llm_config/constants",
)

# Default target resolved from this file (scripts/audit/ -> repo root -> src),
# so the script works identically from any working directory (F023).
DEFAULT_SRC_DIR: Path = Path(__file__).resolve().parents[2] / "apps" / "api" / "src"

FILE_THRESHOLDS = (800, 1000)
FUNCTION_THRESHOLDS = (100, 200)
TOP_N = 15

_SKIP_TOKENS = frozenset(
    {
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENCODING,
        tokenize.ENDMARKER,
    }
)


def _docstring_ranges(tree: ast.AST) -> list[tuple[int, int]]:
    """Line ranges of every module/class/function docstring in the tree."""
    ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                doc = body[0]
                ranges.append((doc.lineno, doc.end_lineno or doc.lineno))
    return ranges


def code_lines(source: str) -> tuple[set[int], ast.AST] | None:
    """Return the set of line numbers carrying logical code, plus the AST.

    Returns None when the file cannot be tokenized or parsed (it is then
    excluded from the metrics rather than silently miscounted).
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        tree = ast.parse(source)
    except (SyntaxError, tokenize.TokenError, ValueError):
        return None

    doc_ranges = _docstring_ranges(tree)

    def in_docstring(line: int) -> bool:
        return any(start <= line <= end for start, end in doc_ranges)

    lines: set[int] = set()
    for token in tokens:
        if token.type in _SKIP_TOKENS:
            continue
        for line in range(token.start[0], token.end[0] + 1):
            if not in_docstring(line):
                lines.add(line)
    return lines, tree


def is_data_module(relative_path: str) -> bool:
    """True when the file is a size-exempt data module (see protocol)."""
    normalized = relative_path.replace("\\", "/")
    return any(prefix in normalized for prefix in DATA_MODULE_PREFIXES)


def main(src_dir: str | Path = DEFAULT_SRC_DIR) -> int:
    """Measure and print the audit size metrics for ``src_dir``."""
    root = Path(src_dir)
    if not root.is_dir():
        print(f"ERROR: source directory not found: {root.resolve()}", file=sys.stderr)
        return 1

    files: list[tuple[int, int, str]] = []  # (sloc, raw, path)
    functions: list[tuple[int, str, str]] = []  # (sloc, path, name)
    unparsable: list[str] = []

    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf-8", errors="replace")
        result = code_lines(source)
        if result is None:
            unparsable.append(str(path))
            continue
        lines, tree = result
        raw = source.count("\n") + 1
        files.append((len(lines), raw, str(path)))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                span = range(node.lineno, (node.end_lineno or node.lineno) + 1)
                fn_sloc = sum(1 for line in span if line in lines)
                functions.append((fn_sloc, str(path), node.name))

    total_sloc = sum(sloc for sloc, _, _ in files)
    total_raw = sum(raw for _, raw, _ in files)
    fn_sizes = sorted((sloc for sloc, _, _ in functions), reverse=True)

    print(f"files={len(files)} functions={len(functions)} unparsable={len(unparsable)}")
    print(
        f"total: sloc={total_sloc} raw={total_raw} (code ratio {100 * total_sloc // max(total_raw, 1)}%)"
    )

    for threshold in FILE_THRESHOLDS:
        big = [f for f in files if f[0] >= threshold]
        big_logic = [f for f in big if not is_data_module(f[2])]
        cumulative = sum(f[0] for f in big)
        print(
            f"files >= {threshold} SLOC: {len(big)} "
            f"(logic: {len(big_logic)}, data: {len(big) - len(big_logic)}) "
            f"— cumulative {cumulative} SLOC = {100 * cumulative // max(total_sloc, 1)}% of code"
        )

    if fn_sizes:
        print(
            f"functions: median={statistics.median(fn_sizes):.0f} "
            f"p90={fn_sizes[len(fn_sizes) // 10]}"
        )
        for threshold in FUNCTION_THRESHOLDS:
            count = sum(1 for size in fn_sizes if size > threshold)
            print(f"functions > {threshold} SLOC: {count}")

    print(f"\ntop {TOP_N} files (sloc/raw, [data] = size-exempt data module):")
    for sloc, raw, path in sorted(files, reverse=True)[:TOP_N]:
        tag = " [data]" if is_data_module(path) else ""
        print(f"  {sloc:6d} / {raw:6d}  {path}{tag}")

    print(f"\ntop {TOP_N} functions (pure-code SLOC):")
    for sloc, path, name in sorted(functions, reverse=True)[:TOP_N]:
        print(f"  {sloc:6d}  {path}::{name}")

    if unparsable:
        print("\nWARNING — unparsable files (excluded from metrics):", file=sys.stderr)
        for path in unparsable:
            print(f"  {path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC_DIR))
