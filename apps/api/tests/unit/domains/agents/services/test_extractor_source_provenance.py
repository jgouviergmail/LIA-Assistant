"""Host-fabricated history cannot become the person's intent or commitments."""

from contextlib import ExitStack, asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.domains.agents.nodes import initiative_node as initiative
from src.domains.agents.nodes.initiative_schemas import InitiativeDecision
from src.domains.agents.services import jev_extraction_observer as observer
from src.domains.agents.services import open_loop_extractor as loops
from src.domains.agents.weather.catalogue_manifests import get_weather_forecast_catalogue_manifest
from src.domains.shared.extraction_targets import SYNTHETIC_MESSAGE_KEY
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.message_view import as_model_messages

pytestmark = pytest.mark.unit
ACTUAL_REQUEST = "Je dois rappeler le plombier demain."


def _history():
    return as_model_messages(
        [
            HumanMessage(content=ACTUAL_REQUEST),
            AIMessage(content="Merci pour la précision."),
            AIMessage(
                content="PROACTIVE_HOST_PROPOSAL",
                additional_kwargs={"proactive_notification": True},
            ),
            HumanMessage(
                content="HOST_REFUSAL_SCAFFOLD", additional_kwargs={SYNTHETIC_MESSAGE_KEY: True}
            ),
        ]
    )


def test_initiative_query_uses_actual_person_input_after_synthetic_refusal():
    assert initiative._extract_original_query({"messages": _history()}) == ACTUAL_REQUEST


def test_synthetic_only_history_is_not_an_initiative_query():
    assert initiative._extract_original_query({"messages": [_history()[-1]]}) == ""


def test_open_loop_tail_ignores_host_scaffold_and_proactive_proposals():
    assert loops._format_messages_tail(_history()) == (
        f"USER: {ACTUAL_REQUEST}\nASSISTANT: Merci pour la précision."
    )


async def test_native_and_generative_initiative_share_the_actual_request():
    native = AsyncMock(return_value=None)
    generative = AsyncMock(
        return_value=InitiativeDecision(
            analysis="Complete", should_act=False, reasoning="No utility"
        )
    )
    with ExitStack() as stack:
        stack.enter_context(patch.object(initiative.settings, "initiative_enabled", True))
        stack.enter_context(
            patch("src.domains.agents.services.response_context.start_response_context_prefetch")
        )
        for name, value in {
            "runtime_user_id_str": str(uuid4()),
            "_get_adjacent_read_only_manifests": [get_weather_forecast_catalogue_manifest],
            "_format_execution_summary": "Current results",
            "get_llm": MagicMock(),
        }.items():
            stack.enter_context(patch.object(initiative, name, return_value=value))
        stack.enter_context(
            patch.object(initiative, "_load_memory_facts", AsyncMock(return_value=[]))
        )
        stack.enter_context(
            patch.object(initiative, "_load_user_interests", AsyncMock(return_value={}))
        )
        stack.enter_context(patch.object(initiative, "choose_empty_initiative", native))
        stack.enter_context(patch.object(initiative, "get_structured_output", generative))
        await initiative._initiative_core(
            {"messages": _history(), "initiative_iteration": 0, "current_turn_id": 1}, {}
        )

    native_context = native.await_args.kwargs["state"]["context"]
    assert native_context["original_query"] == ACTUAL_REQUEST
    prompt = "\n\n".join(message.text for message in generative.await_args.kwargs["messages"])
    assert ACTUAL_REQUEST in prompt
    assert "HOST_REFUSAL_SCAFFOLD" not in prompt
    assert "PROACTIVE_HOST_PROPOSAL" not in prompt


async def test_open_loop_observer_and_extractor_receive_identical_cleaned_tail():
    repository = MagicMock()
    repository.list_open_for_user = AsyncMock(return_value=[])

    @asynccontextmanager
    async def database():
        session = MagicMock()
        session.commit = AsyncMock()
        yield session

    native = AsyncMock(return_value=DecisionAttempt(outcome="disabled"))
    generative = AsyncMock(return_value=loops.OpenLoopExtraction(items=[]))
    application = AsyncMock(return_value={"opened": 0, "closed": 0, "skipped": 0})
    with (
        patch("src.infrastructure.database.session.get_db_context", database),
        patch("src.domains.open_loops.repository.OpenLoopRepository", return_value=repository),
        patch.object(loops.settings, "open_loops_enabled", True),
        patch("src.infrastructure.llm.get_llm", return_value=MagicMock()),
        patch(
            "src.core.llm_config_helper.get_llm_config_for_agent",
            return_value=SimpleNamespace(provider="openai", model="test-model"),
        ),
        patch("src.infrastructure.llm.structured_output.get_structured_output", generative),
        patch("src.infrastructure.proactive.tracking.track_proactive_tokens", AsyncMock()),
        patch.object(loops, "apply_extraction", application),
        patch.object(observer, "choose_with_jev", native),
        patch.object(observer, "record_action", AsyncMock()),
    ):
        await loops.extract_open_loops_background(
            user_id=str(uuid4()), messages=_history(), session_id="test", run_id="synthetic-test"
        )

    prompt = "\n\n".join(message.text for message in generative.await_args.kwargs["messages"])
    assert native.await_args.kwargs["state"]["extractor_prompt"] == prompt
    assert ACTUAL_REQUEST in prompt
    assert "HOST_REFUSAL_SCAFFOLD" not in prompt
    assert "PROACTIVE_HOST_PROPOSAL" not in prompt
    application.assert_awaited_once()
