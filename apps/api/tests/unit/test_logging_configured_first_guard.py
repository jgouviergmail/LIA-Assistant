"""Guard: the API configures logging BEFORE it imports any application module.

Importing the application runs code: tool modules build their singleton
instances, registries announce what they register, the prompt loader reports
the versions it found. Whatever logs during that import, before
``configure_logging()`` has run, logs under structlog's DEFAULTS — console
rendering Promtail cannot parse, no level filter, no PII filter. ``main.py``
said « Configure logging before anything else » while importing every route
first: measured 2026-09-23, DEBUG lines at ``LOG_LEVEL=INFO`` in the production
logs, tool parameters included.

The configuration is therefore a side effect of the FIRST application import
of ``main.py`` (``logging_bootstrap``), and this guard holds that order.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
BOOTSTRAP_MODULE = "src.infrastructure.observability.logging_bootstrap"


def _application_imports(tree: ast.Module) -> list[str]:
    """Module-level ``src.*`` imports of ``tree``, in source order, fully named."""
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("src."):
            names.extend(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names if alias.name.startswith("src."))
    return names


@pytest.mark.unit
def test_main_imports_the_logging_bootstrap_before_any_application_module() -> None:
    tree = ast.parse((SRC / "main.py").read_text(encoding="utf-8"))

    imports = _application_imports(tree)

    assert imports, "main.py imports no application module — the guard reads the wrong file"
    assert imports[0] == BOOTSTRAP_MODULE, (
        f"main.py imports {imports[0]} before {BOOTSTRAP_MODULE}: anything that "
        "module logs at import time escapes the logging configuration"
    )


@pytest.mark.unit
def test_the_bootstrap_configures_logging_when_imported() -> None:
    path = SRC / Path(*BOOTSTRAP_MODULE.split(".")[1:]).with_suffix(".py")
    tree = ast.parse(path.read_text(encoding="utf-8"))

    module_level_calls = [
        node.value.func.id
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
    ]

    assert module_level_calls == ["configure_logging"]
