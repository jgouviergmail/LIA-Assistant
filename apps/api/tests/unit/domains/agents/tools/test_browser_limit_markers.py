"""The browser tool's limit markers must match what the browser layer WRITES.

``browser_navigate_tool`` decides ``RATE_LIMIT_EXCEEDED`` from a substring of
the ``ValueError`` the pool raises. The marker read « Max concurrent » while
``pool.py`` writes « Maximum concurrent », so that branch could never be true:
a saturated pool fell through to ``CONFIGURATION_ERROR``, and the model was
told to fix a setting where it should have waited (ADR-303).

Nothing linked the two files. This test does — until typed exceptions remove
the reading entirely.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.domains.agents.tools.browser_tools import (
    BROWSER_LIMIT_MARKERS,
    _is_browser_limit_error,
)

pytestmark = [pytest.mark.unit]

BROWSER_DIR = Path(__file__).parents[5] / "src" / "infrastructure" / "browser"


def _raised_messages() -> list[str]:
    """Every literal text the browser layer raises inside a ``ValueError``.

    Reads the f-string parts too: ``pool.py`` builds its sentence from several
    pieces, and the marker lives in the first one.
    """
    messages: list[str] = []
    for path in sorted(BROWSER_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                continue
            for arg in node.exc.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    messages.append(arg.value)
                elif isinstance(arg, ast.JoinedStr):
                    messages.append(
                        "".join(
                            part.value
                            for part in arg.values
                            if isinstance(part, ast.Constant) and isinstance(part.value, str)
                        )
                    )
    return messages


class TestMarkersMatchTheirProducers:
    """A marker nobody's message contains is a branch nobody can reach."""

    def test_every_marker_is_found_in_a_real_raised_message(self) -> None:
        raised = _raised_messages()
        assert raised, "no ValueError message found — the scan is broken, not the code"
        for marker in BROWSER_LIMIT_MARKERS:
            assert any(marker in message for message in raised), (
                f"« {marker} » appears in no message the browser layer raises. "
                f"Messages found: {raised}"
            )

    def test_the_pool_saturation_message_is_recognised(self) -> None:
        """The exact defect: « Maximum concurrent » must read as a limit."""
        assert _is_browser_limit_error("Maximum concurrent browser sessions reached (3/3)")

    def test_the_navigation_cap_message_is_recognised(self) -> None:
        assert _is_browser_limit_error("Max navigations per session reached")

    def test_an_unrelated_refusal_is_not_a_limit(self) -> None:
        assert not _is_browser_limit_error("URL blocked: private address")
