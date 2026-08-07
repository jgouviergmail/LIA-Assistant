"""Characterization tests for ``response_node`` (Feathers golden-master net).

These tests pin the CURRENT observable behavior of ``response_node`` — NOT the
desired behavior — so that the upcoming decomposition of the ~2200-line function
into cohesive helpers can be proven behavior-preserving. Every assertion below
was verified GREEN against the pre-refactoring code.

The single most important contract protected here is the exact SET of keys the
node writes into its returned ``state_update`` dict, on each distinct return
path (nominal LLM synthesis, draft fast-path, LLM timeout). A dropped or added
key is exactly the "undeclared key silently dropped by the MessagesState
reducer" trap that the extraction must never introduce.

Heavy collaborators (LLM chain, prompt loader, psychological profile fetch,
embedding model, background fire-and-forget scheduling) are patched to run the
node end-to-end deterministically, mirroring ``test_response_node.py``.
"""

from collections.abc import Coroutine
from contextlib import ExitStack
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.core.i18n_api_messages import APIMessages
from src.domains.agents.constants import (
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_MESSAGES,
    STATE_KEY_TURN_TYPE,
    TURN_TYPE_ACTION,
)
from src.domains.agents.drafts.models import DraftAction
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.response_node import (
    STATE_KEY_DRAFT_ACTION_RESULT,
    response_node,
)
from src.domains.agents.prompts import get_error_fallback_message

_RESP = "src.domains.agents.nodes.response_node"


def _close_scheduled_coroutine(coro: Coroutine[Any, Any, Any], **_kwargs: Any) -> None:
    """Stand in for ``safe_fire_and_forget`` without leaking its coroutine.

    Args:
        coro: The coroutine the production code scheduled.
        **_kwargs: ``name`` / ``run_id``, irrelevant to a double.
    """
    coro.close()


# Exact key set written by the nominal LLM-synthesis return path (no ReAct
# passthrough, no skill registry). Extraction MUST preserve this set verbatim.
NOMINAL_STATE_UPDATE_KEYS = {
    STATE_KEY_MESSAGES,
    "content_final_replacement",
    STATE_KEY_DRAFT_ACTION_RESULT,
    "current_turn_registry",
    "knowledge_enrichment_result",
    "memory_injection_debug",
    "rag_injection_debug",
    "journal_injection_debug",
    "injected_journal_ids",
}


def _patch_collaborators(
    stack: ExitStack,
    *,
    llm_response: str = "ok",
    chain_side_effect: BaseException | None = None,
) -> dict[str, Mock]:
    """Patch response_node's heavy collaborators for deterministic end-to-end runs.

    Returns handles on the ``get_llm`` factory mock and the synthesis ``chain``
    mock so tests can assert which LLM type was requested and whether the LLM
    was actually invoked (fast-paths skip it).
    """
    mock_get_prompt = stack.enter_context(patch(f"{_RESP}.get_response_prompt"))
    mock_get_llm = stack.enter_context(patch(f"{_RESP}.get_llm"))
    mock_cpt = stack.enter_context(patch(f"{_RESP}.ChatPromptTemplate"))

    mock_chain = AsyncMock()
    if chain_side_effect is not None:
        mock_chain.ainvoke.side_effect = chain_side_effect
    else:
        mock_chain.ainvoke = AsyncMock(return_value=AIMessage(content=llm_response))

    mock_prompt_obj = Mock()
    mock_prompt_obj.__or__ = Mock(return_value=mock_chain)
    mock_cpt.from_messages.return_value = mock_prompt_obj
    mock_get_prompt.return_value = "system"
    mock_get_llm.return_value = Mock()

    # A fire-and-forget double OWNS the coroutine it is handed. A bare Mock
    # drops it, and "coroutine 'extract_open_loops_background' was never
    # awaited" then fires at the next collection — which the autouse finalizer
    # in conftest deliberately forces at teardown, so the warning lands on a
    # PASSING test and rots there. Closing is the honest no-op: nothing runs,
    # nothing leaks. `test_response_node.py` solves the same problem by making
    # each extractor a sync Mock; closing at the boundary also covers whatever
    # extractor is scheduled next.
    stack.enter_context(
        patch(
            "src.domains.agents.nodes.post_response_extractions.safe_fire_and_forget",
            side_effect=_close_scheduled_coroutine,
        )
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
    return {"get_llm": mock_get_llm, "chain": mock_chain}


def _base_config() -> dict:
    return {"metadata": {"run_id": "char-run"}}


@pytest.mark.asyncio
async def test_char_nominal_return_contract_exact_key_set():
    """A plain conversational turn writes EXACTLY the nominal state_update keys.

    Golden master over the MessagesState contract: this is the assertion that
    catches any extraction dropping/adding a returned key (reducer trap).
    """
    state = MessagesState(
        messages=[HumanMessage(content="Bonjour")],
        agent_results={},
        metadata={"user_id": "u"},
    )
    with ExitStack() as stack:
        _patch_collaborators(stack, llm_response="Salut !")
        result = await response_node(state, _base_config())

    assert set(result.keys()) == NOMINAL_STATE_UPDATE_KEYS
    assert len(result[STATE_KEY_MESSAGES]) == 1
    assert isinstance(result[STATE_KEY_MESSAGES][0], AIMessage)
    assert result[STATE_KEY_MESSAGES][0].content == "Salut !"
    # No post-processing modification (no registry/widget/psyche) -> None sentinel.
    assert result["content_final_replacement"] is None
    # Draft slot is always cleared to prevent cross-turn persistence.
    assert result[STATE_KEY_DRAFT_ACTION_RESULT] is None
    # No ReAct passthrough and no skill registry -> those optional keys are absent.
    assert STATE_KEY_AGENT_RESULTS not in result
    assert "registry" not in result


@pytest.mark.asyncio
async def test_char_react_passthrough_merges_agent_results():
    """ReAct passthrough injects the agent's final answer and returns agent_results.

    When ``react_agent_result.final_message`` is present, the node merges it under
    the ``{turn}:react_agent`` key and echoes agent_results back in state_update
    (persistence by contract, F5).
    """
    state = MessagesState(
        messages=[HumanMessage(content="Question")],
        agent_results={},
        metadata={"user_id": "u"},
    )
    state["react_agent_result"] = {"final_message": "Réponse ReAct", "iteration_count": 2}
    state["current_turn_id"] = 0

    with ExitStack() as stack:
        _patch_collaborators(stack, llm_response="Reformulé")
        result = await response_node(state, _base_config())

    assert STATE_KEY_AGENT_RESULTS in result
    assert "0:react_agent" in result[STATE_KEY_AGENT_RESULTS]
    merged = result[STATE_KEY_AGENT_RESULTS]["0:react_agent"]
    assert merged["data"]["react_synthesis"] == "Réponse ReAct"


@pytest.mark.asyncio
async def test_char_vision_attachment_switches_to_vision_llm():
    """An image attachment on the current turn selects the ``vision_analysis`` LLM."""
    from src.domains.attachments.models import AttachmentContentType

    state = MessagesState(
        messages=[HumanMessage(content="Décris cette image")],
        agent_results={},
        metadata={
            "user_id": "u",
            "current_turn_attachments": [
                {"content_type": AttachmentContentType.IMAGE, "file_id": "f1"}
            ],
        },
    )

    with ExitStack() as stack:
        mocks = _patch_collaborators(stack, llm_response="Une image")
        # build_vision_message_async loads base64 from disk -> stub it out.
        stack.enter_context(
            patch(
                "src.domains.attachments.llm_content.build_vision_message_async",
                AsyncMock(return_value=HumanMessage(content="multimodal")),
            )
        )
        result = await response_node(state, _base_config())

    mocks["get_llm"].assert_any_call("vision_analysis")
    assert set(result.keys()) == NOMINAL_STATE_UPDATE_KEYS


@pytest.mark.asyncio
async def test_char_draft_confirm_fast_path_skips_llm():
    """A confirmed draft short-circuits: no LLM call, minimal 3-key state_update."""
    state = MessagesState(
        messages=[HumanMessage(content="ok")],
        agent_results={},
        metadata={"user_id": "u"},
    )
    state[STATE_KEY_DRAFT_ACTION_RESULT] = {
        "action": DraftAction.CONFIRM.value,
        "draft_id": "d1",
        "draft_type": "email",
    }

    with ExitStack() as stack:
        mocks = _patch_collaborators(stack)
        # Bypass the real draft executor: the fast-path is what we characterize.
        stack.enter_context(
            patch(f"{_RESP}._execute_draft_if_confirmed", AsyncMock(return_value=None))
        )
        result = await response_node(state, _base_config())

    mocks["chain"].ainvoke.assert_not_called()
    assert set(result.keys()) == {
        STATE_KEY_MESSAGES,
        STATE_KEY_DRAFT_ACTION_RESULT,
        "current_turn_registry",
    }
    assert result[STATE_KEY_DRAFT_ACTION_RESULT] is None
    assert result[STATE_KEY_MESSAGES][0].content == APIMessages.draft_action_completed("fr")


@pytest.mark.asyncio
async def test_char_draft_cancel_fast_path_message():
    """A cancelled draft short-circuits with the localized cancellation message."""
    state = MessagesState(
        messages=[HumanMessage(content="annule")],
        agent_results={},
        metadata={"user_id": "u"},
    )
    state[STATE_KEY_DRAFT_ACTION_RESULT] = {
        "action": DraftAction.CANCEL.value,
        "draft_id": "d1",
        "draft_type": "email",
    }

    with ExitStack() as stack:
        mocks = _patch_collaborators(stack)
        stack.enter_context(
            patch(f"{_RESP}._execute_draft_if_confirmed", AsyncMock(return_value=None))
        )
        result = await response_node(state, _base_config())

    mocks["chain"].ainvoke.assert_not_called()
    assert result[STATE_KEY_MESSAGES][0].content == APIMessages.draft_cancelled("fr")


@pytest.mark.asyncio
async def test_char_llm_timeout_returns_error_only_contract():
    """LLM timeout returns ONLY a messages key with the localized fallback."""
    state = MessagesState(
        messages=[HumanMessage(content="Question longue")],
        agent_results={},
        metadata={"user_id": "u"},
        user_language="en",
    )

    with ExitStack() as stack:
        _patch_collaborators(stack, chain_side_effect=TimeoutError())
        result = await response_node(state, _base_config())

    assert set(result.keys()) == {STATE_KEY_MESSAGES}
    assert result[STATE_KEY_MESSAGES][0].content == get_error_fallback_message(
        "TimeoutError", language="en"
    )


@pytest.mark.asyncio
async def test_char_plan_rejection_runs_full_synthesis():
    """A rejected plan does NOT fast-path: it formats the rejection and calls the LLM."""
    state = MessagesState(
        messages=[HumanMessage(content="Supprime tous mes emails")],
        agent_results={},
        metadata={"user_id": "u"},
    )
    state["plan_rejection_reason"] = "Action destructive refusée par l'utilisateur"
    state[STATE_KEY_TURN_TYPE] = TURN_TYPE_ACTION

    with ExitStack() as stack:
        mocks = _patch_collaborators(stack, llm_response="D'accord, je ne supprime rien.")
        result = await response_node(state, _base_config())

    mocks["chain"].ainvoke.assert_called_once()
    assert set(result.keys()) == NOMINAL_STATE_UPDATE_KEYS
    assert result[STATE_KEY_MESSAGES][0].content == "D'accord, je ne supprime rien."


@pytest.mark.asyncio
async def test_char_skill_react_fast_path_uses_runner_answer():
    """A script skill runs the ReAct sub-agent; its answer becomes the response.

    Characterizes the SKILL ACTIVATION block + skill-react fast-path: when the
    query-analyzer-detected skill has scripts, ``ReactSubAgentRunner`` produces
    the final answer, the main synthesis LLM is skipped, and a synthetic
    ``activate_skill_tool`` call is attached so the frontend shows the badge.
    """
    from types import SimpleNamespace

    state = MessagesState(
        messages=[HumanMessage(content="Lance mon skill")],
        agent_results={},
        metadata={"user_id": "u"},
    )
    state["query_intelligence"] = {"detected_skill_name": "my_skill"}

    skill_data = {
        "scripts": ["run.py"],
        "references": [],
        "source_path": "/skills/my_skill/SKILL.md",
    }
    fake_run_result = SimpleNamespace(
        iteration_count=1,
        final_message="Réponse du skill",
        duration_ms=42,
        accumulated_registry={},
    )
    runner_instance = Mock()
    runner_instance.run = AsyncMock(return_value=fake_run_result)

    with ExitStack() as stack:
        mocks = _patch_collaborators(stack)
        stack.enter_context(patch(f"{_RESP}.settings.skills_enabled", True))
        # active_skills_ctx defaults to None (no restriction) -> no patch needed.
        stack.enter_context(
            patch("src.domains.skills.cache.SkillsCache.get_always_loaded", Mock(return_value=[]))
        )
        stack.enter_context(
            patch(
                "src.domains.skills.cache.SkillsCache.get_by_name_for_user",
                Mock(return_value=skill_data),
            )
        )
        stack.enter_context(
            patch("src.domains.skills.cache.SkillsCache.get_by_name", Mock(return_value=skill_data))
        )
        stack.enter_context(patch("src.domains.skills.tools.skills_tools", []))
        stack.enter_context(
            patch(
                "src.domains.agents.tools.react_runner.ReactSubAgentRunner",
                Mock(return_value=runner_instance),
            )
        )
        result = await response_node(state, _base_config())

    # Main synthesis LLM skipped — the skill runner's answer is authoritative.
    mocks["chain"].ainvoke.assert_not_called()
    msg = result[STATE_KEY_MESSAGES][0]
    assert msg.content == "Réponse du skill"
    assert msg.tool_calls
    assert msg.tool_calls[0]["name"] == "activate_skill_tool"
    assert msg.tool_calls[0]["args"] == {"name": "my_skill"}


@pytest.mark.asyncio
async def test_char_interactive_widget_injection_sets_content_replacement():
    """Post-LLM widget HTML is appended and signals a content replacement.

    Characterizes the V3 HTML rendering seam: when the current turn carries an
    interactive widget, its HTML is appended to the LLM answer, the final message
    content is rewritten, and ``content_final_replacement`` carries the merged
    content so the frontend replaces the streamed text.
    """
    state = MessagesState(
        messages=[HumanMessage(content="Montre l'app")],
        agent_results={},
        metadata={"user_id": "u"},
    )

    with ExitStack() as stack:
        _patch_collaborators(stack, llm_response="Voici")
        # Force a non-empty current-turn registry and a deterministic widget render.
        stack.enter_context(
            patch(
                f"{_RESP}._filter_registry_by_current_turn",
                Mock(return_value={"w1": {"type": "MCP_APP", "payload": {}}}),
            )
        )
        stack.enter_context(
            patch(
                f"{_RESP}.generate_html_for_interactive_widgets",
                Mock(return_value="<div>WIDGET</div>"),
            )
        )
        result = await response_node(state, _base_config())

    final = result[STATE_KEY_MESSAGES][0].content
    assert final == "Voici\n\n<div>WIDGET</div>"
    assert result["content_final_replacement"] == final
