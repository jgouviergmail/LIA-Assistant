"""A confirmed draft is a real turn and must feed the extractions (L5 / D2).

Sequence before this lot, for "send Marie a mail saying I'm moving to Lyon":

- turn 1 — the rich message produces a draft and the graph suspends on
  ``interrupt()`` **before** ``response_node``: nothing extracted;
- turn 2 — the confirmation lands in ``response_node``, which returns from the
  draft fast path **before** scheduling: nothing extracted either.

So the whole flow fed neither memory, nor interests, nor the journal — and the
extraction prompt targets the LAST user message, so no later turn recovered it.

What makes the fix exact rather than approximate: draft resumption is a bare
``Command(resume=...)`` with no message injection, so at the fast path the last
message in state is still the original request. These tests pin that.
"""

from contextlib import ExitStack
from unittest.mock import AsyncMock, Mock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.response_node import response_node

USER_ID = "22222222-2222-2222-2222-222222222222"
RICH_MESSAGE = "envoie un mail à Marie pour lui dire que je déménage à Lyon en septembre"


def _patch_collaborators(stack: ExitStack) -> dict[str, Mock]:
    """Neutralize the node's heavy collaborators; return the extraction mocks."""
    mock_get_prompt = stack.enter_context(
        patch("src.domains.agents.nodes.response_node.get_response_prompt")
    )
    mock_get_llm = stack.enter_context(patch("src.domains.agents.nodes.response_node.get_llm"))
    mock_cpt = stack.enter_context(
        patch("src.domains.agents.nodes.response_node.ChatPromptTemplate")
    )
    mock_chain = AsyncMock()
    mock_chain.ainvoke = AsyncMock(return_value=AIMessage(content="ok"))
    mock_prompt_obj = Mock()
    mock_prompt_obj.__or__ = Mock(return_value=mock_chain)
    mock_cpt.from_messages.return_value = mock_prompt_obj
    mock_get_prompt.return_value = "system"
    mock_get_llm.return_value = Mock()

    stack.enter_context(
        patch("src.domains.agents.nodes.post_response_extractions.safe_fire_and_forget")
    )
    stack.enter_context(
        patch(
            "src.domains.agents.services.response_context.build_psychological_profile",
            AsyncMock(return_value=("", Mock(value="neutral"), [])),
        )
    )
    stack.enter_context(
        patch(
            "src.infrastructure.llm.user_message_embedding.get_or_compute_embedding",
            AsyncMock(return_value=None),
        )
    )
    stack.enter_context(
        patch(
            "src.infrastructure.llm.user_message_embedding.is_trivial_message",
            Mock(return_value=False),
        )
    )

    # Sync mocks on purpose: the extractors are `async def`, and the no-op
    # safe_fire_and_forget never awaits them.
    return {
        "memory": stack.enter_context(
            patch(
                "src.domains.agents.nodes.post_response_extractions.extract_memories_background",
                new_callable=Mock,
            )
        ),
        "interest": stack.enter_context(
            patch(
                "src.domains.agents.nodes.post_response_extractions.extract_interests_background",
                new_callable=Mock,
            )
        ),
        "journal": stack.enter_context(
            patch(
                "src.domains.journals.extraction_service.extract_journal_entry_background",
                new_callable=Mock,
            )
        ),
    }


def _state(draft_action: str | None) -> MessagesState:
    state = MessagesState(
        messages=[HumanMessage(content=RICH_MESSAGE)],
        agent_results={},
        metadata={"user_id": "test-user"},
    )
    if draft_action is not None:
        state["draft_action_result"] = {
            "action": draft_action,
            "draft_id": "draft-1",
            "draft_type": "email",
        }
    return state


def _config() -> dict:
    return {
        "metadata": {"run_id": "test-run"},
        "configurable": {
            "langgraph_user_id": USER_ID,
            "thread_id": "thread-1",
            "user_memory_enabled": True,
            "user_journals_enabled": True,
        },
    }


@pytest.mark.unit
class TestDraftFastPathSchedulesExtractions:
    """The three user-visible subsystems must run on a draft turn."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("action", ["confirm", "cancel", "confirm_batch"])
    async def test_every_terminal_draft_action_schedules(self, action: str):
        with ExitStack() as stack:
            mocks = _patch_collaborators(stack)
            await response_node(_state(action), _config())

        mocks["memory"].assert_called_once()
        mocks["interest"].assert_called_once()
        mocks["journal"].assert_called_once()

    @pytest.mark.asyncio
    async def test_extraction_targets_the_original_request(self):
        """Draft resumption injects no message: the rich request is still last."""
        with ExitStack() as stack:
            mocks = _patch_collaborators(stack)
            await response_node(_state("confirm"), _config())

        forwarded = mocks["memory"].call_args.kwargs["messages"]
        assert forwarded[-1].content == RICH_MESSAGE

    @pytest.mark.asyncio
    async def test_fast_path_still_returns_the_short_confirmation(self):
        """Behaviour preserved: scheduling is a side effect, not a rewrite."""
        with ExitStack() as stack:
            _patch_collaborators(stack)
            result = await response_node(_state("confirm"), _config())

        assert result["draft_action_result"] is None
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], AIMessage)

    @pytest.mark.asyncio
    async def test_journal_receives_the_confirmation_text_as_response(self):
        """There was no LLM call on this path — the short message is the response."""
        with ExitStack() as stack:
            mocks = _patch_collaborators(stack)
            result = await response_node(_state("confirm"), _config())

        assert (
            mocks["journal"].call_args.kwargs["assistant_response"] == result["messages"][0].content
        )

    @pytest.mark.asyncio
    async def test_nominal_turn_is_unaffected(self):
        """No draft in state — the normal path keeps scheduling exactly once."""
        with ExitStack() as stack:
            mocks = _patch_collaborators(stack)
            await response_node(_state(None), _config())

        mocks["memory"].assert_called_once()
        mocks["interest"].assert_called_once()
        mocks["journal"].assert_called_once()
