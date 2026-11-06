"""The skill a plan may carry (audit D2, ADR-370).

The planner's model may tag a plan with a plausible but wrong skill, and the response
node activates what the plan carries: observed, ``interactive-map`` on a diagram whose
steps targeted an MCP server, then a game's skill run after the page the plan had just
written. The analyzer's verdict is authoritative, so a tag that contradicts it stays off
the plan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domains.agents.context.runtime_context import runtime_user_id_str
from src.domains.agents.services.analysis.skill_suppression import contradicting_domain
from src.domains.skills.cache import SkillsCache
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.agents.analysis.query_intelligence import QueryIntelligence

logger = get_logger(__name__)


def resolve_plan_skill_name(
    llm_skill_name: str | None, intelligence: QueryIntelligence
) -> str | None:
    """Validate the planner-emitted ``skill_name`` before it reaches metadata.

    Coherence rules:
        1. No skill_name emitted: nothing to propagate.
        2. It matches ``intelligence.detected_skill_name``: coherent, keep.
        3. The analyzer detected a DIFFERENT skill: the detection is authoritative;
           drop the value (the response node uses the detection) and log the mismatch.
        4. No skill detected, and the primary domain rules a skill out (a page, an MCP
           server): the analyzer settled it; drop.
        5. No skill detected: keep only a real skill of the catalog (user-scoped then
           global); anything else is a hallucination; drop.

    Args:
        llm_skill_name: ``skill_name`` field from the planner's output.
        intelligence: Query intelligence carrying the analyzer's verdict.

    Returns:
        The skill name to store in ``plan.metadata``, or ``None`` to omit it.
    """
    if not llm_skill_name:
        return None

    detected = intelligence.detected_skill_name
    if detected:
        if llm_skill_name == detected:
            return llm_skill_name
        logger.warning(
            "planner_skill_name_mismatch_dropped",
            llm_skill_name=llm_skill_name,
            detected_skill_name=detected,
            msg="Planner emitted a skill_name inconsistent with the "
            "QueryAnalyzer detection; dropping it (detection is authoritative)",
        )
        return None

    contradiction = contradicting_domain(intelligence.domains)
    if contradiction:
        logger.info(
            "planner_skill_name_dropped_by_domain",
            llm_skill_name=llm_skill_name,
            reason=contradiction,
        )
        return None

    if SkillsCache.get_by_name_for_user(llm_skill_name, str(runtime_user_id_str() or "")):
        return llm_skill_name

    logger.warning(
        "planner_skill_name_unknown_dropped",
        llm_skill_name=llm_skill_name,
        msg="Planner emitted a skill_name absent from the catalog; dropping it",
    )
    return None
