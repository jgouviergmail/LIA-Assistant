"""Skill Bypass Strategy — deterministic plan templates.

OPTIMIZATION ONLY: converts deterministic plan_template → ExecutionPlan without LLM.
The PRIMARY activation mechanism is model-driven (LLM reads catalogue and decides).
This strategy fires BEFORE the LLM planner for skills marked deterministic=true.

Matching: relaxed domain overlap — allows up to SKILLS_EARLY_DETECTION_MAX_MISSING_DOMAINS
missing domains between query's detected domains and template agent names.
This compensates for the QueryAnalyzer not detecting all domains in composite queries
(e.g., "briefing quotidien" may miss "email" domain).

Steps whose tools require OAuth scopes the user lacks are filtered out before building
the plan, so users without a given connector get a graceful partial briefing instead
of a validation-fail → replan round-trip.

If no match → falls through to LLM planner which may still activate the skill.

Pattern: ReferenceBypassStrategy, CrossDomainBypassStrategy.
"""

from typing import TYPE_CHECKING, Any

from src.core.constants import SKILLS_EARLY_DETECTION_MAX_MISSING_DOMAINS
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

    Matching logic (relaxed — tolerates partial domain coverage):
    - Only deterministic plan_template skills are considered
    - Template domains must be covered by query domains with at most
      SKILLS_EARLY_DETECTION_MAX_MISSING_DOMAINS missing (default: 1)
    - Single-domain queries (e.g., "show events") won't match multi-domain
      skills (e.g., briefing = event+task+weather+email → 3 missing > 1)
    - Steps whose tools require unavailable OAuth scopes are filtered out
    - If mismatch → no bypass → LLM planner handles it (standard path)
    """

    requires_catalogue = False

    async def can_handle(
        self,
        intelligence: "QueryIntelligence",
        catalogue: "FilteredCatalogue | None" = None,
    ) -> bool:
        from src.core.context import active_skills_ctx
        from src.domains.skills.cache import SkillsCache

        if not SkillsCache.is_loaded():
            return False

        query_domains = set(intelligence.domains or [])
        if intelligence.primary_domain:
            query_domains.add(intelligence.primary_domain)
        if not query_domains:
            return False

        active = active_skills_ctx.get()

        for skill in SkillsCache.get_all():
            if active is not None and skill["name"] not in active:
                continue
            template = skill.get("plan_template")
            if not template or not template.get("deterministic"):
                continue

            steps = template.get("steps", [])
            skill_domains = {
                s.get("agent_name", "").replace("_agent", "") for s in steps if s.get("agent_name")
            }
            if not skill_domains:
                continue
            # Relaxed matching: require at least 1 overlapping domain and allow
            # up to N missing. Per-skill override via plan_template.max_missing_domains,
            # falls back to the global constant.
            max_missing = template.get(
                "max_missing_domains", SKILLS_EARLY_DETECTION_MAX_MISSING_DOMAINS
            )
            overlap = len(skill_domains & query_domains)
            missing = len(skill_domains) - overlap
            if overlap >= 1 and missing <= max_missing:
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
        from src.core.context import active_skills_ctx
        from src.domains.agents.services.planner.planner_utils import (
            build_plan_from_steps,
            create_virtual_catalogue,
        )
        from src.domains.skills.cache import SkillsCache

        query_domains = set(intelligence.domains or [])
        if intelligence.primary_domain:
            query_domains.add(intelligence.primary_domain)

        active = active_skills_ctx.get()

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
            if active is not None and skill["name"] not in active:
                continue

            steps_data = template.get("steps", [])
            skill_domains = {
                s.get("agent_name", "").replace("_agent", "")
                for s in steps_data
                if s.get("agent_name")
            }

            # Relaxed matching: require at least 1 overlapping domain and allow
            # up to N missing (same logic as can_handle, per-skill override).
            max_missing = template.get(
                "max_missing_domains", SKILLS_EARLY_DETECTION_MAX_MISSING_DOMAINS
            )
            overlap = len(skill_domains & query_domains)
            missing = len(skill_domains) - overlap
            if not skill_domains or overlap < 1 or missing > max_missing:
                continue

            # Filter steps whose tools require OAuth scopes the user lacks.
            # This avoids a validation-fail → replan round-trip for users without
            # a given connector (e.g., no Gmail → skip email step gracefully).
            available_scopes = set(config.get("configurable", {}).get("oauth_scopes", []))
            filtered_steps_data = _filter_steps_by_scopes(steps_data, available_scopes)

            if not filtered_steps_data:
                logger.info(
                    "skill_bypass_all_steps_filtered",
                    skill_name=skill["name"],
                    reason="No steps remain after scope filtering",
                )
                continue

            # Convert template → ExecutionPlan steps
            steps: list[ExecutionStep] = []
            try:
                for step_data in filtered_steps_data:
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

            skipped_count = len(steps_data) - len(filtered_steps_data)

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
                skipped_steps=skipped_count,
                missing_domains=sorted(skill_domains - query_domains),
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


def _filter_steps_by_scopes(
    steps_data: list[dict],
    available_scopes: set[str],
) -> list[dict]:
    """Filter out template steps whose tools require OAuth scopes the user lacks.

    Steps without a tool_name or whose tool has no required scopes are kept.
    This enables graceful partial execution of multi-domain skill templates
    (e.g., briefing without email for users who haven't connected Gmail).

    After filtering, any ``depends_on`` references pointing to removed steps
    are cleaned up so the dependency graph stays valid.

    Args:
        steps_data: Raw step dicts from plan_template.
        available_scopes: User's granted OAuth scopes (from state/config).

    Returns:
        Filtered list of step dicts (order preserved, depends_on sanitized).
    """
    if not steps_data:
        return steps_data

    # Lazy import: registry is only needed when scopes are checked
    from src.domains.agents.registry import get_global_registry

    registry = get_global_registry()
    filtered: list[dict] = []
    removed_step_ids: set[str] = set()

    for step in steps_data:
        tool_name = step.get("tool_name")
        if not tool_name:
            filtered.append(step)
            continue

        try:
            manifest = registry.get_tool_manifest(tool_name)
        except Exception:
            logger.debug(
                "skill_bypass_tool_manifest_not_found",
                tool_name=tool_name,
            )
            manifest = None

        if not manifest:
            # Tool not registered (e.g., MCP tool) → keep step, let runtime handle it
            filtered.append(step)
            continue

        required = set(manifest.permissions.required_scopes)
        if not required or required.issubset(available_scopes):
            filtered.append(step)
        else:
            removed_step_ids.add(step.get("step_id", ""))
            logger.info(
                "skill_bypass_step_filtered_by_scope",
                tool_name=tool_name,
                missing_scopes=sorted(required - available_scopes),
            )

    # Sanitize depends_on references to removed steps.
    # Shallow-copy affected dicts to avoid mutating the cached skill template.
    if removed_step_ids:
        for i, step in enumerate(filtered):
            deps = step.get("depends_on")
            if deps:
                sanitized = [d for d in deps if d not in removed_step_ids]
                if len(sanitized) != len(deps):
                    filtered[i] = {**step, "depends_on": sanitized}

    return filtered
