"""Both discussion kinds schedule the same learning with an immutable source context."""

from collections.abc import Callable, Coroutine
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.conversation_source import current_conversation_source
from src.core.conversation_target import ConversationKind, ConversationRef
from src.core.run_authority import current_run_authority, run_authority_scope
from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.context.runtime_context import LiaRuntimeContext, runtime_context_if_running
from src.domains.agents.domain_schemas import RouterOutput
from src.domains.agents.models import MessagesState, create_initial_state
from src.domains.agents.nodes import post_response_extractions as scheduler
from src.infrastructure.async_utils import await_run_id_tasks
from tests.fixtures.learning_sources import source_authority
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.unit
ENTRIES = {
    "memory": "src.domains.agents.nodes.post_response_extractions.extract_memories_background",
    "interests": "src.domains.agents.nodes.post_response_extractions.extract_interests_background",
    "open_loops": "src.domains.agents.nodes.post_response_extractions.extract_open_loops_background",
    "journal": "src.domains.journals.extraction_service.extract_journal_entry_background",
    "psyche": "src.domains.psyche.post_response.psyche_post_response_background",
    "recurrence": "src.domains.agents.services.recurrence_ledger.record_occurrence_if_allowed",
}


def _state(target: ConversationRef, run_id: str) -> MessagesState:
    intelligence = QueryIntelligence(
        original_query="Find my appointment",
        english_query="Find my appointment",
        immediate_intent="search",
        immediate_confidence=0.9,
        user_goal=UserGoal.FIND_INFORMATION,
        goal_reasoning="Find an event",
        domains=["event"],
        primary_domain="event",
    )
    return {
        **create_initial_state(target.owner_id, str(target.runtime_id), run_id),
        "messages": [HumanMessage(content="Find my appointment")],
        "query_intelligence": intelligence.to_serializable_dict(),
        "routing_history": [
            RouterOutput(
                intention="action",
                confidence=0.9,
                context_label="general",
                next_node="planner",
                domains=["event"],
            )
        ],
        "user_timezone": DEFAULT_USER_DISPLAY_TIMEZONE,
    }


@pytest.mark.parametrize("kind", list(ConversationKind))
async def test_all_six_background_families_keep_the_source_after_the_parent_scope_exits(
    kind: ConversationKind, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = ConversationRef(uuid4(), uuid4(), kind, 7, uuid4())
    authority = source_authority(target)
    context = LiaRuntimeContext.for_conversation(
        target=target,
        memory_enabled=True,
        journals_enabled=True,
        psyche_enabled=True,
        extraction_revision=4,
        language="de",
    )
    observed: set[str] = set()

    def reader(family: str) -> Callable[..., Coroutine[object, object, int]]:
        async def run(*args: object, **kwargs: object) -> int:
            assert current_conversation_source() == target
            assert runtime_context_if_running() == context
            assert current_run_authority() is (authority if family == "recurrence" else None)
            assert (args[0] if args else kwargs["user_id"]) == str(target.owner_id)
            if family in {"memory", "interests", "journal"}:
                assert kwargs["conversation_id"] == str(target.id)
                assert kwargs["session_id"] == str(target.runtime_id)
            if family == "open_loops":
                assert kwargs["session_id"] == str(target.id)
            if family == "psyche":
                assert kwargs["extraction_revision"] == context.extraction_revision
            observed.add(family)
            return 0

        return run

    for family, path in ENTRIES.items():
        monkeypatch.setattr(path, reader(family))
    for flag in ("open_loops_enabled", "journals_enabled", "psyche_enabled", "habits_enabled"):
        monkeypatch.setattr(settings, flag, True)
    run_id = str(uuid4())
    config: RunnableConfig = {"configurable": {"thread_id": str(target.runtime_id)}}
    with run_authority_scope(authority), installed_runtime_context(context):
        scheduler._schedule_post_response_extractions(
            _state(target, run_id),
            config,
            run_id,
            user_msg_is_trivial=False,
            personality_instruction=None,
            user_message_embedding=None,
            user_language="de",
            final_content="A fictional answer",
            previous_journal_injected_ids=[],
            psyche_appraisal=None,
        )
        assert len(authority.writers) == 1
    assert await await_run_id_tasks(run_id) == len(ENTRIES)
    assert observed == ENTRIES.keys()
    assert not authority.writers
