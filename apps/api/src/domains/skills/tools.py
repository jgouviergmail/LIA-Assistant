"""Skill tools — LangChain tools for skill activation and script execution.

Per agentskills.io client implementation guide (Step 4):
- activate_skill_tool: Dedicated tool pattern for model-driven L2 activation
- run_skill_script: Execute scripts from skill scripts/ directory

Pattern: web_fetch_tools.py (validate_runtime_config → UnifiedToolOutput).
"""

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Annotated, Any

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool

from src.domains.agents.constants import AGENT_QUERY
from src.domains.agents.context.runtime_context import LiaRuntimeContext
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
# Skill import — disk write + DB + cache reload. Raised from 5 when replacement
# confirmation became two-phase: an edit now costs two calls (the refused one
# that describes the impact, then the confirmed one), so the old budget allowed
# only 2.5 edits per minute and a single retry could exhaust it.
_RATE_LIMIT_IMPORT = 10
_RATE_LIMIT_WINDOW = 60


def _coerce_files(
    files: dict[str, Any] | str | None,
) -> tuple[dict[str, str] | None, UnifiedToolOutput | None]:
    """Coerce the ``files`` argument of :func:`import_user_skill` to a str map.

    Mirrors :func:`_coerce_parameters`: some LLMs serialize nested dict tool
    arguments as JSON strings. Accepts a ``dict``, a JSON-object string, or
    ``None``; rejects anything else with a clean failure output. Every value is
    coerced to ``str`` (skill files are text).

    Args:
        files: Raw value received from the tool invocation.

    Returns:
        Tuple ``(coerced_map, failure_output)`` — exactly one is non-None.
    """
    raw: dict[str, Any] | None
    if files is None:
        return None, UnifiedToolOutput.failure(
            message="files is required (map of relative path → text content)",
            error_code="INVALID_INPUT",
        )
    if isinstance(files, dict):
        raw = files
    elif isinstance(files, str):
        try:
            parsed = json.loads(files)
        except json.JSONDecodeError as exc:
            return None, UnifiedToolOutput.failure(
                message=f"files is not a valid JSON string: {exc}",
                error_code="INVALID_INPUT",
            )
        if not isinstance(parsed, dict):
            return None, UnifiedToolOutput.failure(
                message="files JSON must decode to an object (path → content map)",
                error_code="INVALID_INPUT",
            )
        raw = parsed
    else:
        return None, UnifiedToolOutput.failure(
            message=f"files must be a dict or JSON string — got {type(files).__name__}",
            error_code="INVALID_INPUT",
        )

    coerced: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            return None, UnifiedToolOutput.failure(
                message="files keys must be strings (relative file paths)",
                error_code="INVALID_INPUT",
            )
        coerced[key] = value if isinstance(value, str) else str(value)
    return coerced, None


@tool
@track_tool_metrics(
    tool_name="activate_skill",
    agent_name=AGENT_QUERY,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def activate_skill_tool(
    name: Annotated[str, "Name of the skill to activate (from available_skills catalogue)"],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any] | None, InjectedToolArg] = None,
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
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any] | None, InjectedToolArg] = None,
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
            # Strict default: an unresolvable skill gets NO frame privileges.
            # `is_system_skill` grants `credentialless` + `allow-same-origin`
            # on the client iframe, so the permissive fallback would hand a
            # user-imported skill system-level frame privileges (ADR-137).
            is_system = SkillsCache.entry_is_system(skill_info) if skill_info else False
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


class _ResourceTooLarge(Exception):
    """A bundled resource exceeds the read cap (raised inside the worker thread)."""


def _read_resource_file(resource_path: Path) -> tuple[int, str]:
    """Stat, size-check and read one resource file. Runs off the event loop.

    Args:
        resource_path: Absolute path to the resolved resource.

    Returns:
        Tuple of (size in bytes, decoded text).

    Raises:
        FileNotFoundError: Missing file, or a path that is not a regular file.
        _ResourceTooLarge: File exceeds ``SKILLS_RESOURCE_MAX_SIZE_KB``.
        UnicodeDecodeError: File is not valid UTF-8 text.
    """
    from src.core.constants import SKILLS_RESOURCE_MAX_SIZE_KB

    if not resource_path.exists() or not resource_path.is_file():
        raise FileNotFoundError(str(resource_path))
    file_size = resource_path.stat().st_size
    if file_size > SKILLS_RESOURCE_MAX_SIZE_KB * 1024:
        raise _ResourceTooLarge(str(resource_path))
    return file_size, resource_path.read_text(encoding="utf-8")


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
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read a bundled resource file from a skill's directory.

    Per agentskills.io standard L3: on-demand resource loading.
    Use this to read templates, examples, references, or any file
    listed in <skill_resources> after activating a skill.

    Also serves the two files that are NOT advertised as resources —
    ``SKILL.md`` and ``translations.json`` — so a skill can be understood
    before being edited. Activation strips the frontmatter, so without this
    the assistant could never see a skill's own ``description``, ``category``,
    ``priority``, ``plan_template`` or ``outputs``: it could only rewrite it
    blind. They stay out of ``all_resources`` on purpose, to keep every
    activation prompt unchanged.
    """
    config = validate_runtime_config(runtime, "read_skill_resource")
    if isinstance(config, UnifiedToolOutput):
        return config

    from src.core.constants import SKILLS_RESOURCE_MAX_SIZE_KB, SKILLS_RESOURCE_SKIP_FILES
    from src.domains.skills.cache import SkillsCache

    user_id = str(config.user_id)
    skill = SkillsCache.get_by_name_for_user(skill_name, user_id)
    if not skill:
        return UnifiedToolOutput.failure(
            message=f"Skill '{skill_name}' not found",
            error_code="NOT_FOUND",
        )

    # Validate path is a discovered resource, or one of the two manifest files.
    all_resources = skill.get("all_resources", [])
    if path not in all_resources and path not in SKILLS_RESOURCE_SKIP_FILES:
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

    # Disk stat + read are blocking: offload them, like the import pipeline does.
    # An async path must never sit on filesystem I/O — it freezes the loop for
    # every concurrent request, SSE streams included.
    try:
        file_size, content = await asyncio.to_thread(_read_resource_file, resource_path)
    except FileNotFoundError:
        return UnifiedToolOutput.failure(
            message=f"Resource '{path}' not found on disk",
            error_code="NOT_FOUND",
        )
    except _ResourceTooLarge:
        return UnifiedToolOutput.failure(
            message=f"Resource exceeds {SKILLS_RESOURCE_MAX_SIZE_KB}KB limit",
            error_code="VALIDATION_ERROR",
        )
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


async def _resolve_edit_target(
    name: str, user_id: str
) -> tuple[dict[str, Any] | None, UnifiedToolOutput | None]:
    """Resolve an existing skill of that name, rejecting the ones a user cannot edit.

    Three refusals, all deliberate product decisions:

    - a **system** skill is never editable, and no fork is offered;
    - another user's skill is refused without disclosing that it exists;
    - a skill the user has switched off must be re-enabled first — it is absent
      from the injected catalogue, so editing it would silently modify something
      the user believes is inactive.

    Args:
        name: Frontmatter name of the incoming package.
        user_id: Caller's user id.

    Returns:
        ``(existing_skill, None)`` when the name is free (``existing_skill`` is
        None) or points at an editable skill of the caller; ``(None, failure)``
        when the import must be refused.
    """
    from uuid import UUID

    from src.domains.skills.cache import SkillsCache
    from src.domains.skills.preference_service import SkillPreferenceService
    from src.infrastructure.database.session import get_db_context

    # The caller's own skill wins, exactly like the resolution the assistant
    # sees. get_by_name alone returns the first match in ANY scope, so a name
    # held by both a system skill and this user would have been reported as
    # read-only — refusing to edit something the user owns.
    existing = SkillsCache.get_by_name_for_user(name, user_id) or SkillsCache.get_by_name(name)
    if existing is None:
        return None, None

    if existing.get("scope") == "admin":
        return None, UnifiedToolOutput.failure(
            message=(
                f"'{name}' is a system skill and cannot be modified. System skills are "
                "maintained by the administrator."
            ),
            error_code="SYSTEM_SKILL_READ_ONLY",
        )

    if existing.get("owner_id") != user_id:
        # Undifferentiated with a free name would be wrong (the import WILL fail
        # downstream); undifferentiated with "not found" is what protects the
        # other user's privacy — the name is simply unavailable.
        return None, UnifiedToolOutput.failure(
            message=f"The name '{name}' is not available. Choose a different one.",
            error_code="NAME_UNAVAILABLE",
        )

    async with get_db_context() as db:
        active = await SkillPreferenceService(db).get_active_skills_for_user(UUID(user_id))
    if name not in active:
        return None, UnifiedToolOutput.failure(
            message=(
                f"Skill '{name}' is currently disabled. Re-enable it in "
                "Settings > LIA Skills > My Skills before modifying it."
            ),
            error_code="SKILL_DISABLED",
        )

    return existing, None


def replacement_token(name: str, files: dict[str, str]) -> str:
    """Derive the confirmation token binding an approval to one exact package.

    A boolean flag would not be a safeguard: the model can set it on the very
    first call, so "two calls" would be a convention it is free to skip. The
    token cannot be guessed — it is a digest the model can only obtain by first
    receiving the refusal — which is what makes the confirmation *structural*.

    It also closes a subtler hole: because the digest covers the file contents,
    a package altered between the summary and the confirmation no longer
    matches. The user therefore approves exactly what gets written.

    Args:
        name: Frontmatter name of the incoming package.
        files: Incoming file map (relative path → content).

    Returns:
        Short hexadecimal token.
    """
    digest = hashlib.sha256(name.encode("utf-8"))
    for path in sorted(files):
        digest.update(path.encode("utf-8"))
        digest.update(hashlib.sha256(files[path].encode("utf-8")).digest())
    return digest.hexdigest()[:12]


def _describe_replacement(existing: dict[str, Any], files: dict[str, str]) -> UnifiedToolOutput:
    """Refuse an unconfirmed replacement, describing exactly what it would drop.

    Mirrors the unconditional draft confirmation the DevOps tool uses — the HITL
    machinery itself is unavailable here, because skills with scripts run inside
    an isolated ReAct sub-agent whose drafts never reach the main graph.

    Args:
        existing: Cached dict of the skill being replaced.
        files: Incoming file map (relative path → content).

    Returns:
        A structured failure carrying the impact summary and the token that the
        confirming call must echo back.
    """
    from src.core.constants import SKILLS_IMPORT_TEXT_EXTENSIONS

    current = {"SKILL.md", *(existing.get("all_resources") or [])}
    incoming = set(files)
    # Binary assets are carried over by the server, so they are never "lost".
    dropped = sorted(
        path
        for path in current - incoming
        if Path(path).suffix.lower() in SKILLS_IMPORT_TEXT_EXTENSIONS
    )
    added = sorted(incoming - current)

    lines = [f"Replacing the existing skill '{existing['name']}' — confirm with the user first."]
    lines.append(f"Replaced: {', '.join(sorted(current & incoming)) or 'nothing'}")
    if added:
        lines.append(f"Added: {', '.join(added)}")
    if dropped:
        lines.append(f"REMOVED (content lost): {', '.join(dropped)}")
    lines.append(
        "There is no version history: the previous content cannot be restored. "
        "Present this to the user in their language and get their agreement, then "
        "call again with the SAME files and "
        f'replace_token="{replacement_token(str(existing["name"]), files)}". '
        "The token is bound to these exact file contents: change anything and it "
        "no longer applies."
    )
    return UnifiedToolOutput.failure(
        message="\n".join(lines),
        error_code="CONFIRMATION_REQUIRED",
    )


async def _precheck_import(
    files: dict[str, str], user_id: str, *, replace_token: str
) -> UnifiedToolOutput | None:
    """Run every refusal that precedes an import, in one place.

    Kept out of the tool body on purpose: the tool sits at CC 8 without it and
    would land one branch short of the complexity threshold with it inlined —
    crossing that line trips the shrink-only ratchet for the whole backend.

    Args:
        files: Coerced file map of the incoming package.
        user_id: Caller's user id.
        replace_token: Token echoed from a previous refusal, proving the user
            approved this exact package.

    Returns:
        A failure to return verbatim, or None when the import may proceed.
    """
    from src.domains.skills.import_service import parse_incoming_skill_name

    incoming_name, name_error = parse_incoming_skill_name(files)
    if name_error is not None:
        return UnifiedToolOutput.failure(message=name_error, error_code="IMPORT_REJECTED")

    existing, refusal = await _resolve_edit_target(incoming_name, user_id)
    if refusal is not None:
        return refusal
    if existing is not None and replace_token != replacement_token(incoming_name, files):
        return _describe_replacement(existing, files)
    return None


@tool
@track_tool_metrics(
    tool_name="import_user_skill",
    agent_name=AGENT_QUERY,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(max_calls=_RATE_LIMIT_IMPORT, window_seconds=_RATE_LIMIT_WINDOW, scope="user")
async def import_user_skill(
    files: Annotated[
        dict[str, Any] | str,
        (
            "The skill's files as a map of relative path → text content. MUST "
            "include a top-level 'SKILL.md'. Optional resources go under their "
            "standard sub-path, e.g. 'scripts/render.py', 'references/rules.md'. "
            "Either a JSON object (preferred) or a JSON string."
        ),
    ],
    replace_token: Annotated[
        str,
        (
            "Only when replacing an existing skill: the token returned by the "
            "previous CONFIRMATION_REQUIRED refusal, after the user agreed. It "
            "cannot be guessed and is bound to these exact file contents. Leave "
            "empty when creating a new skill."
        ),
    ] = "",
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Import or update a skill in the user's own skills.

    Creating: pass the full file map under a free name — imports immediately.

    Updating: pass the SAME name with the complete regenerated package. The
    whole package is replaced, so send every file the skill needs, not just the
    ones that changed (read the current ones first with ``read_skill_resource``,
    including ``SKILL.md``). The first call is REFUSED and returns exactly what
    the replacement would drop, plus a token: show the summary to the user, then
    call again with the SAME files and that ``replace_token``. The token cannot be
    guessed and is bound to the exact file contents, so the user approves exactly
    what gets written. There is no version history — a replacement cannot
    be undone. Bundled binary assets (the gallery thumbnail) are preserved
    automatically.

    System skills, other users' skills, and skills the user has disabled are
    refused. On any validation error, the failure describes the problem so the
    caller can fix the files and retry.
    """
    coerced_files, coercion_error = _coerce_files(files)
    if coercion_error is not None:
        return coercion_error

    config = validate_runtime_config(runtime, "import_user_skill")
    if isinstance(config, UnifiedToolOutput):
        return config

    from src.core.config import get_settings

    if not getattr(get_settings(), "skills_chat_import_enabled", False):
        return UnifiedToolOutput.failure(
            message="Direct skill import from chat is disabled",
            error_code="FEATURE_DISABLED",
        )

    from uuid import UUID

    from src.core.exceptions import BaseAPIException
    from src.domains.skills.import_service import SkillImportService
    from src.infrastructure.database.session import get_db_context

    refusal = await _precheck_import(
        coerced_files or {}, str(config.user_id), replace_token=replace_token
    )
    if refusal is not None:
        return refusal

    try:
        async with get_db_context() as db:
            skill = await SkillImportService(db).import_files(
                coerced_files or {}, owner_id=UUID(str(config.user_id))
            )
    except BaseAPIException as exc:
        # Surface the validation detail so the LLM can correct and retry.
        return UnifiedToolOutput.failure(
            message=str(getattr(exc, "detail", exc)),
            error_code="IMPORT_REJECTED",
        )

    return UnifiedToolOutput.action_success(
        message=(
            f"Skill '{skill['name']}' imported and active. "
            "It is available in Settings › LIA Skills › My Skills."
        ),
        metadata={
            "skill_name": skill["name"],
            "has_scripts": bool(skill.get("scripts")),
            "resource_count": len(skill.get("all_resources") or []),
        },
    )


# Module-level list for tool_registry auto-discovery
skills_tools = [activate_skill_tool, run_skill_script, read_skill_resource, import_user_skill]
