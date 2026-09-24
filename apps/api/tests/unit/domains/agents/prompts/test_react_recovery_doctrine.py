"""The ReAct doctrine recovers before it concludes (ADR-310).

Measured on 2026-09-23: the prompt recovered only on an ERROR or an EMPTY result,
so a forecast served for the wrong day (a success) was never retried; and it
told the loop to give up on cross-checks (« Never stall the primary intent for
secondary enrichment »), which the weather of a trip was. These tests read the
real prompts.
"""

from __future__ import annotations

import pytest

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.domains.agents.prompts.prompt_loader import load_prompt

pytestmark = pytest.mark.unit


def _static(name: str) -> str:
    return load_prompt(name).split(DYNAMIC_CONTEXT_MARKER, 1)[0]


class TestTheReactPrompt:
    def test_a_result_is_verified_against_the_request(self) -> None:
        assert "VERIFY" in _static("react_agent_prompt")

    def test_the_ladder_replaces_the_narrow_triggers(self) -> None:
        static = _static("react_agent_prompt")
        assert "RECOVERY LADDER" in static
        assert "Never stall the primary intent for secondary enrichment" not in static
        assert "SELF-CORRECTION & RECOVERY" not in static
        assert "ZERO-RESULT HANDLING" not in static

    def test_the_final_message_declares_gaps_and_fallback_sources(self) -> None:
        static = _static("react_agent_prompt")
        assert "<unresolved>" in static and "(fallback)" in static

    def test_the_exemplar_passes_no_relative_date(self) -> None:
        assert 'date="tomorrow"' not in load_prompt("react_agent_prompt")

    def test_no_attempt_count_is_promised(self) -> None:
        """A prompt states what the code enforces (ADR-284): nothing counts attempts per fact."""
        assert "2 alternate attempts" not in load_prompt("react_agent_prompt")

    def test_only_what_was_set_out_for_is_declared(self) -> None:
        """Measured on the ADR-310 bench (2026-09-24): on a clean turn two model
        families of three declared details nobody had asked for, and one declared a
        fact it held from a web search — each bought a pass that could change nothing.
        What is declared is tied to what the loop DID: the facts it set out to obtain."""
        final = _static("react_agent_prompt").split("<FinalResponse>", 1)[1]
        assert "you set out to obtain" in final
        assert "fact obtained from another source" in final
        assert "the facts you set out to obtain" in load_prompt("react_recovery_directive")

    def test_a_detail_never_looked_up_is_not_a_gap(self) -> None:
        """Measured on the bench's full run: a listing of appointments declared their
        durations and places unresolved « for an overlap check » nobody had asked for,
        and a model wrote the block only to say that nothing was missing."""
        final = _static("react_agent_prompt").split("<FinalResponse>", 1)[1]
        assert "you never looked up" in final
        assert "write no block at all" in final

    def test_a_started_cross_check_is_never_dropped_in_silence(self) -> None:
        """Measured on the incident's replay (2026-09-24): 4 runs of 9 called the
        forecast once, got the wrong day and left the weather out without a word —
        the 2026-09-23 give-up, made silent. A fact the loop set out to obtain ends
        obtained or declared."""
        obstacles = _static("react_agent_prompt").split("OBSTACLES:", 1)[1].split("\n", 1)[0]
        assert "each cross-check you started" in obstacles
        assert "never dropped in silence" in obstacles

    def test_the_pass_rewrites_the_whole_answer(self) -> None:
        """Measured on the bench's full run: told to « conclude again », a model wrote a
        final message about its gaps alone, and the list its draft held never reached
        the answer — the pass had destroyed a complete answer."""
        assert "restates every finding" in load_prompt("react_recovery_directive")

    def test_the_directive_names_the_ladder_the_prompt_defines(self) -> None:
        """The recovery directive refers to the ladder by the prompt's own name."""
        assert "RECOVERY LADDER" in load_prompt("react_recovery_directive")


def test_the_script_rung_lives_where_the_sandbox_is_bound() -> None:
    """ADR-284: a prompt promises only what the turn can run — the sandbox rung is
    in the <Computation> block, rendered only when run_python_tool is bound."""
    assert "RECOVERY LADDER" in load_prompt("react_computation_prompt")
    assert "run_python_tool" not in _static("react_agent_prompt")


def test_the_response_states_fallback_sources_and_gaps() -> None:
    authority = load_prompt("response_system_prompt_base").split("<DataAuthority>", 1)[1]
    authority = authority.split("</DataAuthority>", 1)[0]
    assert "fallback source" in authority and "unresolved" in authority
