"""Skill tools — LangChain tools for skill activation and script execution.

Per agentskills.io client implementation guide (Step 4):
- activate_skill_tool: Dedicated tool pattern for model-driven L2 activation
- run_skill_script: Execute scripts from skill scripts/ directory

Pattern: web_fetch_tools.py (validate_runtime_config → UnifiedToolOutput).
"""

from typing import Annotated, Any

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool

from src.domains.agents.constants import AGENT_QUERY
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.agents.utils.rate_limiting import rate_limit
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

# Rate limit constants (per-user, per minute)
_RATE_LIMIT_SCRIPT = 5  # subprocess execution — conservative
_RATE_LIMIT_RESOURCE = 20  # file reads — more permissive
_RATE_LIMIT_WINDOW = 60


@tool
@track_tool_metrics(
    tool_name="activate_skill",
    agent_name=AGENT_QUERY,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def activate_skill_tool(
    name: Annotated[str, "Name of the skill to activate (from available_skills catalogue)"],
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Load a skill's full instructions and bundled resources listing.

    Per agentskills.io standard: dedicated tool activation pattern.
    Call this when a task matches a skill's description from the catalogue.
    Returns the skill's instructions wrapped in structured tags.
    """
    config = validate_runtime_config(runtime, "activate_skill")
    if isinstance(config, UnifiedToolOutput):
        return config

    from src.domains.skills.activation import activate_skill

    content = activate_skill(name, user_id=str(config.user_id))
    if not content:
        return UnifiedToolOutput.failure(
            message=f"Skill '{name}' not found",
            error_code="NOT_FOUND",
        )

    return UnifiedToolOutput.action_success(
        message=content,
        metadata={"skill_name": name, "activation": "dedicated_tool"},
    )


@tool
@track_tool_metrics(
    tool_name="run_skill_script",
    agent_name=AGENT_QUERY,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(max_calls=_RATE_LIMIT_SCRIPT, window_seconds=_RATE_LIMIT_WINDOW, scope="user")
async def run_skill_script(
    skill_name: Annotated[str, "Name of the skill containing the script"],
    script: Annotated[str, "Script filename (e.g., 'extract.py')"],
    parameters: Annotated[dict[str, Any] | None, "Parameters passed to the script"] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Execute a Python script from a skill's scripts/ directory."""
    config = validate_runtime_config(runtime, "run_skill_script")
    if isinstance(config, UnifiedToolOutput):
        return config

    from src.core.config import get_settings

    if not getattr(get_settings(), "skills_scripts_enabled", False):
        return UnifiedToolOutput.failure(
            message="Skill scripts are disabled",
            error_code="FEATURE_DISABLED",
        )

    from src.domains.skills.executor import SkillScriptExecutor

    result = await SkillScriptExecutor.execute(
        skill_name=skill_name,
        script_name=script,
        parameters=parameters or {},
        user_id=str(config.user_id),
    )

    if result.success:
        return UnifiedToolOutput.action_success(
            message=result.output,
            structured_data={"skill_output": result.output},
            metadata={
                "skill_name": skill_name,
                "script": script,
                "execution_time_ms": result.execution_time_ms,
            },
        )
    return UnifiedToolOutput.failure(
        message=result.error or "Script execution failed",
        error_code="INTERNAL_ERROR",
        metadata={"skill_name": skill_name, "script": script},
    )


@tool
@track_tool_metrics(
    tool_name="read_skill_resource",
    agent_name=AGENT_QUERY,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(max_calls=_RATE_LIMIT_RESOURCE, window_seconds=_RATE_LIMIT_WINDOW, scope="user")
async def read_skill_resource(
    skill_name: Annotated[str, "Name of the skill containing the resource"],
    path: Annotated[
        str, "Relative path to the resource (e.g., 'template.md', 'examples/sample.md')"
    ],
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read a bundled resource file from a skill's directory.

    Per agentskills.io standard L3: on-demand resource loading.
    Use this to read templates, examples, references, or any file
    listed in <skill_resources> after activating a skill.
    """
    config = validate_runtime_config(runtime, "read_skill_resource")
    if isinstance(config, UnifiedToolOutput):
        return config

    from pathlib import Path

    from src.core.constants import SKILLS_RESOURCE_MAX_SIZE_KB
    from src.domains.skills.cache import SkillsCache

    user_id = str(config.user_id)
    skill = SkillsCache.get_by_name_for_user(skill_name, user_id)
    if not skill:
        return UnifiedToolOutput.failure(
            message=f"Skill '{skill_name}' not found",
            error_code="NOT_FOUND",
        )

    # Validate path is in discovered resources
    all_resources = skill.get("all_resources", [])
    if path not in all_resources:
        return UnifiedToolOutput.failure(
            message=f"Resource '{path}' not found in skill '{skill_name}'",
            error_code="NOT_FOUND",
        )

    # Path traversal protection (consistent with executor.py)
    skill_dir = Path(skill["source_path"]).parent
    resource_path = (skill_dir / path).resolve()
    try:
        resource_path.relative_to(skill_dir.resolve())
    except ValueError:
        return UnifiedToolOutput.failure(
            message="Path traversal detected",
            error_code="VALIDATION_ERROR",
        )

    if not resource_path.exists() or not resource_path.is_file():
        return UnifiedToolOutput.failure(
            message=f"Resource '{path}' not found on disk",
            error_code="NOT_FOUND",
        )

    # Size check
    file_size = resource_path.stat().st_size
    if file_size > SKILLS_RESOURCE_MAX_SIZE_KB * 1024:
        return UnifiedToolOutput.failure(
            message=f"Resource exceeds {SKILLS_RESOURCE_MAX_SIZE_KB}KB limit",
            error_code="VALIDATION_ERROR",
        )

    try:
        content = resource_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return UnifiedToolOutput.failure(
            message=f"Resource '{path}' is not a text file",
            error_code="VALIDATION_ERROR",
        )

    return UnifiedToolOutput.action_success(
        message=content,
        metadata={
            "skill_name": skill_name,
            "resource_path": path,
            "size_bytes": file_size,
        },
    )


# Module-level list for tool_registry auto-discovery
skills_tools = [activate_skill_tool, run_skill_script, read_skill_resource]
