"""Skill Bypass Strategy — deterministic plan templates, semantic identification.

OPTIMIZATION: converts a deterministic plan_template → ExecutionPlan without an
LLM planner call when the QueryAnalyzer has semantically identified a matching
skill. Runs first in the strategy chain.

Identification signal: ``QueryIntelligence.detected_skill_name`` — produced by
the QueryAnalyzer via semantic alignment between the user's request and each
skill's description (not by domain overlap or keyword matching).

Scope: only skills with ``plan_template.deterministic = true`` are eligible here.
Non-deterministic skills are left to the LLM planner which shapes plan steps
based on the skill's instructions (model-driven activation).

Per-user isolation: all cache lookups are user-scoped via
``SkillsCache.get_by_name_for_user(name, user_id)`` so that a user's own skill
overrides an admin skill of the same name (per agentskills.io semantics), and
no other user's skill is ever reachable.

Steps whose tools require OAuth scopes the user lacks are filtered out before
building the plan, so users without a given connector get a graceful partial
briefing instead of a validation-fail → replan round-trip.

If no match → falls through to the LLM planner.
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
    """Bypass the LLM planner when QueryAnalyzer identifies a deterministic skill.

    ``requires_catalogue = False`` → bypass group (no tool catalogue needed).

    Matching:
    - ``can_handle`` is a lightweight presence check on
      ``intelligence.detected_skill_name`` (no cache lookup, no user context).
    - ``plan`` performs the user-scoped lookup, checks the skill is deterministic
      and active for the current user, then builds the ExecutionPlan from the
      template (with OAuth scope-based step filtering).

    On any mismatch (skill not found, non-deterministic, inactive, or all steps
    filtered out by scopes), the strategy returns ``PlanningResult(success=False)``
    and the planner falls through to the next strategy (typically the LLM planner).
    """

    requires_catalogue = False

    async def can_handle(
        self,
        intelligence: "QueryIntelligence",
        catalogue: "FilteredCatalogue | None" = None,
    ) -> bool:
        """Return True when the QueryAnalyzer has identified any skill.

        Cheap presence check. The full verification (user-scoped lookup,
        deterministic flag, active skills filter) happens in ``plan`` so that
        user isolation is enforced with the proper ``user_id`` from config.

        Args:
            intelligence: Parsed query intelligence including ``detected_skill_name``.
            catalogue: Unused (kept for strategy interface uniformity).

        Returns:
            True if a skill was semantically identified by the QueryAnalyzer.
        """
        return getattr(intelligence, "detected_skill_name", None) is not None

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
        """Build a deterministic ExecutionPlan from the identified skill's template.

        Enforces user isolation at every lookup and bails out gracefully whenever
        the identified skill is not eligible for deterministic bypass.

        Args:
            intelligence: Query intelligence with ``detected_skill_name``.
            config: Runnable config — ``configurable.user_id`` and
                ``configurable.oauth_scopes`` are read for scoping and filtering.
            catalogue: Unused (virtual catalogue is built from the template).
            validation_feedback: Unused in bypass (no replan).
            clarification_response: Unused in bypass.
            clarification_field: Unused in bypass.
            existing_plan: Unused in bypass.

        Returns:
            ``PlanningResult(success=True)`` when the skill matches and a plan is
            built, otherwise ``PlanningResult(success=False)`` with a reason.
        """
        from src.core.context import active_skills_ctx
        from src.domains.agents.services.planner.planner_utils import (
            build_plan_from_steps,
            create_virtual_catalogue,
        )
        from src.domains.skills.cache import SkillsCache

        skill_name = getattr(intelligence, "detected_skill_name", None)
        if not skill_name:
            return PlanningResult(plan=None, success=False, error="No skill detected")

        user_id = str(config.get("configurable", {}).get("user_id", ""))

        # User-scoped lookup: a user's own skill overrides an admin skill with
        # the same name; skills owned by other users are never reachable.
        skill = SkillsCache.get_by_name_for_user(skill_name, user_id)
        if not skill:
            return PlanningResult(
                plan=None, success=False, error=f"Skill '{skill_name}' not found for user"
            )

        template = skill.get("plan_template") or {}
        is_deterministic = bool(template.get("deterministic"))
        has_scripts = bool(skill.get("scripts"))

        # Script-only skills (no deterministic plan_template) must still bypass
        # the LLM planner — otherwise the planner would generate a spurious plan
        # based on the primary_domain (e.g. "place" → Google Places API calls)
        # before the ReactSubAgentRunner ever gets to execute the skill's own
        # script. Emit an empty plan: parallel_executor handles it gracefully,
        # and response_node then triggers the runner (which discovers the skill
        # via `_skill_needs_runner` and executes the script end-to-end).
        if not is_deterministic and has_scripts:
            active = active_skills_ctx.get()
            if active is not None and skill_name not in active:
                return PlanningResult(
                    plan=None,
                    success=False,
                    error=f"Skill '{skill_name}' is not active for user",
                )
            # ExecutionPlan requires either steps or a documented empty reason.
            # Build directly (skipping build_plan_from_steps) so metadata is
            # complete BEFORE the model_validator runs.
            from src.domains.agents.nodes.utils import extract_session_id_from_config
            from src.domains.agents.orchestration.plan_schemas import ExecutionPlan

            configurable = config.get("configurable", {})
            plan = ExecutionPlan(
                plan_id=f"smart_{configurable.get('run_id', 'unknown')}",
                user_id=str(configurable.get("user_id", "")),
                session_id=extract_session_id_from_config(config, required=False) or "",
                steps=[],
                execution_mode="sequential",
                metadata={
                    "smart_planner": True,
                    "intent": intelligence.immediate_intent,
                    "domains": intelligence.domains,
                    "user_goal": intelligence.user_goal.value,
                    "tokens_estimate": 0,
                    "cardinality_magnitude": intelligence.cardinality_magnitude,
                    "for_each_detected": intelligence.for_each_detected,
                    "skill_name": skill_name,
                    "skill_bypass": True,
                    "skill_bypass_noop": True,
                },
            )
            logger.info(
                "skill_bypass_noop_script_only",
                skill_name=skill_name,
                msg="Empty plan — ReactSubAgentRunner will execute the script",
            )
            return PlanningResult(
                plan=plan,
                success=True,
                used_template=False,
                tokens_used=0,
                tokens_saved=500,
                filtered_catalogue=create_virtual_catalogue(
                    tool_names=[],
                    domains=intelligence.domains or [],
                    is_bypass=True,
                ),
            )

        if not is_deterministic:
            # Non-deterministic skills without scripts fall back to the LLM
            # planner (prompt-expert / advisory archetypes).
            return PlanningResult(
                plan=None, success=False, error=f"Skill '{skill_name}' is not deterministic"
            )

        active = active_skills_ctx.get()
        if active is not None and skill_name not in active:
            return PlanningResult(
                plan=None, success=False, error=f"Skill '{skill_name}' is not active for user"
            )

        steps_data = template.get("steps", [])
        if not steps_data:
            return PlanningResult(
                plan=None, success=False, error=f"Skill '{skill_name}' has no steps"
            )

        # Filter steps whose tools require OAuth scopes the user lacks.
        # This avoids a validation-fail → replan round-trip for users without
        # a given connector (e.g., no Gmail → skip email step gracefully).
        available_scopes = set(config.get("configurable", {}).get("oauth_scopes", []))
        filtered_steps_data = _filter_steps_by_scopes(steps_data, available_scopes)

        if not filtered_steps_data:
            logger.info(
                "skill_bypass_all_steps_filtered",
                skill_name=skill_name,
                reason="No steps remain after scope filtering",
            )
            return PlanningResult(
                plan=None, success=False, error="All skill steps filtered by missing scopes"
            )

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
                skill_name=skill_name,
                error=str(e),
            )
            return PlanningResult(
                plan=None, success=False, error=f"Invalid template for skill '{skill_name}'"
            )

        if not steps:
            return PlanningResult(
                plan=None, success=False, error=f"Skill '{skill_name}' produced no steps"
            )

        skipped_count = len(steps_data) - len(filtered_steps_data)

        plan = build_plan_from_steps(steps, intelligence, config)
        plan.metadata["skill_name"] = skill_name
        plan.metadata["skill_bypass"] = True

        tool_names = [s.tool_name for s in steps if s.tool_name]
        virtual_catalogue = create_virtual_catalogue(
            tool_names=tool_names,
            domains=intelligence.domains or [],
            is_bypass=True,
        )

        logger.info(
            "skill_bypass_matched",
            skill_name=skill_name,
            steps_count=len(steps),
            skipped_steps=skipped_count,
        )
        return PlanningResult(
            plan=plan,
            success=True,
            used_template=True,
            tokens_used=0,
            tokens_saved=500,
            filtered_catalogue=virtual_catalogue,
        )


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
