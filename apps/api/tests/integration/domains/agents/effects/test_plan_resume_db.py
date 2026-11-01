"""A resumed plan replayed twice leaves ONE effect row per act, on a real PostgreSQL (spec D7, Hg).

The resume executes the confirmed draft, then runs the step that waited for its
result. LangGraph may execute a node again (a crash, a retry): the second pass
must perform nothing — the draft's key ``draft:{id}`` and the step's key
``{run}:step:{step}`` are each claimed once, the replay served the record.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.tools import StructuredTool
from sqlalchemy import delete, select

from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.models import AgentEffect, EffectStatus
from src.domains.agents.effects.treatments import treatment_collector
from src.domains.agents.nodes.draft_sequence import decision_entry
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType
from src.domains.agents.orchestration.tool_data_projection import without_tool_data
from src.domains.users.models import User

pytestmark = pytest.mark.integration

PERFORMED: list[tuple[str, str]] = []


@pytest.fixture
async def maker(async_engine: Any) -> Any:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest.fixture
async def user(maker: Any) -> Any:
    row = User(
        email=f"resume-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Resume Owner",
    )
    async with maker() as session:
        session.add(row)
        await session.commit()
    yield row
    async with maker() as session:
        await session.execute(delete(User).where(User.id == row.id))
        await session.commit()


def _register(name: str, coroutine: Any, parameter: str, policy: str) -> None:
    from src.domains.agents.registry import get_global_registry
    from src.domains.agents.registry.catalogue import (
        CostProfile,
        ParameterSchema,
        PermissionProfile,
        ToolManifest,
    )
    from src.domains.agents.tools import tool_registry

    tool_registry.register_external_tool(
        StructuredTool.from_function(coroutine=coroutine, name=name, description=name)
    )
    get_global_registry().register_tool_manifest(
        ToolManifest(
            name=name,
            agent="probe_agent",
            description=name,
            parameters=[
                ParameterSchema(name=parameter, type="string", required=True, description="p")
            ],
            outputs=[],
            cost=CostProfile(est_tokens_in=10, est_tokens_out=10),
            permissions=PermissionProfile(required_scopes=[]),
            mutation_policy=policy,  # type: ignore[arg-type]
            mutation_policy_reason="fixture" if policy == "reversible" else None,
        ),
        override=True,
    )


async def _delete(note_id: str) -> Any:
    PERFORMED.append(("delete", note_id))
    return {"success": True, "data": {"deleted_id": note_id}}


async def _label(note_id: str) -> Any:
    PERFORMED.append(("label", note_id))
    return {"success": True, "data": {"labelled": note_id}}


async def _rows(maker: Any, user_id: uuid.UUID) -> list[AgentEffect]:
    async with maker() as session:
        result = await session.execute(
            select(AgentEffect)
            .where(AgentEffect.user_id == user_id)
            .order_by(AgentEffect.idempotency_key)
        )
        return list(result.scalars().all())


class TestAResumedPlanActsOnce:
    async def test_replaying_the_resume_performs_nothing_twice(
        self, maker: Any, user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domains.agents.nodes.plan_resume import held_plan_of, resume_held_steps
        from src.domains.agents.orchestration.parallel_executor import execute_plan_parallel
        from src.domains.agents.tools import tool_registry

        monkeypatch.setattr(tool_registry, "_TOOL_REGISTRY", {})
        monkeypatch.setattr(tool_registry, "_INITIALIZED", True)
        PERFORMED.clear()
        gate_runtime.reset_policy_cache()
        _register("resume_probe_delete_tool", _delete, "note_id", "confirm")
        _register("resume_probe_label_tool", _label, "note_id", "reversible")
        thread = f"thread-{uuid.uuid4().hex[:8]}"
        run = SimpleNamespace(
            user_id=user.id,
            thread_id=thread,
            execution_mode="pipeline",
            is_automated_source=False,
            deps=object(),
            side_channel_queue=None,
        )
        config: dict[str, Any] = {
            "configurable": {"thread_id": thread},
            "metadata": {"run_id": "run-r"},
        }
        plan = ExecutionPlan(
            plan_id="plan-r",
            user_id=str(user.id),
            session_id="s",
            execution_mode="parallel",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_type=StepType.TOOL,
                    agent_name="probe_agent",
                    tool_name="resume_probe_delete_tool",
                    parameters={"note_id": "n-42"},
                ),
                ExecutionStep(
                    step_id="s2",
                    step_type=StepType.TOOL,
                    agent_name="probe_agent",
                    tool_name="resume_probe_label_tool",
                    parameters={"note_id": "$steps.s1.deleted_id"},
                ),
            ],
        )
        with (
            patch(
                "src.domains.agents.context.runtime_context.runtime_context_if_running",
                return_value=run,
            ),
            patch(
                "src.domains.agents.services.draft_executor.runtime_context_if_running",
                return_value=run,
            ),
            patch(
                "src.domains.agents.context.store.get_tool_context_store",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "src.domains.agents.orchestration.parallel_executor._load_execution_contexts",
                new=AsyncMock(return_value={}),
            ),
            treatment_collector(run_id="run-r"),
        ):
            first = await execute_plan_parallel(plan, config, "run-r", turn_id=1)
            (draft,) = first.pending_drafts
            state: dict[str, Any] = {
                "execution_plan": plan,
                "completed_steps": without_tool_data(first.completed_steps),
                "held_plan": held_plan_of(plan, first, previous=None),
                "draft_action_result": decision_entry(draft, "confirm"),
                "current_turn_id": 1,
                "user_language": "en",
                "registry": dict(first.registry),
                "agent_results": {},
                "messages": [],
            }
            await resume_held_steps(state, config, "run-r")  # type: ignore[arg-type]
            await resume_held_steps(state, config, "run-r")  # type: ignore[arg-type]

        assert PERFORMED == [("delete", "n-42"), ("label", "n-42")], "each act once"
        acts = [row for row in await _rows(maker, user.id) if row.status is EffectStatus.SUCCEEDED]
        assert sorted(row.idempotency_key for row in acts) == sorted(
            [f"draft:{draft.draft_id}", "run-r:step:s2"]
        ), "one row per act, each act claimed once"
