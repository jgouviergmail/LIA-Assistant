"""Systemic guard for the exception-swallowing doctrine, enforced statically on src/.

One AST scan over every ``src/**/*.py`` file: an ``except`` handler whose body
is only ``pass`` (or a lone constant such as ``...``) fails the build.

Doctrine (2026-07 code-scanning remediation — 193 sites converted):

- **Intentional best-effort swallow** (metrics emission, cache invalidation,
  teardown): use ``contextlib.suppress(SpecificError)`` around the guarded
  statements. It is iso-functional with ``try/except: pass``, reads as explicit
  intent, and never leaves an empty handler for CodeQL (``py/empty-except``)
  to flag.
- **Multi-handler constructs** where one branch must swallow while another
  logs: nest ``with suppress(...)`` INSIDE the ``try`` (see
  ``domains/agents/api/sse_keepalive.py``) — the context manager intercepts
  its exceptions before the remaining ``except`` clauses, exactly like a
  dedicated earlier handler.
- **A swallow that hides a real signal** is not fixed by either form: add a
  ``logger.debug(...)`` (or higher) with context instead of suppressing.

Comments inside an empty handler do not make it non-empty: the AST (like
CodeQL) sees only statements. Put the justification comment ABOVE the
``with suppress(...)`` block.

The scan has an allow-list. If a new legitimate empty handler appears, add the
file with a justification — do not weaken the scan. A self-check test guards
the scan against rot.
"""

import ast
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).parents[2] / "src"

# No legitimate empty except handler remains in src/. Add entries only with a
# written justification of why neither suppress() nor logging fits.
EMPTY_EXCEPT_ALLOWED_FILES: set[str] = set()


def _is_empty_handler(handler: ast.ExceptHandler) -> bool:
    """True when the handler body is a lone ``pass`` or constant expression.

    A single constant expression (``...``, a stray string) is as empty as
    ``pass``: nothing observable happens in the branch.
    """
    if len(handler.body) != 1:
        return False
    stmt = handler.body[0]
    if isinstance(stmt, ast.Pass):
        return True
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)


def _iter_empty_except_handlers(tree: ast.AST):
    """Yield ``(lineno, caught)`` for every empty except handler."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and _is_empty_handler(node):
            caught = ast.unparse(node.type) if node.type is not None else "<bare>"
            yield node.lineno, caught


class TestEmptyExceptGuardScan:
    """Sanity checks on the scan itself (guards against scan rot)."""

    def test_scan_detects_synthetic_violations(self):
        """Every empty-handler shape must be detected in a synthetic snippet."""
        snippet = (
            "try:\n"
            "    a()\n"
            "except ValueError:\n"
            "    pass\n"
            "try:\n"
            "    b()\n"
            "except (KeyError, TypeError):\n"
            "    ...\n"
            "try:\n"
            "    c()\n"
            "except Exception:\n"
            "    pass\n"
            "except:\n"
            "    pass\n"
        )
        found = list(_iter_empty_except_handlers(ast.parse(snippet)))
        assert len(found) == 4, (
            "The empty-except AST scan no longer detects the synthetic "
            f"violations (found {len(found)}/4) — the guard is broken, fix it "
            "before trusting it."
        )

    def test_scan_ignores_legitimate_handlers(self):
        """suppress() usage and non-empty handlers must not be flagged."""
        snippet = (
            "from contextlib import suppress\n"
            "with suppress(ValueError):\n"
            "    a()\n"
            "try:\n"
            "    b()\n"
            "except Exception:\n"
            "    logger.debug('failed')\n"
        )
        assert list(_iter_empty_except_handlers(ast.parse(snippet))) == []


class TestNoEmptyExceptHandlers:
    """CI guard: an empty except handler in src/ fails the build."""

    def test_no_empty_except_handlers(self):
        """Scan all production code for empty except handlers."""
        violations: list[str] = []
        for py_file in sorted(SRC_DIR.rglob("*.py")):
            rel_path = py_file.relative_to(SRC_DIR).as_posix()
            if rel_path in EMPTY_EXCEPT_ALLOWED_FILES:
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for lineno, caught in _iter_empty_except_handlers(tree):
                violations.append(f"src/{rel_path}:{lineno} — except {caught}: <empty>")

        if violations:
            pytest.fail(
                "Empty except handler(s) detected — use contextlib.suppress() "
                "for intentional best-effort swallows, or log the failure "
                "(exception-swallowing doctrine, see this module's docstring):\n"
                + "\n".join(f"  - {v}" for v in violations)
            )
