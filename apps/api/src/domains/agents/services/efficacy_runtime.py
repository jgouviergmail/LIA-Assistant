"""Bounded cognitive guidance; no new model, tool authority or execution loop."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast

from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.core.run_config import run_id_of
from src.domains.agents.analysis.efficacy_context import (
    EfficacyAnalysis,
    EfficacyTurnContext,
    read_turn_context,
)
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.models import MessagesState
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.efficacy_evidence import current_coverage
from src.domains.agents.services.outcome_evidence import GoalCoverage, coverage_has_gap
from src.domains.psyche.efficacy_contracts import EfficacyProfile
from src.domains.psyche.efficacy_policy import choose_policy, render_policy
from src.domains.psyche.efficacy_repository import EfficacyRepository
from src.domains.psyche.efficacy_service import efficacy_enabled
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


async def capture_efficacy_context(
    analysis: EfficacyAnalysis, config: RunnableConfig
) -> EfficacyTurnContext | None:
    runtime = runtime_context_if_running()
    if runtime is None or runtime.is_automated_source or not runtime.psyche_enabled:
        return None
    if not settings.psyche_enabled:
        return None
    if not (
        settings.psyche_efficacy_collection_enabled or settings.psyche_efficacy_influence_enabled
    ):
        return None
    try:
        async with asyncio.timeout(0.75), get_db_context() as db:
            from src.domains.psyche.repository import PsycheStateRepository

            await PsycheStateRepository(db).lock_reset_owner(runtime.user_id)
            collection = await efficacy_enabled(db, runtime.user_id)
            influence = await efficacy_enabled(db, runtime.user_id, influence=True)
            if not (collection or influence):
                return None
            from src.domains.psyche.service import PsycheService

            if collection:
                await PsycheService(db).get_or_create_state(runtime.user_id)
            epoch = await EfficacyRepository(db).capture_epoch(runtime.user_id)
            await db.commit()
            if epoch is None:
                return None
            return EfficacyTurnContext(
                owner_id=runtime.user_id,
                run_id=run_id_of(config, "unknown"),
                epoch=epoch,
                analysis=analysis,
                issued_at=datetime.now(UTC),
                collection_enabled=collection,
            )
    except Exception as exc:
        logger.warning("efficacy_context_unavailable", error_type=type(exc).__name__)
        return None


async def build_efficacy_block(
    raw: object,
    *,
    run_id: str,
    state: Mapping[str, object] | None = None,
    can_verify: bool = False,
    clarification_resolved: bool = False,
) -> str:
    context = read_turn_context(raw)
    runtime = runtime_context_if_running()
    if (
        context is None
        or runtime is None
        or runtime.is_automated_source
        or runtime.user_id != context.owner_id
        or context.run_id != run_id
        or not runtime.psyche_enabled
    ):
        return ""
    try:
        async with asyncio.timeout(0.75):
            profile = await _current_profile(context)
        if profile is None:
            return ""
        coverage = current_coverage(state) if state is not None else ()
        # Present complete evidence overrides a historical concern. Never request
        # another tool from the final response, which cannot execute one.
        gap = _coverage_gap(coverage) if coverage else context.analysis.verification_needed
        policy = choose_policy(
            profile,
            context.analysis.domains,
            current_gap=gap,
            ambiguous=unresolved_ambiguity(context.analysis, coverage, clarification_resolved),
            can_verify=can_verify,
            budget_available=_budget_available(state),
        )
        if policy.action == "none":
            return ""
        return str(load_prompt("psyche_efficacy_directive")).format(policy=render_policy(policy))
    except Exception as exc:
        logger.warning("efficacy_influence_unavailable", error_type=type(exc).__name__)
        return ""


def _coverage_gap(coverage: tuple[GoalCoverage, ...]) -> bool:
    """A requested goal the outcome vocabulary reads as a gap, or whose outcome is unknown."""
    return any(coverage_has_gap(item) or item.status == "unknown" for item in coverage)


def _budget_available(state: Mapping[str, object] | None) -> bool:
    if state is None:
        return True  # planner still obeys its existing hard plan/permission budget
    from src.domains.agents.utils.react_budget import react_exit_reason

    if state.get("execution_mode") != "react":
        return True
    return react_exit_reason(cast(MessagesState, state)) is None


def efficacy_context_from_state(state: Mapping[str, object]) -> object:
    qi = state.get("query_intelligence")
    return qi.get("efficacy_context") if isinstance(qi, Mapping) else None


def has_available_verifier(tool_names: list[str], mode: str, connector_domains: list[str]) -> bool:
    from src.domains.agents.registry.catalogue import get_tool_category
    from src.domains.agents.semantic.manifest_semantics import available_manifest

    for name in tool_names:
        manifest = available_manifest(name)
        if (
            manifest is not None
            and get_tool_category(manifest) in {"search", "readonly"}
            and manifest.agent.removesuffix("_agent") in connector_domains
            and mode in manifest.execution_modes
        ):
            return True
    return False


async def _current_profile(context: EfficacyTurnContext) -> EfficacyProfile | None:
    from src.domains.psyche.repository import PsycheStateRepository

    if not settings.psyche_enabled or not settings.psyche_efficacy_influence_enabled:
        return None
    async with get_db_context() as db:
        await PsycheStateRepository(db).lock_reset_owner(context.owner_id)
        if not await efficacy_enabled(db, context.owner_id, influence=True):
            return None
        repo = EfficacyRepository(db)
        if await repo.capture_epoch(context.owner_id) != context.epoch:
            return None
        now = datetime.now(UTC)
        if not context.valid_at(now):
            return None
        return await repo.read_profile(
            context.owner_id,
            now=now,
            collection_enabled=settings.psyche_efficacy_collection_enabled,
            influence_enabled=True,
        )


def attach_efficacy_analysis(
    start: EfficacyTurnContext | None, analysis: EfficacyAnalysis
) -> EfficacyTurnContext | None:
    if start is None or not analysis.domains:
        return None
    return start.model_copy(update={"analysis": analysis})


def verifier_available_in_state(state: Mapping[str, object]) -> bool:
    qi = state.get("query_intelligence")
    domains = qi.get("domains") if isinstance(qi, Mapping) else None
    names = state.get("react_tool_names")
    if not isinstance(domains, list) or not isinstance(names, list):
        return False
    return has_available_verifier(
        [name for name in names if isinstance(name, str)],
        "react",
        [domain for domain in domains if isinstance(domain, str)],
    )


def unresolved_ambiguity(
    analysis: EfficacyAnalysis, coverage: tuple[GoalCoverage, ...], resolved: bool
) -> bool:
    if resolved or not analysis.ambiguous:
        return False
    return not (coverage and all(item.status == "satisfied" for item in coverage))
