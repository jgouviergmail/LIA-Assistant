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

The container runs a second process before the API: the migrations. Its
``alembic/env.py`` imports every model, and measured 2026-10-03 the lines those
imports log reached the container log under the same defaults (DEBUG lines at
``LOG_LEVEL=INFO``, console rendering). It holds the same rule, and calls no
``fileConfig``, which would replace the configured root handler.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
ALEMBIC_ENV = SRC.parent / "alembic" / "env.py"
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
@pytest.mark.parametrize("entry_point", [SRC / "main.py", ALEMBIC_ENV], ids=["main", "alembic"])
def test_an_entry_point_imports_the_logging_bootstrap_before_any_application_module(
    entry_point: Path,
) -> None:
    tree = ast.parse(entry_point.read_text(encoding="utf-8"))

    imports = _application_imports(tree)

    assert imports, f"{entry_point.name} imports no application module — wrong file read"
    assert imports[0] == BOOTSTRAP_MODULE, (
        f"{entry_point.name} imports {imports[0]} before {BOOTSTRAP_MODULE}: anything "
        "that module logs at import time escapes the logging configuration"
    )


@pytest.mark.unit
def test_the_migrations_do_not_reconfigure_logging() -> None:
    tree = ast.parse(ALEMBIC_ENV.read_text(encoding="utf-8"))

    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }

    assert not called & {"fileConfig", "dictConfig", "basicConfig"}


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
