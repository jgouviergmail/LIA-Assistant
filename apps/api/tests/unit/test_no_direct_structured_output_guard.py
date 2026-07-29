"""Systemic guard: structured output must go through the central chokepoint.

One AST scan over every ``src/**/*.py`` file: **no direct
``.with_structured_output(...)`` call outside the chokepoint module**
(``infrastructure/llm/structured_output.py``).

Why this is a guard and not a convention: ``get_structured_output`` carries
the provider-specific constraints that a raw ``with_structured_output`` call
silently bypasses — notably DeepSeek V4 with thinking enabled and Anthropic
with extended thinking, which both REJECT the forced ``tool_choice`` that
``with_structured_output(method="function_calling")`` emits (HTTP 400). The
chokepoint routes those combinations through safe paths (JSON-mode fallback /
auto-tool). A bypass works with the developer's model, then breaks in
production the day an admin flips the LLM override to such a combination.

Measured incident (2026-07-29, prod): ``telephony/return_synthesis.py``
called ``llm.with_structured_output`` directly; the admin override moved
``telephony_synthesis`` to ``deepseek-v4-flash`` with reasoning effort
``high`` → every post-call synthesis failed with ``400 — Thinking mode does
not support this tool_choice`` → the user received the raw English vendor
transcript summary with no structured debrief. Every other structured-output
consumer already went through the chokepoint and was immune.

The scan flags **call expressions** only (``ast.Call`` on an
``ast.Attribute``), so docstring/comment mentions are naturally out of scope
(same design choice as ``test_no_hardcoded_timezone_guard``). The allow-list
is shrink-only: add a file only with a written justification — never weaken
the scan. A self-check test keeps the scan itself from rotting.
"""

import ast
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).parents[2] / "src"

# Files where a direct .with_structured_output(...) call is legitimate:
#   - infrastructure/llm/structured_output.py: THE chokepoint — the only
#     module allowed to talk to LangChain's structured-output API directly.
ALLOWED_FILES: set[str] = {
    "infrastructure/llm/structured_output.py",
}


def _iter_direct_structured_output_calls(tree: ast.AST):
    """Yield the line number of every ``<expr>.with_structured_output(...)`` call."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "with_structured_output"
        ):
            yield node.lineno


class TestStructuredOutputGuardScan:
    """Sanity checks on the scan itself (guards against scan rot)."""

    def test_scan_detects_the_chokepoint_call_sites(self):
        """The scan must detect the calls where they legitimately live."""
        chokepoint = SRC_DIR / "infrastructure" / "llm" / "structured_output.py"
        tree = ast.parse(chokepoint.read_text(encoding="utf-8"))
        linenos = list(_iter_direct_structured_output_calls(tree))
        assert linenos, (
            "The AST scan no longer detects any .with_structured_output(...) call "
            "in infrastructure/llm/structured_output.py — the guard is broken, "
            "fix it before trusting it."
        )

    def test_scan_detects_synthetic_violation_and_ignores_docstrings(self):
        """A real call is flagged; a docstring mention is not."""
        snippet = (
            '"""Docs may mention llm.with_structured_output(schema) freely."""\n'
            "result = llm.with_structured_output(Schema, include_raw=True)\n"
        )
        found = list(_iter_direct_structured_output_calls(ast.parse(snippet)))
        assert found == [2], (
            "The AST scan no longer isolates real .with_structured_output calls "
            f"from docstring mentions (found lines: {found}) — the guard is "
            "broken, fix it before trusting it."
        )


class TestNoDirectStructuredOutputCalls:
    """CI guard: a structured-output bypass outside the chokepoint fails the build."""

    def test_no_direct_with_structured_output_outside_chokepoint(self):
        """Scan all production code for direct .with_structured_output(...) calls."""
        violations: list[str] = []
        for py_file in sorted(SRC_DIR.rglob("*.py")):
            rel_path = py_file.relative_to(SRC_DIR).as_posix()
            if rel_path in ALLOWED_FILES:
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for lineno in _iter_direct_structured_output_calls(tree):
                violations.append(f"src/{rel_path}:{lineno}")

        if violations:
            pytest.fail(
                "Direct .with_structured_output(...) call(s) outside the chokepoint "
                "detected — route the call through get_structured_output / "
                "get_structured_output_with_retry (infrastructure/llm/"
                "structured_output.py), which carries the provider constraints "
                "(DeepSeek V4 thinking, Anthropic extended thinking, OpenAI strict "
                "mode) that a raw call silently bypasses:\n"
                + "\n".join(f"  - {v}" for v in violations)
            )
