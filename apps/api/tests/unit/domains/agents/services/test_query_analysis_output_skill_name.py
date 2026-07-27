"""The analyzer's ``skill_name`` is normalised at the parsing boundary.

The prompt instructs the model to "leave it null" in prose, and the structured
output runs with ``strict_mode: false`` — so the model writes the four
characters ``null``, which every ``if skill_name:`` in the pipeline reads as a
detected skill. Measured 2026-07-27 against production (deepseek-v4-flash):
84 to 100% of analyses of a plain "create an image of a cat" came back that way,
including on the real ``analyze_full`` path (20/20).

Normalising here — rather than at each consumer — is what keeps the chat
override from logging ``chat_override_cleared_skill_name(skill_name="null")``,
a line that claims a skill was cleared when none was ever detected.
"""

from __future__ import annotations

import pytest

from src.domains.agents.services.query_analyzer_service import QueryAnalysisOutput

pytestmark = pytest.mark.unit


def _output(skill_name: object) -> QueryAnalysisOutput:
    """Build a minimal analysis output carrying ``skill_name``.

    Args:
        skill_name: Raw value as the LLM would emit it.

    Returns:
        The parsed model.
    """
    return QueryAnalysisOutput(
        intent="action",
        english_query="create a realistic image of a cat",
        reasoning="probe",
        skill_name=skill_name,  # type: ignore[arg-type]
    )


class TestSentinelNormalisation:
    """Textual stand-ins for "no value" must land as ``None``."""

    @pytest.mark.parametrize(
        "raw", ["null", "NULL", "Null", " null ", "none", "None", "nil", "undefined", "n/a", "-"]
    )
    def test_sentinel_becomes_none(self, raw: str) -> None:
        assert _output(raw).skill_name is None

    @pytest.mark.parametrize("raw", ["", "   ", "\t\n"])
    def test_blank_becomes_none(self, raw: str) -> None:
        assert _output(raw).skill_name is None

    def test_absent_field_stays_none(self) -> None:
        assert (
            QueryAnalysisOutput(
                intent="action", english_query="probe", reasoning="probe"
            ).skill_name
            is None
        )


class TestRealNamesSurvive:
    """Normalisation must not eat legitimate detections."""

    def test_real_name_is_preserved(self) -> None:
        assert _output("briefing-quotidien").skill_name == "briefing-quotidien"

    def test_real_name_is_stripped(self) -> None:
        assert _output("  interactive-map\n").skill_name == "interactive-map"

    def test_name_merely_containing_a_sentinel_survives(self) -> None:
        """Substring match would be a bug: only the WHOLE value is a sentinel."""
        assert _output("nullify-notes").skill_name == "nullify-notes"
        assert _output("none-the-wiser").skill_name == "none-the-wiser"
