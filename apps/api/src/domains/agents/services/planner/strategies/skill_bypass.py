"""Skill Bypass Strategy — deterministic plan templates.

OPTIMIZATION ONLY: converts deterministic plan_template → ExecutionPlan without LLM.
The PRIMARY activation mechanism is model-driven (LLM reads catalogue and decides).
This strategy fires BEFORE the LLM planner for skills marked deterministic=true.

Matching: exact domain overlap between query's primary_domain and template agent names.
If no match → falls through to LLM planner which may still activate the skill.

Pattern: ReferenceBypassStrategy, CrossDomainBypassStrategy.
"""

from typing import TYPE_CHECKING, Any

from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType
from src.domains.agents.services.planner.planning_result import PlanningResult
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from src.domains.agents.analysis.query_intelligence import QueryIntelligence
    from src.domains.agents.services.smart_catalogue_service import FilteredCatalogue

logger = get_logger(__name__)

__all__ = ["SkillBypassStrategy"]


class SkillBypassStrategy:
    """Bypass LLM planning when a deterministic skill template matches.

    requires_catalogue = False → bypass group (no catalogue needed).

    Matching logic (conservative — multi-domain coverage):
    - Only deterministic plan_template skills are considered
    - ALL template domains must be covered by the query's detected domains
    - Single-domain queries (e.g., "show events") won't match multi-domain
      skills (e.g., briefing = event+task+weather)
    - If mismatch → no bypass → LLM planner handles it (standard path)
    """

    requires_catalogue = False

    async def can_handle(
        self,
        intelligence: "QueryIntelligence",
        catalogue: "FilteredCatalogue | None" = None,
    ) -> bool:
        from src.core.context import disabled_skills_ctx
        from src.domains.skills.cache import SkillsCache

        if not SkillsCache.is_loaded():
            return False

        query_domains = set(intelligence.domains or [])
        if intelligence.primary_domain:
            query_domains.add(intelligence.primary_domain)
        if not query_domains:
            return False

        disabled = disabled_skills_ctx.get() or set()

        for skill in SkillsCache.get_all():
            if skill["name"] in disabled:
                continue
            template = skill.get("plan_template")
            if not template or not template.get("deterministic"):
                continue

            steps = template.get("steps", [])
            skill_domains = {
                s.get("agent_name", "").replace("_agent", "") for s in steps if s.get("agent_name")
            }
            # ALL template domains must be covered by the query's domains
            if skill_domains and skill_domains.issubset(query_domains):
                return True

        return False

    async def plan(
        self,
        intelligence: "QueryIntelligence",
        config: "RunnableConfig",
        catalogue: "FilteredCatalogue | None" = None,
        validation_feedback: str | None = None,
        clarification_response: str | None = None,
        clarification_field: str | None = None,
        existing_plan: "Any | None" = None,
    ) -> PlanningResult:
        from src.core.context import disabled_skills_ctx
        from src.domains.agents.services.planner.planner_utils import (
            build_plan_from_steps,
            create_virtual_catalogue,
        )
        from src.domains.skills.cache import SkillsCache

        query_domains = set(intelligence.domains or [])
        if intelligence.primary_domain:
            query_domains.add(intelligence.primary_domain)

        disabled = disabled_skills_ctx.get() or set()

        # User-scoped lookup: admin skills + user's own skills (override semantics)
        user_id = config.get("configurable", {}).get("user_id", "")
        skills = SkillsCache.get_for_user(str(user_id)) if user_id else SkillsCache.get_all()

        for skill in sorted(
            skills,
            key=lambda s: s.get("priority", 50),
            reverse=True,
        ):
            template = skill.get("plan_template")
            if not template or not template.get("deterministic"):
                continue
            if skill["name"] in disabled:
                continue

            steps_data = template.get("steps", [])
            skill_domains = {
                s.get("agent_name", "").replace("_agent", "")
                for s in steps_data
                if s.get("agent_name")
            }

            # ALL template domains must be covered by query domains
            if not skill_domains or not skill_domains.issubset(query_domains):
                continue

            # Convert template → ExecutionPlan steps
            steps: list[ExecutionStep] = []
            try:
                for step_data in steps_data:
                    steps.append(
                        ExecutionStep(
                            step_id=step_data["step_id"],
                            step_type=StepType(step_data.get("step_type", "TOOL")),
                            agent_name=step_data["agent_name"],
                            tool_name=step_data.get("tool_name"),
                            parameters=step_data.get("parameters", {}),
                            depends_on=step_data.get("depends_on", []),
                            description=step_data.get("description", ""),
                        )
                    )
            except (KeyError, ValueError) as e:
                logger.warning(
                    "skill_template_invalid",
                    skill_name=skill["name"],
                    error=str(e),
                )
                continue

            if not steps:
                continue

            plan = build_plan_from_steps(steps, intelligence, config)
            plan.metadata["skill_name"] = skill["name"]
            plan.metadata["skill_bypass"] = True

            tool_names = [s.tool_name for s in steps if s.tool_name]
            virtual_catalogue = create_virtual_catalogue(
                tool_names=tool_names,
                domains=intelligence.domains or [],
                is_bypass=True,
            )

            logger.info(
                "skill_bypass_matched",
                skill_name=skill["name"],
                steps_count=len(steps),
            )
            return PlanningResult(
                plan=plan,
                success=True,
                used_template=True,
                tokens_used=0,
                tokens_saved=500,
                filtered_catalogue=virtual_catalogue,
            )

        return PlanningResult(plan=None, success=False, error="No skill matched")
