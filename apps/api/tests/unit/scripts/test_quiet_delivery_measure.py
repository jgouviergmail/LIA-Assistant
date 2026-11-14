"""The quiet-delivery measurement asks what production asks, and reads what production reads.

The script is a paid, on-demand measurement (never a gate): nothing would see it drift
from the response node it imitates — a prompt without the delivery instruction, a ReAct
turn built like a pipeline one, a declaration read by another rule — and its numbers
would then measure something else. These tests hold its deterministic halves; no model
is asked, a scripted one answers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage

from scripts.routines import measure_quiet_delivery as bench
from src.core.config import settings
from src.core.time_utils import now_in_timezone
from src.domains.agents.constants import STATE_KEY_AGENT_RESULTS
from src.domains.agents.formatters.tool_data import tool_data_section
from src.domains.agents.services import nothing_new
from src.domains.agents.services.nothing_new import quiet_run_scope
from src.domains.diagnostics import failure_context

pytestmark = pytest.mark.unit

ZONE = "Europe/Paris"
SCENARIOS = {scenario.key: scenario for scenario in bench.SCENARIOS}
TAG = "<lia_nothing_new/>"


@pytest.fixture(autouse=True)
def _a_platform_with_nothing_to_report(monkeypatch: pytest.MonkeyPatch) -> None:
    async def nothing() -> list[Any]:
        return []

    monkeypatch.setattr(settings, "diagnostics_enabled", True)
    monkeypatch.setattr(failure_context, "get_active_degradations", nothing)
    nothing_new._declared.clear()


async def _turn(key: str, mode: bench.Mode) -> bench.Turn:
    with quiet_run_scope(True):
        return await bench._turn(SCENARIOS[key], mode, ZONE, "fr", f"test-{key}-{mode}")


def test_every_scenario_states_what_is_expected_of_it() -> None:
    assert {key: scenario.silence_expected for key, scenario in SCENARIOS.items()} == {
        "nothing_found": True,
        "something_found": False,
        "condition_unmet": True,
        "condition_met": False,
        "same_as_before": None,
    }


@pytest.mark.parametrize("mode", bench.MODES)
async def test_the_instruction_is_production_s_and_given_only_in_a_quiet_run(
    mode: bench.Mode,
) -> None:
    turn = await _turn("nothing_found", mode)

    assert bench.INSTRUCTION_MARKER in turn.system_prompt
    # Outside a quiet run the prompt builder injects nothing: the bench refuses
    # to measure an instruction it did not get from production.
    with pytest.raises(SystemExit):
        await bench._turn(SCENARIOS["nothing_found"], mode, ZONE, "fr", "outside")


async def test_a_react_turn_hands_the_loop_s_answer_and_drops_it_from_the_history() -> None:
    scenario = SCENARIOS["condition_met"]
    answer = scenario.react_answer(now_in_timezone(ZONE).date())

    turn = await _turn("condition_met", "react")

    assert turn.summary == answer
    assert [type(message) for message in turn.messages] == [HumanMessage]
    assert all(answer not in str(message.content) for message in turn.messages)


async def test_a_pipeline_turn_hands_the_step_s_data_and_no_loop_answer() -> None:
    turn = await _turn("nothing_found", "pipeline")

    assert turn.summary == ""
    section = tool_data_section(turn.state[STATE_KEY_AGENT_RESULTS], bench.TURN)
    assert "get_emails_tool" in section and '"total": 0' in section


async def test_the_previous_run_stays_in_the_history_of_a_run_that_repeats_it() -> None:
    turn = await _turn("same_as_before", "react")

    assert [type(message) for message in turn.messages] == [HumanMessage, AIMessage, HumanMessage]


@pytest.mark.parametrize(
    ("key", "answer", "declared", "correct"),
    [
        pytest.param("nothing_found", f"Rien de nouveau.\n{TAG}", True, True, id="silent-rightly"),
        pytest.param("nothing_found", "Aucune facture.", False, False, id="needless-notice"),
        pytest.param("something_found", f"Une facture.\n{TAG}", True, False, id="missed-notice"),
        pytest.param("something_found", "Une facture est arrivée.", False, True, id="told"),
        pytest.param("same_as_before", f"Toujours la même.\n{TAG}", True, None, id="observed"),
        # A tag cut short is written, and declares nothing: production's rule.
        pytest.param("nothing_found", "Rien.\n<lia_nothing_new", False, False, id="cut-short"),
    ],
)
async def test_a_run_reads_the_declaration_through_the_production_seam(
    key: str, answer: str, declared: bool, correct: bool | None
) -> None:
    run = await bench._run(
        SCENARIOS[key], "react", "scripted", FakeListChatModel(responses=[answer]), ZONE, "fr"
    )

    assert run.error == ""
    assert (run.declared, run.correct) == (declared, correct)
    assert run.tag_written is ("<lia_nothing_new" in answer)
    assert "<lia_nothing_new" not in run.answer_excerpt


def test_the_summary_counts_each_model_mode_and_scenario_apart() -> None:
    runs = [
        bench.Run("m", "react", "nothing_found", True, declared=True, correct=True),
        bench.Run("m", "react", "nothing_found", True, declared=False, correct=False),
        bench.Run("m", "pipeline", "nothing_found", True, error="TimeoutError: slow"),
    ]

    rows = bench._summary(runs).splitlines()[2:]

    assert rows == [
        "| m | react | nothing_found | 2 | silence | 1/2 | 0/2 | 1/2 | 0 | 0 | 0.0000 |",
        "| m | pipeline | nothing_found | 1 | silence | 0/0 | 0/0 | 0/0 | 0 | 1 | 0.0000 |",
    ]


async def test_the_platform_is_stated_like_the_data_not_read_from_the_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Measured 2026-11-13: dev's open alert reached the answers and kept them from silence."""
    from src.domains.diagnostics.advisor import CapabilityDegradation

    async def degraded() -> list[CapabilityDegradation]:
        return [CapabilityDegradation("platform", "critical", "open_incident:Disk", None)]

    monkeypatch.setattr(failure_context, "get_active_degradations", degraded)

    turn = await _turn("nothing_found", "react")

    assert turn.honesty_chars == 0
    assert "open_incident:Disk" not in turn.system_prompt
    # The instance's own advisor is back once the turn is built.
    assert failure_context.get_active_degradations is degraded


async def test_another_instruction_is_measured_in_place_of_the_versioned_one(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate.txt"
    candidate.write_text("<delivery_declaration>\nA CANDIDATE RULE\n</delivery_declaration>")

    with bench._instruction(candidate) as variant:
        turn = await _turn("nothing_found", "pipeline")

    assert variant == "candidate"
    assert "A CANDIDATE RULE" in turn.system_prompt
    # The versioned file speaks again once the measurement is over.
    assert "A CANDIDATE RULE" not in (await _turn("nothing_found", "pipeline")).system_prompt
    with bench._instruction(None) as variant:
        assert variant == "current"


def test_the_modes_asked_are_the_ones_named() -> None:
    # The families are named one way for every bench (`scripts/llm_families.py`).
    assert bench._parse_modes(None) == ["pipeline", "react"]
    assert bench._parse_modes("react") == ["react"]
    with pytest.raises(SystemExit):
        bench._parse_modes("batch")
