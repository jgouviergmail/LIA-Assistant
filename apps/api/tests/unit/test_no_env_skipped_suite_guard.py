"""Systemic guard: no test module may disable itself on a missing API key.

One AST scan over every ``tests/**/*.py``: a module-level ``pytestmark`` that
skips the whole file when an environment variable is unset takes the entire
suite out of CI, silently and permanently. Nothing reports it — a skipped test
is green — so the file keeps accumulating assertions that never run and rots
against the code it claims to protect.

Measured on 2026-07-26: ten such files held **219 test functions that had never
run** (234 cases once parametrization expands), covering the HITL classifier,
the draft executor, resumption strategies, graph construction and the streaming
mixin. Re-enabled with a dummy key, **142 came back red** (125 failures, 17
setup errors) against 92 green: they had been written against
``AIMessage.content`` before the LangChain 1.x ``.text`` migration, and against
a classifier that predates structured output. A test that cannot fail is not
coverage, it is decoration.

What to do instead of a blanket skip:

- The test only needs an LLM *shape* → mock it. That is a unit test; it belongs
  in ``tests/unit/`` with no environment gate at all.
- The test genuinely calls a paid provider → mark it ``@pytest.mark.integration``
  (or ``e2e``). CI deselects those markers explicitly, so the exclusion is
  visible in the command instead of hidden in the file.
- A single test needs a key → gate THAT test, not the module. A function-level
  ``@pytest.mark.skipif`` leaves the rest of the file running.

``ALLOWED_ENV_SKIPPED_MODULES`` is shrink-only: entries come out as suites are
repaired, and none may be added. A self-check test guards the scan against rot.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parents[1]

#: Environment variables whose absence must not disable a whole suite.
#: Provider credentials only — a module gated on, say, a platform capability is
#: a different (legitimate) question.
_CREDENTIAL_ENV_MARKERS: frozenset[str] = frozenset(
    {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "DEEPSEEK_API_KEY",
        "PERPLEXITY_API_KEY",
        "BRAVE_API_KEY",
    }
)

#: Suites still gated behind a credential check. SHRINK-ONLY — repair the suite
#: and delete its line; never add one. The count is the number of tests the
#: entry currently hides, so the cost stays visible.
#:
#: EMPTY as of 2026-07-26: of the ten offending suites, eight were repaired
#: (hermetic harnesses — an in-memory LangGraph store, a doubled agent registry,
#: a neutralised TCM session) and two honestly relabelled `e2e`, because they
#: genuinely call a paid provider — one is a model-quality eval, the other calls
#: twice per test. Keep it empty — an entry here means tests that nobody runs.
ALLOWED_ENV_SKIPPED_MODULES: dict[str, int] = {}


def _mentions_credential_env(node: ast.AST) -> bool:
    """True when the expression reads one of the credential env vars.

    Args:
        node: Any AST subtree (a ``skipif`` condition, in practice).

    Returns:
        True if a credential variable name appears as a string constant inside
        an ``os.getenv(...)`` / ``os.environ[...]`` style lookup.
    """
    return any(
        isinstance(child, ast.Constant)
        and isinstance(child.value, str)
        and child.value in _CREDENTIAL_ENV_MARKERS
        for child in ast.walk(node)
    )


def _declares_deselected_marker(node: ast.AST) -> bool:
    """True when the ``pytestmark`` expression also carries an excluded marker.

    ``integration``/``e2e``/``slow`` appear verbatim in the CI ``-m`` filters, so
    a suite carrying one is excluded *visibly*. That is the sanctioned escape
    hatch for a test that genuinely calls a paid provider.

    Args:
        node: The ``pytestmark`` assignment value.

    Returns:
        True if an excluded marker is applied anywhere in the expression.
    """
    return any(
        isinstance(child, ast.Attribute)
        and child.attr in {"integration", "e2e", "slow"}
        and isinstance(child.value, ast.Attribute)
        and child.value.attr == "mark"
        for child in ast.walk(node)
    )


def _module_level_credential_skip(tree: ast.Module) -> int | None:
    """Line number of a module-level ``pytestmark`` gated on a credential.

    A module that ALSO declares an excluded marker is not reported: its
    exclusion is already explicit in the CI command.

    Args:
        tree: Parsed test module.

    Returns:
        The line number of the offending assignment, or ``None``.
    """
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if "pytestmark" not in targets:
            continue
        if _mentions_credential_env(node.value) and not _declares_deselected_marker(node.value):
            return node.lineno
    return None


def _iter_test_modules() -> list[Path]:
    """Every test module under ``tests/``, excluding this guard itself."""
    return [
        path
        for path in sorted(TESTS_DIR.rglob("test_*.py"))
        if path.resolve() != Path(__file__).resolve()
    ]


def _relative(path: Path) -> str:
    """Path relative to ``tests/``, forward-slashed, for stable allowlist keys."""
    return path.relative_to(TESTS_DIR).as_posix()


pytestmark = pytest.mark.unit


class TestEnvSkipGuardScan:
    """Sanity checks on the scan itself (guards against scan rot)."""

    def test_scan_detects_a_synthetic_module_level_skip(self) -> None:
        snippet = (
            "import os\n"
            "import pytest\n"
            "pytestmark = pytest.mark.skipif(\n"
            "    not os.getenv('OPENAI_API_KEY'), reason='needs a key'\n"
            ")\n"
        )
        assert _module_level_credential_skip(ast.parse(snippet)) == 3

    def test_scan_ignores_a_function_level_skip(self) -> None:
        """Gating ONE test is the recommended form — it must not be flagged."""
        snippet = (
            "import os\n"
            "import pytest\n"
            "@pytest.mark.skipif(not os.getenv('OPENAI_API_KEY'), reason='needs a key')\n"
            "def test_one():\n"
            "    pass\n"
        )
        assert _module_level_credential_skip(ast.parse(snippet)) is None

    def test_scan_ignores_a_marker_that_is_not_a_credential(self) -> None:
        snippet = (
            "import os\n"
            "import pytest\n"
            "pytestmark = pytest.mark.skipif(\n"
            "    not os.getenv('RUN_HEAVY_SUITE'), reason='opt-in'\n"
            ")\n"
        )
        assert _module_level_credential_skip(ast.parse(snippet)) is None

    def test_scan_ignores_a_plain_marker_list(self) -> None:
        snippet = "import pytest\npytestmark = [pytest.mark.unit]\n"
        assert _module_level_credential_skip(ast.parse(snippet)) is None

    def test_scan_accepts_a_credential_skip_declared_alongside_an_excluded_marker(self) -> None:
        """The sanctioned escape hatch: the CI ``-m`` filter names the marker."""
        snippet = (
            "import os\n"
            "import pytest\n"
            "pytestmark = [\n"
            "    pytest.mark.e2e,\n"
            "    pytest.mark.skipif(not os.getenv('OPENAI_API_KEY'), reason='real LLM'),\n"
            "]\n"
        )
        assert _module_level_credential_skip(ast.parse(snippet)) is None

    def test_scan_reaches_the_known_offenders(self) -> None:
        """The allowlist must describe files that exist and still offend.

        A stale entry is worse than none: it reserves an exemption for a file
        that no longer needs it, and the next reader trusts the list.
        """
        offenders = {
            _relative(path)
            for path in _iter_test_modules()
            if _module_level_credential_skip(ast.parse(path.read_text(encoding="utf-8")))
            is not None
        }
        stale = sorted(set(ALLOWED_ENV_SKIPPED_MODULES) - offenders)
        assert not stale, (
            f"{len(stale)} allowlist entr(ies) no longer skip on a credential — "
            f"delete them from ALLOWED_ENV_SKIPPED_MODULES: {stale}"
        )


class TestNoNewEnvSkippedSuite:
    """The gate itself."""

    def test_no_test_module_disables_itself_on_a_missing_credential(self) -> None:
        violations: list[str] = []
        for path in _iter_test_modules():
            lineno = _module_level_credential_skip(ast.parse(path.read_text(encoding="utf-8")))
            if lineno is None:
                continue
            relative = _relative(path)
            if relative in ALLOWED_ENV_SKIPPED_MODULES:
                continue
            violations.append(f"{relative}:{lineno}")

        assert not violations, (
            f"{len(violations)} test module(s) skip their whole suite when a provider key is "
            f"absent, so CI never runs them: {sorted(violations)}. Mock the provider and keep "
            "the tests unconditional, or mark the file 'integration' so the exclusion is "
            "visible in the CI command. Do NOT add an allowlist entry."
        )
