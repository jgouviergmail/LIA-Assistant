"""Wiring tests: open-loop extraction as 5th post-response background task (P5).

`_schedule_post_response_extractions` must schedule the open-loop extraction
under the SAME guards as the sibling extractions (automated source, trivial
message) plus the global flag.
"""

from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import pytest
from langchain_core.messages import HumanMessage

from src.domains.agents.nodes.post_response_extractions import (
    _schedule_post_response_extractions,
)
from tests.helpers.runtime_context import installed_runtime_context, make_runtime_context


def _state():
    return {"messages": [HumanMessage(content="je dois rappeler le plombier demain")]}


#: The config the node receives carries thread plumbing only (ADR-231).
_CONFIG = {"configurable": {"thread_id": "thread-1"}}


def _context(*, automated: bool = False):
    """The run context the scheduler reads: identity plus the user's preferences."""
    return make_runtime_context(
        user_id=UUID("11111111-1111-1111-1111-111111111111"),
        thread_id="thread-1",
        conversation_id="thread-1",
        is_automated_source=automated,
        memory_enabled=False,
        journals_enabled=False,
        psyche_enabled=False,
    )


def _call(state, context, *, flag_on: bool = True):
    """Invoke the scheduler with every sibling extraction neutralized."""
    captured: list = []
    config = _CONFIG

    def _fake_fire_and_forget(coro, *, name="", run_id=None):
        captured.append((name, coro))
        coro.close()  # prevent un-awaited coroutine warnings

    with (
        installed_runtime_context(context),
        patch(
            "src.domains.agents.nodes.post_response_extractions.safe_fire_and_forget",
            side_effect=_fake_fire_and_forget,
        ),
        patch(
            "src.domains.agents.nodes.post_response_extractions.settings",
            SimpleNamespace(
                open_loops_enabled=flag_on,
                journals_enabled=False,
                psyche_enabled=False,
            ),
        ),
    ):
        _schedule_post_response_extractions(
            state,
            config,
            "run-1",
            user_msg_is_trivial=False,
            personality_instruction=None,
            user_message_embedding=None,
            user_language="fr",
            final_content="Noté !",
            previous_journal_injected_ids=[],
            psyche_appraisal=None,
        )
    return captured


@pytest.mark.unit
class TestOpenLoopExtractionWiring:
    def test_scheduled_when_flag_on_and_message_meaningful(self):
        captured = _call(_state(), _context(), flag_on=True)
        names = [name for name, _ in captured]
        assert any(name.startswith("open_loop_extraction_") for name in names)

    def test_not_scheduled_when_flag_off(self):
        captured = _call(_state(), _context(), flag_on=False)
        names = [name for name, _ in captured]
        assert not any(name.startswith("open_loop_extraction_") for name in names)

    def test_not_scheduled_for_automated_source(self):
        captured = _call(_state(), _context(automated=True), flag_on=True)
        names = [name for name, _ in captured]
        assert not any(name.startswith("open_loop_extraction_") for name in names)
