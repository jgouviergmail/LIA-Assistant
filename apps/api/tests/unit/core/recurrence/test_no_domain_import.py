"""The genericity boundary — asserted, not promised.

`core/recurrence` must serve consumers that do not exist yet. A single import
of `src.domains` would make it the property of its first consumer, and the
second one would inherit a dependency it has no use for.

An AST check rather than a runtime one: an import inside a function body would
survive `import src.core.recurrence` and still tie the package to a domain.

The second guard below is about a subtler tie. Moving the schedule helpers in
brought `src.core.time_utils` with them, which imports `src.core.config` and
BUILDS a full `Settings()` at module import: the package suddenly refused to
load without a database URL and a Fernet key. Nothing in FORBIDDEN_ROOTS was
touched, so the AST check stayed green. `now_utc()` is `datetime.now(UTC)` —
the dependency bought nothing.

And it costs more than independence: `core.constants` reads `RecurrenceLimits`
from this package, so `time_utils` closes the chain on a partially-initialised
`core.config` and the application does not boot at all. Reintroduced on purpose
to check this guard, the whole suite failed to COLLECT.
"""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[4] / "src" / "core" / "recurrence"

#: Import roots the package may never reach for, at any depth.
FORBIDDEN_ROOTS = ("src.domains", "src.infrastructure", "src.api")


def _imported_modules(source: str) -> list[str]:
    """Every module name a file imports, `from` and plain, at any depth."""
    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            found.append(node.module)
    return found


def test_the_package_exists() -> None:
    assert PACKAGE.is_dir(), f"{PACKAGE} not found"
    assert sorted(p.name for p in PACKAGE.glob("*.py")) == [
        "__init__.py",
        "dictation.py",
        "display.py",
        "engine.py",
        "schedule.py",
        "spec.py",
    ]


def test_no_module_imports_a_domain() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.glob("*.py")):
        for module in _imported_modules(path.read_text(encoding="utf-8")):
            if module.startswith(FORBIDDEN_ROOTS):
                offenders.append(f"{path.name}: {module}")
    assert offenders == [], (
        "core/recurrence must stay domain-free so a future consumer inherits "
        f"no dependency: {offenders}"
    )


#: Modules whose import pulls configuration, a database, or a network client.
#: A recurrence rule is arithmetic on a calendar; it needs none of them.
HEAVY_MODULES = ("src.core.config", "src.core.time_utils", "src.core.constants")


def test_no_module_reaches_for_configuration() -> None:
    """The package must load with no environment at all.

    A consumer that only wants to know when something fires should not have to
    stand up settings to ask.
    """
    offenders: list[str] = []
    for path in sorted(PACKAGE.glob("*.py")):
        for module in _imported_modules(path.read_text(encoding="utf-8")):
            if module.startswith(HEAVY_MODULES):
                offenders.append(f"{path.name}: {module}")
    assert offenders == [], (
        "core/recurrence must import with no configuration; these pull " f"settings in: {offenders}"
    )


def test_the_package_imports_in_a_bare_interpreter() -> None:
    """The AST guard names modules; this one proves the consequence.

    Run in a subprocess, because this process has already imported settings
    through the suite's conftest. The environment keeps what the interpreter
    itself needs (an empty PATH stops Windows loading its own DLLs) and drops
    every variable the application configures itself from.
    """
    import os
    import subprocess
    import sys

    stripped = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DATABASE", "REDIS", "SECRET", "FERNET", "LIA_", "POSTGRES"))
    }
    result = subprocess.run(
        [sys.executable, "-c", "import src.core.recurrence as r; print(len(r.__all__))"],
        capture_output=True,
        text=True,
        env=stripped,
        cwd=str(PACKAGE.parents[2]),
    )
    assert result.returncode == 0, (
        "core/recurrence must import with no application configuration: " + result.stderr[-2000:]
    )
