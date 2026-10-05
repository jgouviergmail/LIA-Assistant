"""Known paid attempts survive failures and cancellation at each direct boundary."""

import asyncio
from contextlib import ExitStack, asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.core.llm_agent_config import LLMAgentConfig
from src.domains.heartbeat.prompts import generate_heartbeat_message
from src.domains.heartbeat.schemas import HeartbeatContext
from src.domains.interests.proactive_task import InterestProactiveTask
from src.domains.psyche.service import PsycheService
from src.domains.user_mcp.description_generation import generate_domain_description
from src.infrastructure.scheduler import interest_subject_clustering, peer_message_delivery
from src.infrastructure.scheduler.reminder_notification import generate_reminder_message

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "caller", ["heartbeat", "interest", "peer", "mcp", "reminder", "psyche", "clustering"]
)
@pytest.mark.parametrize("error_type", [RuntimeError, asyncio.CancelledError])
async def test_direct_paid_attempt_is_settled_once_before_failure_leaves(caller, error_type):
    owner = uuid4()
    failure = error_type("synthetic failure after known usage")
    llm = SimpleNamespace(model="requested-model")
    seen_owners = []

    async def fail(*_args, **kwargs):
        if "user_id" in kwargs:
            seen_owners.append(kwargs["user_id"])
        capture = kwargs["config"]["callbacks"][0]
        request = uuid4()
        capture.on_chat_model_start({}, [], run_id=request)
        capture.on_llm_end(
            LLMResult(
                generations=[
                    [
                        ChatGeneration(
                            message=AIMessage(
                                content="synthetic response",
                                usage_metadata={
                                    "input_tokens": 28,
                                    "output_tokens": 2,
                                    "total_tokens": 30,
                                    "input_token_details": {"cache_read": 20},
                                },
                                response_metadata={"model_name": "returned-model"},
                            )
                        )
                    ]
                ]
            ),
            run_id=request,
        )
        raise failure

    llm.ainvoke = fail
    db = AsyncMock()

    @asynccontextmanager
    async def database():
        yield db

    with ExitStack() as stack:
        stack.enter_context(patch("src.infrastructure.llm.get_llm", return_value=llm))
        stack.enter_context(patch("src.infrastructure.llm.factory.get_llm", return_value=llm))
        stack.enter_context(
            patch(
                "src.infrastructure.llm.invoke_helpers.invoke_with_instrumentation",
                AsyncMock(side_effect=fail),
            )
        )
        stack.enter_context(
            patch("src.infrastructure.proactive.tracking.ambient_run_id", return_value="sweep-run")
        )
        tracked = stack.enter_context(
            patch("src.infrastructure.proactive.tracking.track_proactive_tokens", AsyncMock())
        )
        stack.enter_context(
            patch(
                "src.domains.usage_limits.enforcement.spend_blocked", AsyncMock(return_value=False)
            )
        )
        stack.enter_context(
            patch(
                "src.domains.psyche.service.build_psyche_prompt_block", AsyncMock(return_value="")
            )
        )
        stack.enter_context(
            patch(
                "src.domains.journals.portrait_builder.build_journal_user_model_block",
                AsyncMock(return_value=""),
            )
        )
        if caller == "heartbeat":
            operation = generate_heartbeat_message("draft", HeartbeatContext(), "fr", user_id=owner)
        elif caller == "interest":
            operation = InterestProactiveTask()._present_content(
                "facts", "topic", "general", "wikipedia", [], "fr", user_id=owner
            )
        elif caller == "peer":
            stack.enter_context(patch.object(peer_message_delivery, "get_db_context", database))
            stack.enter_context(
                patch(
                    "src.domains.personalities.service.PersonalityService.get_prompt_instruction_for_user",
                    AsyncMock(return_value=None),
                )
            )
            stack.enter_context(
                patch(
                    "src.domains.agents.middleware.memory_injection.build_psychological_profile",
                    AsyncMock(return_value=("", None, {})),
                )
            )
            operation = peer_message_delivery._generate_delivery_text(
                SimpleNamespace(id=uuid4(), sender_id=owner, content="synthetic directive"),
                SimpleNamespace(id=owner, full_name="Alice"),
                SimpleNamespace(id=uuid4(), language="fr"),
                1,
            )
        elif caller == "mcp":
            operation = generate_domain_description(
                tool_list=[{"name": "echo", "description": "Synthetic tool"}],
                server_name="Lab",
                user_id=owner,
            )
        elif caller == "reminder":
            stack.enter_context(
                patch(
                    "src.core.llm_config_helper.get_llm_config_for_agent",
                    return_value=LLMAgentConfig(
                        provider="openai",
                        model="gpt-5.6-luna",
                        temperature=0.3,
                        max_tokens=1000,
                        top_p=1.0,
                        frequency_penalty=0.0,
                        presence_penalty=0.0,
                    ),
                )
            )
            operation = generate_reminder_message(
                "Remind me",
                "synthetic task",
                datetime.now(UTC),
                "Europe/Paris",
                None,
                [],
                "fr",
                user_id=str(owner),
                run_id="sweep-run",
            )
        elif caller == "psyche":
            service = PsycheService(db)
            state = SimpleNamespace(
                mood_pleasure=0.1,
                mood_arousal=0.1,
                mood_dominance=0.1,
                active_emotions=[],
                relationship_stage="EXPLORATORY",
                relationship_warmth_active=0.5,
                drive_curiosity=0.5,
                drive_engagement=0.5,
                relationship_depth=0.2,
                relationship_trust=0.5,
                relationship_interaction_count=10,
            )
            service.get_or_create_state = AsyncMock(return_value=state)
            service._load_personality_name = AsyncMock(return_value="Default")
            operation = service.generate_summary(owner, "fr")
        else:
            stack.enter_context(
                patch.object(interest_subject_clustering, "get_db_context", database)
            )
            stack.enter_context(
                patch.object(interest_subject_clustering, "get_llm", return_value=llm)
            )
            stack.enter_context(
                patch.object(
                    interest_subject_clustering,
                    "invoke_with_instrumentation",
                    AsyncMock(side_effect=fail),
                )
            )
            rows, user = MagicMock(), MagicMock()
            rows.scalars.return_value.all.return_value = [
                SimpleNamespace(topic="Synthetic topic", category="general")
            ]
            user.scalar_one_or_none.return_value = SimpleNamespace(language="fr")
            db.execute.side_effect = [rows, user]
            operation = interest_subject_clustering.recluster_user_subjects(owner)
        propagates = error_type is asyncio.CancelledError or caller in {
            "heartbeat",
            "peer",
            "clustering",
        }
        if propagates:
            with pytest.raises(error_type) as caught:
                await operation
            assert caught.value is failure
        else:
            await operation
    assert tracked.await_count == 1
    arguments = tracked.await_args.kwargs
    assert arguments["user_id"] == owner
    assert arguments["run_id"] == (
        "sweep-run" if caller in {"heartbeat", "interest", "reminder"} else None
    )
    assert arguments["failed"] is True
    assert (arguments["tokens_in"], arguments["tokens_out"], arguments["tokens_cache"]) == (
        8,
        2,
        20,
    )
    assert len(arguments["billing_records"]) == 1
    assert arguments["billing_records"][0].model_name == "returned-model"
    if seen_owners:
        assert seen_owners == [str(owner)]
