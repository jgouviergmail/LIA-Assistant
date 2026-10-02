"""Every third-party module ``src/`` imports is declared in ``requirements.txt``.

A distribution that is only present transitively is installed by accident: the day
the package that pulls it stops doing so, or moves it to an optional extra, the import
fails at runtime, with nothing in the manifest to say it was ever needed. Measured on
2026-09-30: ``google-genai``, ``PyJWT``, ``starlette`` and ``typing-extensions`` were
imported by ``src/`` and declared nowhere (dependency programme, lot 3).

The census walks the AST of ``src/`` — function-level imports included — and asks
``importlib.metadata`` which distribution installs each module; a namespace package
(``google``) is resolved one level down, by the distribution whose files hold the
sub-package, since several distributions share its top level.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Mapping
from functools import cache
from importlib.metadata import distribution, packages_distributions
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

API_ROOT = Path(__file__).resolve().parents[2]
SRC = API_ROOT / "src"
MANIFEST = API_ROOT / "requirements.txt"

#: Top-level packages several distributions share (PEP 420), resolved one level down.
_NAMESPACE_PACKAGES = frozenset({"google"})
#: The application's own top-level package.
_LOCAL = frozenset({"src"})


def _canonical(name: str) -> str:
    """A distribution name as PEP 503 compares it."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared(manifest: str) -> set[str]:
    """The distributions a requirements file declares, canonical."""
    names: set[str] = set()
    for raw in manifest.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "-")):
            continue
        match = re.match(r"[A-Za-z0-9][A-Za-z0-9_.\-]*", line)
        if match:
            names.add(_canonical(match.group(0)))
    return names


def _imported_modules(tree: ast.AST) -> set[str]:
    """The third-party modules a module imports: top level, or one level into a namespace."""
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = (
                [f"{node.module}.{alias.name}" for alias in node.names]
                if node.module in _NAMESPACE_PACKAGES
                else [node.module]
            )
        else:
            continue
        for name in names:
            parts = name.split(".")
            if (
                parts[0] in sys.stdlib_module_names
                or parts[0] in _LOCAL
                or parts[0] == "__future__"
            ):
                continue
            modules.add(".".join(parts[:2]) if parts[0] in _NAMESPACE_PACKAGES else parts[0])
    return modules


@cache
def _top_level_owners() -> Mapping[str, list[str]]:
    return packages_distributions()


@cache
def _owners(module: str) -> frozenset[str]:
    """The installed distributions that provide ``module``, canonical."""
    top, _, sub = module.partition(".")
    candidates = _top_level_owners().get(top, [])
    if not sub:
        return frozenset(_canonical(name) for name in candidates)
    prefix = f"{top}/{sub}/"
    return frozenset(
        _canonical(name)
        for name in candidates
        if any(
            str(path).replace("\\", "/").startswith(prefix)
            for path in distribution(name).files or []
        )
    )


def _is_declared(module: str, declared: set[str]) -> bool:
    owners = _owners(module)
    # A platform-marked dependency absent from this interpreter has no installed
    # owner: its own name is then the only evidence there is.
    return bool(owners & declared) if owners else _canonical(module) in declared


def _undeclared(modules: set[str], declared: set[str]) -> dict[str, list[str]]:
    """Each imported module no declared distribution provides, with who does."""
    return {
        module: sorted(_owners(module))
        for module in sorted(modules)
        if not _is_declared(module, declared)
    }


def test_the_census_reads_imports_the_way_the_interpreter_resolves_them() -> None:
    tree = ast.parse(
        "import os\n"
        "import jwt\n"
        "from google import genai\n"
        "from google.genai import types\n"
        "from src.core import config\n"
        "from . import sibling\n"
        "def lazy():\n"
        "    import yaml\n"
    )

    assert _imported_modules(tree) == {"jwt", "google.genai", "yaml"}
    # A namespace package is owned by the distribution holding the sub-package.
    assert _owners("google.genai") == frozenset({"google-genai"})
    assert _undeclared({"jwt"}, declared=set()) == {"jwt": ["pyjwt"]}
    # Installed nowhere here (a platform marker): judged by its own name.
    assert _undeclared({"absent_mod"}, declared={"absent-mod"}) == {}
    assert _undeclared({"absent_mod"}, declared=set()) == {"absent_mod": []}


def test_every_imported_distribution_is_declared() -> None:
    modules: set[str] = set()
    for path in sorted(SRC.rglob("*.py")):
        modules |= _imported_modules(ast.parse(path.read_text(encoding="utf-8")))
    assert modules, "the census read no import: the walk is broken, not the tree clean"

    missing = _undeclared(modules, _declared(MANIFEST.read_text(encoding="utf-8")))
    assert not missing, (
        "src/ imports a distribution requirements.txt does not declare — it is installed "
        "only because something else pulls it. Declare it (a floor at the locked version), "
        f"then `task deps:lock`: {missing}"
    )
