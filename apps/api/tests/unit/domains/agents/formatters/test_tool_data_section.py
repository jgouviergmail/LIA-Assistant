"""The response's tool data section: this turn's read steps, bounded and stated (ADR-347)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from prometheus_client import REGISTRY

from src.core.field_names import FIELD_TOOL_DATA
from src.domains.agents.constants import STATE_KEY_AGENT_RESULTS, STATE_KEY_CURRENT_TURN_ID
from src.domains.agents.formatters import tool_data as section_module
from src.domains.agents.formatters.tool_data import tool_data_section, with_tool_data_section

pytestmark = pytest.mark.unit

TURN = 4


def _record(tool: str, text: str, **extra: object) -> dict[str, object]:
    return {"tool": tool, "text": text, "shown": 1, "total": 1, "key": None, **extra}


def _results(*steps: dict[str, object], turn: int = TURN) -> dict[str, object]:
    return {f"{turn}:plan_executor": {"data": {"step_results": list(steps)}}}


def _step(*records: object) -> dict[str, object]:
    return {"result": "ok", FIELD_TOOL_DATA: list(records)}


def _section(results: dict[str, object], budget: int = 10_000) -> str:
    with patch.object(section_module, "slot_tool_result_budget", return_value=budget):
        return tool_data_section(results, TURN)


def _counted(tool: str, reason: str) -> float:
    value = REGISTRY.get_sample_value(
        "pipeline_tool_data_truncated_total", {"tool_name": tool, "reason": reason}
    )
    return value or 0.0


class TestWhatTheModelReads:
    def test_the_turn_s_blocks_follow_the_header_in_plan_order(self) -> None:
        results = _results(
            _step(_record("list_peer_connections_tool", '{"connections": ["Ada"]}')),
            _step(_record("get_route_matrix_tool", '{"durations": [14, 15]}')),
        )

        section = _section(results)

        assert section.startswith("TOOL DATA")
        assert section.index("[list_peer_connections_tool]") < section.index(
            "[get_route_matrix_tool]"
        )
        assert '{"durations": [14, 15]}' in section

    def test_another_turn_s_blocks_are_never_read(self) -> None:
        results = {
            **_results(_step(_record("old_tool", "OLD")), turn=TURN - 1),
            **_results(_step(_record("new_tool", "NEW"))),
        }

        section = _section(results)

        assert "NEW" in section
        assert "OLD" not in section

    def test_a_turn_without_blocks_adds_nothing(self) -> None:
        assert _section(_results({"result": "Reminder created"})) == ""
        assert _section({}) == ""

    def test_a_record_inside_an_envelope_is_read_too(self) -> None:
        envelope = {"success": True, "data": _step(_record("probe_tool", "ENVELOPED"))}

        assert "ENVELOPED" in _section(_results(envelope))

    def test_a_malformed_record_is_ignored(self) -> None:
        results = _results(_step({"tool": "probe_tool"}, {"text": "x"}, "garbage"))

        assert _section(results) == ""


class TestEveryCutIsStated:
    def test_a_paged_block_says_how_much_is_shown(self) -> None:
        before = _counted("probe_tool", "cut")
        record = _record("probe_tool", "{}", truncated=True, shown=3, total=40, key="rows")

        section = _section(_results(_step(record)))

        assert "3 of 40 'rows' items of probe_tool" in section
        assert _counted("probe_tool", "cut") == before + 1

    def test_a_block_cut_whole_names_its_budget(self) -> None:
        record = _record("probe_tool", "{}", truncated=True, budget_tokens=500)

        assert "cut at 500 tokens" in _section(_results(_step(record)))

    def test_the_largest_blocks_are_dropped_first_and_named(self) -> None:
        before = _counted("web_fetch_tool", "dropped")
        small = _record("list_peer_connections_tool", "small " * 20)
        large = _record("web_fetch_tool", "large " * 400)
        medium = _record("get_route_matrix_tool", "medium " * 40)

        section = _section(_results(_step(large), _step(small), _step(medium)), budget=200)

        assert "small" in section and "medium" in section
        assert "large large" not in section
        assert "1 more data block(s) (web_fetch_tool)" in section
        assert _counted("web_fetch_tool", "dropped") == before + 1

    def test_one_block_is_always_kept_even_over_budget(self) -> None:
        section = _section(_results(_step(_record("web_fetch_tool", "large " * 400))), budget=10)

        assert "large" in section
        assert "did not fit" not in section


class TestTheSectionJoinsTheSummaryInTheChainAlone:
    def test_the_summary_comes_first_then_the_blocks(self) -> None:
        state = {
            STATE_KEY_AGENT_RESULTS: _results(_step(_record("probe_tool", "BLOCK"))),
            STATE_KEY_CURRENT_TURN_ID: TURN,
        }
        with patch.object(section_module, "slot_tool_result_budget", return_value=10_000):
            joined = with_tool_data_section("Reminder created", state)

        assert joined.startswith("Reminder created\n\nTOOL DATA")
        assert joined.endswith("BLOCK")

    def test_either_alone_is_returned_alone(self) -> None:
        state = {
            STATE_KEY_AGENT_RESULTS: _results(_step(_record("probe_tool", "BLOCK"))),
            STATE_KEY_CURRENT_TURN_ID: TURN,
        }
        with patch.object(section_module, "slot_tool_result_budget", return_value=10_000):
            assert with_tool_data_section("", state).startswith("TOOL DATA")
            assert with_tool_data_section("Only words", {}) == "Only words"
