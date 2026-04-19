"""Skill tools — LangChain tools for skill activation and script execution.

Per agentskills.io client implementation guide (Step 4):
- activate_skill_tool: Dedicated tool pattern for model-driven L2 activation
- run_skill_script: Execute scripts from skill scripts/ directory

Pattern: web_fetch_tools.py (validate_runtime_config → UnifiedToolOutput).
"""

import json
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


def _coerce_parameters(
    parameters: dict[str, Any] | str | None,
) -> tuple[dict[str, Any] | None, UnifiedToolOutput | None]:
    """Coerce the ``parameters`` argument of :func:`run_skill_script` to a dict.

    Some LLMs (notably Qwen) serialize nested ``dict`` tool arguments as JSON
    strings instead of structured objects, causing the tool to be invoked with
    ``parameters = '{"location": "Paris"}'`` rather than
    ``parameters = {"location": "Paris"}``. Pydantic rejects the string, the
    ReAct loop retries indefinitely, and we hit ``GraphRecursionError``.

    This helper normalizes the three accepted forms (``dict``, ``str``,
    ``None``) into a ``dict | None`` usable by the executor, returning a
    clean :class:`UnifiedToolOutput.failure` when the input is an invalid
    JSON string.

    Args:
        parameters: Raw value received from the tool invocation.

    Returns:
        Tuple ``(coerced_dict, failure_output)``. Exactly one element is
        non-None: either the coerced dict (possibly ``None`` for empty input)
        or a failure output describing the validation error.
    """
    if parameters is None or isinstance(parameters, dict):
        return parameters, None

    if not isinstance(parameters, str):
        return None, UnifiedToolOutput.failure(
            message=(
                "parameters must be a dict or a JSON string — " f"got {type(parameters).__name__}"
            ),
            error_code="INVALID_INPUT",
        )

    stripped = parameters.strip()
    if not stripped:
        return None, None

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return None, UnifiedToolOutput.failure(
            message=f"parameters is not a valid JSON string: {exc}",
            error_code="INVALID_INPUT",
        )

    if not isinstance(parsed, dict):
        return None, UnifiedToolOutput.failure(
            message=(
                "parameters JSON must decode to an object (dict), " f"got {type(parsed).__name__}"
            ),
            error_code="INVALID_INPUT",
        )

    return parsed, None


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
    parameters: Annotated[
        dict[str, Any] | str | None,
        (
            "Parameters passed to the script. Either a JSON object "
            "(preferred) or a JSON string — both are accepted and normalized."
        ),
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Execute a Python script from a skill's scripts/ directory."""
    coerced_parameters, coercion_error = _coerce_parameters(parameters)
    if coercion_error is not None:
        return coercion_error

    config = validate_runtime_config(runtime, "run_skill_script")
    if isinstance(config, UnifiedToolOutput):
        return config

    from src.core.config import get_settings

    if not getattr(get_settings(), "skills_scripts_enabled", False):
        return UnifiedToolOutput.failure(
            message="Skill scripts are disabled",
            error_code="FEATURE_DISABLED",
        )

    # Inject runtime context (user language, timezone) into parameters so
    # skill scripts can localize their output without the plan_template having
    # to pass these explicitly. Keys are prefixed with ``_`` to signal they
    # are framework-managed and avoid collisions with user-defined parameters.
    # Explicit user-provided values take precedence.
    runtime_configurable = (
        runtime.config.get("configurable", {}) if runtime and runtime.config else {}
    )
    enriched_parameters: dict[str, Any] = dict(coerced_parameters or {})
    if "_lang" not in enriched_parameters:
        enriched_parameters["_lang"] = runtime_configurable.get("user_language", "en")
    if "_tz" not in enriched_parameters:
        enriched_parameters["_tz"] = runtime_configurable.get("user_timezone", "UTC")

    from src.domains.skills.executor import SkillScriptExecutor

    result = await SkillScriptExecutor.execute(
        skill_name=skill_name,
        script_name=script,
        parameters=enriched_parameters,
        user_id=str(config.user_id),
    )

    if result.success:
        # Parse stdout for rich output contract (text/frame/image).
        # Falls back to plain text wrapping if stdout is not valid JSON —
        # preserves backward compatibility with scripts emitting raw text.
        from src.domains.skills.cache import SkillsCache
        from src.domains.skills.output_builder import build_skill_app_output
        from src.domains.skills.script_output import parse_skill_stdout

        parsed = parse_skill_stdout(result.output)

        # Rich output: emit SKILL_APP registry item for frontend widget.
        if parsed.frame is not None or parsed.image is not None:
            skill_info = SkillsCache.get_by_name_for_user(
                skill_name, str(config.user_id)
            ) or SkillsCache.get_by_name(skill_name)
            is_system = bool(skill_info.get("is_system", True)) if skill_info else True
            return build_skill_app_output(
                output=parsed,
                skill_name=skill_name,
                is_system_skill=is_system,
                execution_time_ms=result.execution_time_ms,
            )

        # Text-only output: preserve legacy behaviour (action_success, no registry).
        return UnifiedToolOutput.action_success(
            message=parsed.text,
            structured_data={"skill_output": parsed.text},
            metadata={
                "skill_name": skill_name,
                "script": script,
                "execution_time_ms": result.execution_time_ms,
            },
        )
    # Return both stdout and stderr so the LLM can read validation results
    # even when the script exits non-zero (e.g., validation errors in stdout,
    # Python traceback in stderr).
    combined = result.output or ""
    if result.error:
        combined = f"{combined}\n[stderr] {result.error}" if combined else result.error
    return UnifiedToolOutput.failure(
        message=combined or "Script execution failed",
        error_code="SCRIPT_ERROR",
        metadata={
            "skill_name": skill_name,
            "script": script,
            "exit_code": result.exit_code,
        },
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
