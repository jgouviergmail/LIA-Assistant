"""Unit tests for sub-agent analysis wrapping in `_extract_action_success_messages`.

`delegate_to_sub_agent_tool` returns a UnifiedToolOutput with
`structured_data = {"type": "sub_agent_analysis", "analysis": <full text>,
"expertise": <persona>, ...}`. The parallel executor flattens
`structured_data` into the step result dict, so by the time the result
reaches `_extract_action_success_messages`, the dict contains the keys
`type`, `analysis`, `expertise` alongside the regular `result` field
(which is the 200-char truncated summary).

`_extract_action_success_messages` must recognise this case and wrap the
FULL `analysis` with a deterministic `<SubAgentAnalysis>` tag, so the
response_node's `<SubAgentDeliveryOverride>` block can detect it without
relying on LLM heuristics over markdown structure / voice / length.

These tests cover the detection logic, the tag wrapping format, the
expertise attribute sanitisation, and the no-duplication invariant.
"""

from __future__ import annotations

import pytest

from src.domains.agents.formatters.agent_results import (
    _extract_action_success_messages,
    _wrap_subagent_analysis,
)


@pytest.mark.unit
class TestWrapSubagentAnalysis:
    """Direct tests on the wrapper helper."""

    def test_basic_wrap_round_trip(self):
        """The wrapper produces the expected `<SubAgentAnalysis expertise="...">...</SubAgentAnalysis>` form."""
        result = _wrap_subagent_analysis(
            analysis_text="# Report\n\nKey finding: X.",
            expertise="senior analyst, AI markets",
        )
        assert result.startswith('<SubAgentAnalysis expertise="senior analyst, AI markets">\n')
        assert result.endswith("\n</SubAgentAnalysis>")
        assert "# Report\n\nKey finding: X." in result

    def test_expertise_with_double_quotes_is_sanitised(self):
        """Double quotes in expertise are replaced with single quotes (would otherwise break the attribute)."""
        result = _wrap_subagent_analysis(
            analysis_text="content",
            expertise='analyst "senior level"',
        )
        # The expertise attribute value must not contain unescaped double quotes
        assert "expertise=\"analyst 'senior level'\"" in result

    def test_expertise_with_newlines_is_flattened(self):
        """Newlines in expertise are replaced with spaces to keep the tag on one line."""
        result = _wrap_subagent_analysis(
            analysis_text="content",
            expertise="line one\nline two\nline three",
        )
        first_line = result.split("\n", 1)[0]
        assert first_line == '<SubAgentAnalysis expertise="line one line two line three">'

    def test_expertise_is_truncated_to_120_chars(self):
        """Very long expertise strings are truncated to 120 chars (keeps the tag readable)."""
        long_expertise = "a" * 500
        result = _wrap_subagent_analysis(analysis_text="x", expertise=long_expertise)
        # Extract the attribute value
        start = result.index('expertise="') + len('expertise="')
        end = result.index('"', start)
        assert end - start == 120

    def test_empty_expertise_defaults_to_expert(self):
        """Empty / None expertise falls back to a sensible default so the tag stays valid."""
        result = _wrap_subagent_analysis(analysis_text="x", expertise="")
        assert 'expertise="expert"' in result


@pytest.mark.unit
class TestExtractActionSuccessMessagesSubAgentDetection:
    """`_extract_action_success_messages` detects sub-agent analyses and wraps them."""

    def test_sub_agent_analysis_is_wrapped_with_tag(self):
        """A step result with `type == "sub_agent_analysis"` gets wrapped."""
        data = {
            "step_results": [
                {
                    "type": "sub_agent_analysis",
                    "analysis": "# Market Report 2026\n\nFull expert text here…",
                    "expertise": "senior analyst, AI markets",
                    "result": "Truncated summary up to 200 chars…",
                }
            ]
        }
        messages = _extract_action_success_messages(data)
        assert len(messages) == 1
        msg = messages[0]
        assert msg.startswith("<SubAgentAnalysis expertise=")
        assert msg.endswith("</SubAgentAnalysis>")
        # The FULL analysis (not the truncated summary) is what reaches the LLM
        assert "# Market Report 2026" in msg
        assert "Full expert text here" in msg
        # The truncated summary is NOT duplicated alongside the wrapped analysis
        assert "Truncated summary up to 200 chars" not in msg

    def test_regular_action_success_is_not_wrapped(self):
        """A non-sub-agent result (e.g. reminder creation) is returned untouched."""
        data = {
            "step_results": [
                {
                    "result": "🔔 Reminder created for tomorrow at 14:00",
                }
            ]
        }
        messages = _extract_action_success_messages(data)
        assert messages == ["🔔 Reminder created for tomorrow at 14:00"]

    def test_type_present_but_analysis_missing_falls_back_to_regular(self):
        """If `type` is the marker but `analysis` is missing, the normal extraction kicks in (defensive)."""
        data = {
            "step_results": [
                {
                    "type": "sub_agent_analysis",
                    "result": "Some result without an analysis key",
                }
            ]
        }
        messages = _extract_action_success_messages(data)
        # No SubAgentAnalysis tag because `analysis` is missing
        assert all("<SubAgentAnalysis" not in m for m in messages)
        # But the regular `result` is still surfaced (defensive: don't lose data)
        assert "Some result without an analysis key" in messages

    def test_mixed_sub_agent_and_regular_results(self):
        """A plan with both a sub-agent step and a regular action step surfaces both messages."""
        data = {
            "step_results": [
                {
                    "type": "sub_agent_analysis",
                    "analysis": "Expert text",
                    "expertise": "X",
                    "result": "summary",
                },
                {
                    "result": "🔔 Reminder created",
                },
            ]
        }
        messages = _extract_action_success_messages(data)
        assert len(messages) == 2
        assert any("<SubAgentAnalysis" in m and "Expert text" in m for m in messages)
        assert "🔔 Reminder created" in messages

    def test_multiple_sub_agents_each_get_their_own_tag(self):
        """Two parallel sub-agents → two distinct `<SubAgentAnalysis>` blocks."""
        data = {
            "step_results": [
                {
                    "type": "sub_agent_analysis",
                    "analysis": "Analysis A",
                    "expertise": "expert A",
                    "result": "...",
                },
                {
                    "type": "sub_agent_analysis",
                    "analysis": "Analysis B",
                    "expertise": "expert B",
                    "result": "...",
                },
            ]
        }
        messages = _extract_action_success_messages(data)
        assert len(messages) == 2
        assert 'expertise="expert A"' in messages[0]
        assert "Analysis A" in messages[0]
        assert 'expertise="expert B"' in messages[1]
        assert "Analysis B" in messages[1]

    def test_aggregated_results_path_also_supports_wrapping(self):
        """The aggregated_results path (FOR_EACH-style) also detects sub-agent analyses."""
        data = {
            "aggregated_results": [
                {
                    "type": "sub_agent_analysis",
                    "analysis": "Per-expert analysis",
                    "expertise": "specialist X",
                    "result": "...",
                }
            ]
        }
        messages = _extract_action_success_messages(data)
        assert len(messages) == 1
        assert "<SubAgentAnalysis" in messages[0]
        assert "Per-expert analysis" in messages[0]

    def test_empty_data_returns_empty_list(self):
        """No data → no messages."""
        assert _extract_action_success_messages({}) == []
