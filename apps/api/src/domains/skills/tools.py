"""Skill tools — LangChain tools for skill activation and script execution.

Per agentskills.io client implementation guide (Step 4):
- activate_skill_tool: Dedicated tool pattern for model-driven L2 activation
- run_skill_script: Execute scripts from skill scripts/ directory

Pattern: web_fetch_tools.py (validate_runtime_config → UnifiedToolOutput).
"""

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool

from src.core.constants import DEFAULT_TIMEZONE
from src.core.i18n import resolve_language
from src.domains.agents.constants import AGENT_QUERY
from src.domains.agents.context.runtime_context import LiaRuntimeContext, tool_runtime_context
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.agents.utils.rate_limiting import rate_limit
from src.domains.skills.command_tool import run_skill_command
from src.domains.skills.tool_scope import as_external, scope_refusal
from src.domains.skills.trust import (
    ACTIVATION_REQUEST_DESCRIPTION,
    is_third_party,
    reads_as_external,
)
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

if TYPE_CHECKING:
    from src.domains.skills.executor import ScriptResult

logger = get_logger(__name__)


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
# Skill proposal — a validation (staged on disk, read against the DB) and a
# Redis write; the install is the card's own route, rate limited apart. Ten a
# minute leaves room for a model correcting a refused package.
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


#: The ``type`` a third-party skill's words carry once wrapped (ADR-327).
@tool
@track_tool_metrics(
    tool_name="activate_skill",
    agent_name=AGENT_QUERY,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(max_calls=_RATE_LIMIT_IMPORT, window_seconds=_RATE_LIMIT_WINDOW, scope="user")
async def activate_skill_tool(
    name: Annotated[str, "Name of the skill to activate (from available_skills catalogue)"],
    request: Annotated[str, ACTIVATION_REQUEST_DESCRIPTION] = "",
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Load a skill's full instructions and bundled resources listing.

    Per agentskills.io standard: dedicated tool activation pattern.
    Call this when a task matches a skill's description from the catalogue.
    Returns the skill's instructions wrapped in structured tags — except for a
    skill marked third-party, which runs on its own and returns its answer.
    """
    config = validate_runtime_config(runtime, "activate_skill")
    if isinstance(config, UnifiedToolOutput):
        return config

    from src.domains.skills.activation import activate_skill
    from src.domains.skills.cache import SkillsCache

    if reads_as_external(SkillsCache.get_by_name_for_user(name, str(config.user_id))):
        return await _run_third_party_skill(name, request, runtime, str(config.user_id))
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


async def _run_third_party_skill(
    name: str,
    request: str,
    runtime: ToolRuntime[LiaRuntimeContext, Any] | None,
    user_id: str,
) -> UnifiedToolOutput:
    """A third-party skill activated from the main loop (ADR-327).

    Its instructions never reach the caller: they run in the isolated skill
    runner, and what the runner answers comes back as external content, with
    the registry items its scripts produced (an inline image at most).

    Args:
        name: The skill.
        request: What the skill should do for the person.
        runtime: The caller's tool runtime (its config is the runner's parent).
        user_id: The person.

    Returns:
        The runner's answer, or a failure the model can act on.
    """
    from langchain_core.runnables import RunnableConfig

    from src.core.context import active_skills_ctx
    from src.core.run_config import run_id_of
    from src.domains.agents.nodes.response_skill_runner import (
        run_skill_runner,
        settle_third_party_runner,
        skill_runner_task,
    )
    from src.domains.skills.activation import activate_skill

    active = active_skills_ctx.get()
    if active is not None and name not in active:
        return UnifiedToolOutput.failure(
            message=f"Skill '{name}' not found", error_code="NOT_FOUND"
        )
    if not request.strip():
        return UnifiedToolOutput.failure(
            message=(
                f"Skill '{name}' is third-party: it runs on its own. "
                "Call again with `request`, what it should do for the person."
            ),
            error_code="MISSING_REQUIRED_PARAM",
        )
    config: RunnableConfig = runtime.config if runtime is not None else RunnableConfig()
    task = skill_runner_task(
        name, activate_skill(name, user_id=user_id) or "", request, history="", agent_data=""
    )
    result = await run_skill_runner(
        name, task, config=config, location_query=request, third_party=True
    )
    answer, _, registry = settle_third_party_runner(result, run_id_of(config), name)
    if answer is None:
        return UnifiedToolOutput.failure(
            message=f"Skill '{name}' returned no answer", error_code="EMPTY_RESULT"
        )
    return UnifiedToolOutput.data_success(
        message=as_external(name, answer),
        registry_updates=registry or {},
        metadata={"skill_name": name, "activation": "isolated_runner"},
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
    if (refusal := scope_refusal(skill_name)) is not None:
        return refusal

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
    # Explicit user-provided values take precedence. Language and timezone come
    # from the typed run context (ADR-231); its own defaults are the canonical
    # ones, so the previous inline "en"/"UTC" literals are gone with the bag.
    raw_context = getattr(runtime, "context", None) if runtime else None
    context: LiaRuntimeContext | None = (
        raw_context if isinstance(raw_context, LiaRuntimeContext) else None
    )
    enriched_parameters: dict[str, Any] = dict(coerced_parameters or {})
    if "_lang" not in enriched_parameters:
        enriched_parameters["_lang"] = resolve_language(
            context.language if context is not None else None
        )
    if "_tz" not in enriched_parameters:
        enriched_parameters["_tz"] = context.timezone if context is not None else DEFAULT_TIMEZONE

    from src.domains.skills.executor import SkillScriptExecutor

    result = await SkillScriptExecutor.execute(
        skill_name=skill_name,
        script_name=script,
        parameters=enriched_parameters,
        user_id=str(config.user_id),
    )

    from src.domains.skills.cache import SkillsCache

    skill_info = SkillsCache.get_by_name_for_user(skill_name, str(config.user_id))
    if result.success:
        return _script_success_output(skill_name, script, result, skill_info)
    return _script_failure_output(skill_name, script, result, reads_as_external(skill_info))


def _script_success_output(
    skill_name: str, script: str, result: ScriptResult, skill_info: dict[str, Any] | None
) -> UnifiedToolOutput:
    """What a script that ran well hands back: its text, and its frame or image.

    Stdout follows the rich output contract (text/frame/image) and falls back to
    plain text when it is not that JSON. A skill written elsewhere — or one that
    no longer resolves — draws no frame and no remote image (ADR-327), and
    outside its isolated runner its words arrive as external content.

    Args:
        skill_name: The skill.
        script: The script run.
        result: The executor's result.
        skill_info: The resolved cache entry, or None.

    Returns:
        A ``SKILL_APP`` output for a frame or an image, a text output otherwise.
    """
    from src.domains.skills.cache import SkillsCache
    from src.domains.skills.output_builder import (
        build_skill_app_output,
        restrict_third_party_output,
    )
    from src.domains.skills.script_output import parse_skill_stdout

    parsed = parse_skill_stdout(result.output)
    if skill_info is None or is_third_party(skill_info):
        parsed = restrict_third_party_output(parsed)
    if reads_as_external(skill_info):
        parsed = parsed.model_copy(update={"text": as_external(skill_name, parsed.text)})

    if parsed.frame is not None or parsed.image is not None:
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


def _script_failure_output(
    skill_name: str, script: str, result: ScriptResult, external: bool
) -> UnifiedToolOutput:
    """A script that failed: both its stdout and stderr, so the model can read why.

    Validation results often sit in stdout while the traceback sits in stderr.

    Args:
        skill_name: The skill.
        script: The script run.
        result: The executor's result.
        external: Whether its words reach the caller as external content (ADR-327).

    Returns:
        A ``SCRIPT_ERROR`` failure.
    """
    combined = result.output or ""
    if result.error:
        combined = f"{combined}\n[stderr] {result.error}" if combined else result.error
    if combined and external:
        combined = as_external(skill_name, combined)
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
    if (refusal := scope_refusal(skill_name)) is not None:
        return refusal
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
        message=as_external(skill_name, content) if reads_as_external(skill) else content,
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
    - a **managed** skill — installed from a skill library or a plugin — is kept
      in step with its source, which the next update would overwrite: it is
      updated from the settings, never rewritten here (ADR-327);
    - a skill the user has switched off must be re-enabled first — it is absent
      from the injected catalogue, so editing it would silently modify something
      the user believes is inactive.

    Another person's skill of the same name is never reached (ADR-327: a name is
    unique per account), so for this person the name is simply free.

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
    from src.domains.skills.models import MANAGED_PROVENANCES, SkillProvenance
    from src.domains.skills.preference_service import SkillPreferenceService
    from src.domains.skills.repository import SkillRepository
    from src.infrastructure.database.session import get_db_context

    # The caller's own skill wins, exactly like the resolution the assistant sees.
    existing = SkillsCache.get_by_name_for_user(name, user_id)
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

    async with get_db_context() as db:
        owned = await SkillRepository(db).get_owned(UUID(user_id), name)
        active = await SkillPreferenceService(db).get_active_skills_for_user(UUID(user_id))
    if owned is not None and owned.provenance in MANAGED_PROVENANCES:
        source = "a skill library" if owned.provenance == SkillProvenance.LIBRARY else "a plugin"
        return None, UnifiedToolOutput.failure(
            message=(
                f"'{name}' was installed from {source} and is kept in step with it: it "
                "cannot be modified here. It is updated from Settings > LIA Skills; to "
                "change it by hand, create a skill under another name."
            ),
            error_code="SKILL_MANAGED",
        )
    if name not in active:
        return None, UnifiedToolOutput.failure(
            message=(
                f"Skill '{name}' is currently disabled. Re-enable it in "
                "Settings > LIA Skills > My Skills before modifying it."
            ),
            error_code="SKILL_DISABLED",
        )

    return existing, None


async def _precheck_import(files: dict[str, str], user_id: str) -> UnifiedToolOutput | None:
    """Run every refusal a chat package meets before it is validated, in one place.

    Args:
        files: Coerced file map of the incoming package.
        user_id: Caller's user id.

    Returns:
        A failure to return verbatim, or None when the package may be proposed.
    """
    from src.domains.skills.import_service import parse_incoming_skill_name

    incoming_name, name_error = parse_incoming_skill_name(files)
    if name_error is not None:
        return UnifiedToolOutput.failure(message=name_error, error_code="IMPORT_REJECTED")
    _existing, refusal = await _resolve_edit_target(incoming_name, user_id)
    return refusal


def _proposal_message(name: str, *, replaces: bool) -> str:
    """What the model is told once a package is proposed (technical English, ADR-256)."""
    target = (
        f"It replaces the user's existing skill '{name}'; the card lists what the "
        "replacement adds, changes and removes."
        if replaces
        else "It is a new skill."
    )
    return (
        f"Skill '{name}' is ready to install. {target} A card under your answer shows "
        "it to the user with an Install button: NOTHING is installed until they click "
        "it. Say so in one sentence, and never say the skill is installed, active, "
        "created or updated."
    )


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
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Propose a skill for the user's own skills: they install it from a card.

    Nothing is installed by this call. The package is validated exactly as an
    install would validate it, then shown to the user as a card under your
    answer with an Install button; only their click installs it (ADR-327).

    Creating: pass the full file map under a free name.

    Updating: pass the SAME name with the complete regenerated package. The
    whole package is replaced, so send every file the skill needs, not just the
    ones that changed (read the current ones first with ``read_skill_resource``,
    including ``SKILL.md``). The card states what the replacement adds, changes
    and removes; there is no version history. Bundled binary assets (the
    gallery thumbnail) are preserved automatically.

    System skills, skills installed from a library or a plugin, and skills the
    user has disabled are refused. On any validation error, the failure
    describes the problem so the caller can fix the files and retry.
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
    from src.domains.skills.proposal_service import propose
    from src.infrastructure.observability.metrics_registry import skill_proposals_total

    files_map = coerced_files or {}
    refusal = await _precheck_import(files_map, str(config.user_id))
    if refusal is not None:
        skill_proposals_total.labels(operation="propose", outcome="refused").inc()
        return refusal

    from src.domains.agents.api.run_origin import chat_cards_reach_the_person

    context = tool_runtime_context(runtime)
    conversation_id = context.conversation_id if context is not None else ""
    if not conversation_id or not chat_cards_reach_the_person():
        # A card needs an answer to sit under, drawn where the person reads
        # it: a ticket run or a channel shows none, so nobody could install it.
        return UnifiedToolOutput.failure(
            message=(
                "This run shows the user no card, so nothing was proposed. Tell the user "
                "to ask for this skill in the chat, where a card lets them install it."
            ),
            error_code="CONFIGURATION_ERROR",
        )
    try:
        proposal, _evicted = await propose(
            files_map, owner_id=UUID(str(config.user_id)), conversation_id=conversation_id
        )
    except BaseAPIException as exc:
        # Surface the validation detail so the LLM can correct and retry.
        skill_proposals_total.labels(operation="propose", outcome="refused").inc()
        return UnifiedToolOutput.failure(
            message=str(getattr(exc, "detail", exc)),
            error_code="IMPORT_REJECTED",
        )
    except Exception as exc:  # noqa: BLE001 — the cache failed: nothing was offered
        logger.warning("skill_proposal_not_kept", error_type=type(exc).__name__)
        skill_proposals_total.labels(operation="propose", outcome="unavailable").inc()
        return UnifiedToolOutput.failure(
            message="The skill could not be prepared for the user; nothing was proposed.",
            error_code="DEPENDENCY_ERROR",
        )

    skill_proposals_total.labels(operation="propose", outcome="ok").inc()
    return UnifiedToolOutput.action_success(
        message=_proposal_message(proposal.name, replaces=proposal.replaces is not None),
        metadata={
            "skill_name": proposal.name,
            "proposal_id": proposal.id,
            "replaces": proposal.replaces is not None,
            "file_count": len(proposal.sizes),
        },
    )


# Module-level list for tool_registry auto-discovery
skills_tools = [
    activate_skill_tool,
    run_skill_script,
    run_skill_command,
    read_skill_resource,
    import_user_skill,
]

#: What the response node's skill runner binds once it has activated the skill
#: itself: the activation is done in Python and its instructions travel in the
#: task, so a runner asked to activate first spent one round trip on it — and
#: sometimes never got to the script.
skills_runner_tools = [run_skill_script, run_skill_command, read_skill_resource, import_user_skill]

#: What the ISOLATED runner of a third-party skill binds (ADR-327): its own
#: skill's scripts, commands and resources, which refuse any other skill while
#: it runs. No import tool — a skill written elsewhere never writes a skill.
skills_isolated_tools = [run_skill_script, run_skill_command, read_skill_resource]
