"""Systemic guard: no hardcoded ``"Europe/Paris"`` default anywhere in src/.

The user's display timezone must come from their preferences or, as a last
resort, from the single central default ``DEFAULT_USER_DISPLAY_TIMEZONE``
(``src/core/constants.py``). A hardcoded ``"Europe/Paris"`` literal as a
parameter default, ``.get(..., "Europe/Paris")`` fallback, ``default=`` column
value, or ``Field(default=...)`` silently pins every un-migrated code path to
Paris and defeats the central knob (C3, project rule "never a hardcoded
'Europe/Paris' literal").

This test enforces the rule statically. It parses every ``src/**/*.py`` file
and flags any string literal (``ast.Constant``) whose value is **exactly**
``"Europe/Paris"``. Exact-equality is deliberate: it naturally excludes
docstrings, comments, and longer illustrative strings (``"e.g. 'Europe/Paris'"``)
which are legitimate documentation and are not code defaults.

Three files legitimately hold an exact ``"Europe/Paris"`` literal as *data*
(not as an application default) and are allow-listed below. If a new legitimate
data usage appears, add the file to ``ALLOWED_FILES`` with a justification —
do not weaken the scan.

Context: 2026-07 latent-debt remediation (C3).
"""

import ast
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).parents[2] / "src"

LITERAL = "Europe/Paris"

# Files where an exact "Europe/Paris" literal is legitimate DATA, not an
# application default that should resolve the user's timezone:
#   - core/constants.py: THE central definition (DEFAULT_USER_DISPLAY_TIMEZONE).
#   - core/validators.py: one valid selectable zone in the COMMON_TIMEZONES
#     picker list (a valid option, not "the default").
#   - domains/agents/semantic/core_types.py: an illustrative value in a Pydantic
#     ``examples=[...]`` list.
ALLOWED_FILES: set[str] = {
    "core/constants.py",
    "core/validators.py",
    "domains/agents/semantic/core_types.py",
}


def _iter_paris_literals(tree: ast.AST):
    """Yield the line number of every exact ``"Europe/Paris"`` string constant."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value == LITERAL:
                yield node.lineno


class TestTimezoneGuardScan:
    """Sanity check on the scan itself (guards against scan rot)."""

    def test_scan_detects_the_central_definition(self):
        """The scan must detect the exact literal where it legitimately lives."""
        constants_file = SRC_DIR / "core" / "constants.py"
        linenos = list(_iter_paris_literals(ast.parse(constants_file.read_text(encoding="utf-8"))))
        assert linenos, (
            "The AST scan no longer detects the exact 'Europe/Paris' literal in "
            "core/constants.py — the guard is broken, fix it before trusting it."
        )


class TestNoHardcodedParisTimezone:
    """CI guard: any hardcoded 'Europe/Paris' default fails the build."""

    def test_no_hardcoded_paris_default(self):
        """Scan all production code for hardcoded 'Europe/Paris' literals."""
        violations: list[str] = []
        for py_file in sorted(SRC_DIR.rglob("*.py")):
            rel_path = py_file.relative_to(SRC_DIR).as_posix()
            if rel_path in ALLOWED_FILES:
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for lineno in _iter_paris_literals(tree):
                violations.append(f"src/{rel_path}:{lineno}")

        if violations:
            pytest.fail(
                "Hardcoded 'Europe/Paris' timezone default(s) detected — resolve the "
                "user's timezone or reference DEFAULT_USER_DISPLAY_TIMEZONE instead:\n"
                + "\n".join(f"  - {v}" for v in violations)
            )
