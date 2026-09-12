"""A heavy library is imported where it is used, never at boot.

Every uvicorn worker — and, until ``src.serve``, the supervisor too — pays the
application's import once per PROCESS: with four workers a module imported at
boot is resident four times, whether or not the feature it serves ever runs.
Measured on the production Raspberry Pi (arm64) on 2026-09-12, in a throwaway
process, after ``import src.main``:

* ``fitz`` (PyMuPDF) cost 43 MB per process and was imported at boot by a
  single top-level ``import fitz`` in the PDF renderer, for a feature — a
  generated PDF — that a worker may never exercise. On x86_64 the same import
  measured 118 MB, which is why the figure here is the arm64 one.
* ``pandas`` costs 52 MB, ``sherpa_onnx`` 18 MB before any model: both were
  already lazy, and this guard keeps them so.

The rule is structural, not stylistic: a library in ``LAZY_ONLY`` may only be
imported inside a function or under ``TYPE_CHECKING``. A module-level import
anywhere under ``src/`` — including inside a module-level ``try`` — fails the
build with the measured cost in the message, so the decision is taken with the
number in front of the author rather than discovered on the host.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC_DIR = Path(__file__).parents[2] / "src"

#: Top-level package → measured cost of importing it, per process.
LAZY_ONLY: dict[str, str] = {
    "fitz": "43 MB per process (PyMuPDF, prod arm64 2026-09-12; 118 MB on x86_64)",
    "pymupdf": "43 MB per process (PyMuPDF's other import name)",
    "pandas": "52 MB per process (prod arm64 2026-09-12)",
    "sherpa_onnx": "18 MB per process before any model, 1.6 GB after (STT, 2026-09-12)",
    "onnxruntime": "the runtime under sherpa_onnx",
    "playwright": "spawns a browser; the module alone drags its protocol bindings",
}


def _is_type_checking(test: ast.expr) -> bool:
    """``if TYPE_CHECKING:`` in either spelling."""
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _module_level_statements(body: list[ast.stmt]) -> list[ast.stmt]:
    """Statements executed at import time, descending into try/if/with blocks.

    A function or class body is skipped: an import there runs on call, which
    is exactly what the rule asks for. A ``TYPE_CHECKING`` branch is skipped
    because the interpreter never runs it.
    """
    flat: list[ast.stmt] = []
    for node in body:
        if isinstance(node, ast.If):
            if _is_type_checking(node.test):
                flat.extend(_module_level_statements(node.orelse))
                continue
            flat.extend(_module_level_statements(node.body))
            flat.extend(_module_level_statements(node.orelse))
        elif isinstance(node, ast.Try):
            flat.extend(_module_level_statements(node.body))
            for handler in node.handlers:
                flat.extend(_module_level_statements(handler.body))
            flat.extend(_module_level_statements(node.orelse))
            flat.extend(_module_level_statements(node.finalbody))
        elif isinstance(node, ast.With):
            flat.extend(_module_level_statements(node.body))
        else:
            flat.append(node)
    return flat


def _imported_roots(node: ast.stmt) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name.split(".")[0] for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
        return [node.module.split(".")[0]]
    return []


def boot_time_heavy_imports(path: Path) -> list[tuple[int, str]]:
    """``(line, package)`` for every module-level import of a ``LAZY_ONLY`` package."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        (node.lineno, root)
        for node in _module_level_statements(tree.body)
        for root in _imported_roots(node)
        if root in LAZY_ONLY
    ]


def test_no_heavy_library_is_imported_at_boot() -> None:
    offenders = [
        f"{path.relative_to(SRC_DIR).as_posix()}:{line} imports {root} — {LAZY_ONLY[root]}"
        for path in sorted(SRC_DIR.rglob("*.py"))
        for line, root in boot_time_heavy_imports(path)
    ]
    assert offenders == [], "Import these where they are used:\n  " + "\n  ".join(offenders)


class TestTheScanReadsWhatItClaims:
    """The scan must see through the shapes that hide a boot-time import."""

    def test_flags_a_bare_module_level_import(self, tmp_path: Path) -> None:
        module = tmp_path / "m.py"
        module.write_text("import fitz\n", encoding="utf-8")
        assert boot_time_heavy_imports(module) == [(1, "fitz")]

    def test_flags_an_import_inside_a_module_level_try(self, tmp_path: Path) -> None:
        module = tmp_path / "m.py"
        module.write_text("try:\n    import pandas as pd\nexcept ImportError:\n    pd = None\n")
        assert boot_time_heavy_imports(module) == [(2, "pandas")]

    def test_flags_a_from_import_of_a_submodule(self, tmp_path: Path) -> None:
        module = tmp_path / "m.py"
        module.write_text("from playwright.async_api import async_playwright\n")
        assert boot_time_heavy_imports(module) == [(1, "playwright")]

    def test_accepts_an_import_inside_a_function(self, tmp_path: Path) -> None:
        module = tmp_path / "m.py"
        module.write_text("def render():\n    import fitz\n    return fitz\n")
        assert boot_time_heavy_imports(module) == []

    def test_accepts_a_type_checking_import(self, tmp_path: Path) -> None:
        module = tmp_path / "m.py"
        module.write_text("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import fitz\n")
        assert boot_time_heavy_imports(module) == []

    def test_ignores_packages_outside_the_declared_list(self, tmp_path: Path) -> None:
        module = tmp_path / "m.py"
        module.write_text("import numpy\nfrom fitzgerald import x\n", encoding="utf-8")
        assert boot_time_heavy_imports(module) == []
