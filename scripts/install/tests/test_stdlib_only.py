"""Stdlib-only + Python 3.10 compatibility contract for the wizard (B01).

The installer must run on a bare host with only Python >= 3.10: every module
under ``scripts/install/`` (tests excluded) may import ONLY the standard
library or ``scripts.install`` itself, and installer enums must use
``class Name(str, Enum)`` — never ``enum.StrEnum`` (3.11+).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

INSTALL_ROOT = Path(__file__).resolve().parents[1]

_ALLOWED_PREFIXES = ("scripts.install",)


def _wizard_modules() -> list[Path]:
    # Non-recursive on purpose: tests/ has its own (pytest-using) rules.
    return sorted(INSTALL_ROOT.glob("*.py"))


def _imported_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
    return names


def test_wizard_modules_exist() -> None:
    present = {p.name for p in _wizard_modules()}
    for required in (
        "model.py",
        "i18n.py",
        "questions.py",
        "answers.py",
        "verify.py",
        "manifest.py",
    ):
        assert required in present, f"missing wizard module: {required}"


def test_every_import_is_stdlib_or_wizard_local() -> None:
    offenders: list[str] = []
    for module_path in _wizard_modules():
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for name in _imported_names(tree):
            top = name.split(".")[0]
            if name.startswith(_ALLOWED_PREFIXES):
                continue
            if top in sys.stdlib_module_names:
                continue
            offenders.append(f"{module_path.name}: {name}")
    assert offenders == [], f"non-stdlib imports in wizard: {offenders}"


def test_no_strenum_and_no_relative_escape() -> None:
    for module_path in _wizard_modules():
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # AST-level detection: docstring MENTIONS of StrEnum are fine,
            # importing it or subclassing it is the 3.11+ break.
            if isinstance(node, ast.ImportFrom) and node.level > 1:
                raise AssertionError(
                    f"{module_path.name} escapes the package: level={node.level}"
                )
            if isinstance(node, ast.ImportFrom) and any(
                alias.name == "StrEnum" for alias in node.names
            ):
                raise AssertionError(f"{module_path.name} imports StrEnum (3.11+)")
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_name = ast.unparse(base)
                    if "StrEnum" in base_name:
                        raise AssertionError(
                            f"{module_path.name}:{node.name} subclasses {base_name}"
                        )
