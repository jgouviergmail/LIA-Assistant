"""``run_skill_command`` — a skill runs its own commands (ADR-327 lots 2 and 3).

A skill written for another agent tells it to RUN things: ``python
scripts/fill.py form.pdf``, ``node build.js``, ``bash scripts/convert.sh``. This
tool runs one such command with bash in a COPY of the skill's folder, inside
the SEC-001 throwaway container — read-only root, uid 65534 — with the files
the person attached to this turn in ``../input/``. What the command writes
under ``out/`` becomes the person's generated files, shown under the answer by
the chat's own cards. It runs offline, unless it declares ``hosts``: then it
reaches exactly the permitted ones through the egress proxy
(``command_network``, lot 3).

It serves the skill runner alone. Its gates are the scripts' own
(``skills_scripts_enabled``), plus one: a command is refused outside the
container sandbox, since the legacy in-process mode only isolates when the API
runs as root — the rule ``execute_source`` applies to model-written code.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool

from src.core.config import settings
from src.core.constants import (
    SKILL_COMMAND_KILL_AFTER_SECONDS,
    SKILL_COMMAND_MAX_CHARS,
)
from src.core.context import SkillTurnFile, skill_turn_files
from src.domains.agents.constants import AGENT_QUERY
from src.domains.agents.context.runtime_context import LiaRuntimeContext, tool_runtime_context
from src.domains.agents.python_sandbox.egress.grants import mark_relied_grants
from src.domains.agents.python_sandbox.egress.proxy_client import EgressProxyUnavailable
from src.domains.agents.python_sandbox.egress.tool_path import (
    OUTCOME_ALLOWED,
    OUTCOME_PROXY_UNAVAILABLE,
    OUTCOME_REFUSED,
    NetworkRefusal,
)
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.agents.utils.rate_limiting import rate_limit
from src.domains.skills.command_bundle import (
    COMMAND_DESCRIPTION,
    INPUT_DIR,
    BundleTooLarge,
    CommandOutput,
    InputFile,
    UnreadableOutput,
    pack_bundle,
    safe_file_name,
)
from src.domains.skills.command_network import (
    HOSTS_DESCRIPTION,
    CommandNetwork,
    network_lines,
    plan_command_network,
    run_on_network,
)
from src.domains.skills.command_outputs import Delivery, deliver_outputs
from src.domains.skills.command_sandbox import SandboxTimeout, SandboxUnavailable, run_command
from src.domains.skills.executor import EgressSpec
from src.domains.skills.tool_scope import as_external, scope_refusal
from src.domains.skills.trust import is_third_party, reads_as_external
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)
from src.infrastructure.observability.metrics_registry import (
    skill_command_egress_total,
    skill_commands_total,
)

__all__ = ["run_skill_command"]

logger = get_logger(__name__)

#: ``timeout`` answers 124 when it stopped the command, 137 when it had to kill it.
_TIMED_OUT = frozenset({124, 137})

#: Why a turn file stayed out of the sandbox.
_INPUT_TOO_LARGE = "too_large"
_INPUT_UNAVAILABLE = "unavailable"


def _inputs(files: tuple[SkillTurnFile, ...]) -> tuple[list[InputFile], list[tuple[str, str]]]:
    """The turn's files the sandbox may receive, named; and the others, with a reason.

    Blocking (it reads the disk): runs in the bundle's thread. The size carried
    is the one on disk, never the recorded one — the tar says what it holds.
    """
    root = Path(settings.attachments_storage_path).resolve()
    ceiling = settings.skill_command_max_file_mb * 1024 * 1024
    taken: set[str] = set()
    kept: list[InputFile] = []
    left: list[tuple[str, str]] = []
    for item in files:
        name = safe_file_name(item.filename, taken)
        path = (root / item.file_path).resolve()
        size = path.stat().st_size if path.is_relative_to(root) and path.is_file() else None
        if size is None:
            left.append((name, _INPUT_UNAVAILABLE))
        elif size > ceiling:
            left.append((name, _INPUT_TOO_LARGE))
        else:
            kept.append(InputFile(name=name, path=path, size=size))
    return kept, left


def _prepare(
    skill_dir: Path, files: tuple[SkillTurnFile, ...], ceiling: int
) -> tuple[bytes, list[InputFile], list[tuple[str, str]]]:
    """The bundle, the files it carries and the ones it leaves out. Blocking."""
    inputs, left = _inputs(files)
    return pack_bundle(skill_dir, inputs, max_bytes=ceiling), inputs, left


def _gate_refusal(skill_name: str, command: str) -> UnifiedToolOutput | None:
    """Every refusal that needs neither the skill nor the sandbox."""
    if not command:
        return UnifiedToolOutput.failure(
            message="A command is required", error_code="MISSING_REQUIRED_PARAM"
        )
    if len(command) > SKILL_COMMAND_MAX_CHARS:
        return UnifiedToolOutput.failure(
            message=f"The command exceeds {SKILL_COMMAND_MAX_CHARS} characters",
            error_code="INVALID_INPUT",
        )
    if (refusal := scope_refusal(skill_name)) is not None:
        return refusal
    if not settings.skills_scripts_enabled:
        return UnifiedToolOutput.failure(
            message="Skill scripts are disabled", error_code="FEATURE_DISABLED"
        )
    if str(settings.skills_script_sandbox).lower() != "container":
        return UnifiedToolOutput.failure(
            message="Skill commands require the container sandbox",
            error_code="FEATURE_DISABLED",
        )
    return None


def _listing(pairs: list[tuple[str, str]] | tuple[tuple[str, str], ...]) -> str:
    return ", ".join(f"{name} ({reason.replace('_', ' ')})" for name, reason in pairs)


def _report(
    output: CommandOutput,
    delivery: Delivery,
    inputs: list[InputFile],
    left: list[tuple[str, str]],
    network: CommandNetwork | None,
) -> str:
    """What the model reads: the exit status, both streams, the files each way, the network."""
    lines = [f"Exit code: {output.exit_code if output.exit_code is not None else 'unknown'}"]
    if network is not None:
        lines += network_lines(network)
    if output.exit_code in _TIMED_OUT:
        lines.append(
            f"The command was stopped at its {settings.skill_command_timeout_seconds} s budget."
        )
    for label, text, cut in (
        ("Standard output", output.stdout, output.stdout_truncated),
        ("Standard error", output.stderr, output.stderr_truncated),
    ):
        if text:
            lines += [f"{label}:", text.rstrip("\n")]
            if cut:
                lines.append(f"[{label.lower()} cut at {settings.skill_command_max_text_kb} KB]")
    if delivery.delivered:
        named = ", ".join(f"{item.name} ({item.size} bytes)" for item in delivery.delivered)
        lines.append(
            f"Files handed to the user, shown as cards under the answer — do not link or "
            f"repeat them: {named}"
        )
    skipped = [*output.skipped, *delivery.skipped]
    if skipped:
        lines.append(f"Files written under out/ but not handed back: {_listing(skipped)}")
    if output.incomplete:
        lines.append("The run wrote more than LIA reads back: what followed was not read.")
    if inputs:
        lines.append("Input files: " + ", ".join(f"{INPUT_DIR}/{item.name}" for item in inputs))
    if left:
        lines.append(f"Attached files not sent to the command: {_listing(left)}")
    return "\n".join(lines)


def _outcome(output: CommandOutput) -> str:
    if output.exit_code == 0:
        return "succeeded"
    return "timed_out" if output.exit_code in _TIMED_OUT else "failed"


def _answer(
    skill_name: str, output: CommandOutput, report: str, external: bool, delivery: Delivery
) -> UnifiedToolOutput:
    message = as_external(skill_name, report) if external else report
    outcome = _outcome(output)
    skill_commands_total.labels(outcome=outcome).inc()
    structured = {
        "exit_code": output.exit_code,
        "files": [item.name for item in delivery.delivered],
    }
    if outcome == "succeeded":
        return UnifiedToolOutput.action_success(
            message=message,
            structured_data=structured,
            metadata={"skill_name": skill_name},
        )
    return UnifiedToolOutput.failure(
        message=message,
        error_code="TIMEOUT" if outcome == "timed_out" else "SCRIPT_ERROR",
        metadata={"skill_name": skill_name, **structured},
    )


def _produced[T](refusal: UnifiedToolOutput | None, value: T | None) -> T | UnifiedToolOutput:
    """What a stage produced, or the answer the command ends on.

    A stage that answered a refusal (a question, a gate, a failure it
    named) started nothing after it; one that answered neither a refusal
    nor a value produced nothing, which is a failure said as such.

    Args:
        refusal: The output the stage answered instead of producing, if any.
        value: What the stage produced, if anything.

    Returns:
        The value, or the output ``run_skill_command`` returns.
    """
    if refusal is not None:
        return refusal
    if value is None:
        return UnifiedToolOutput.failure(
            message="The command produced nothing", error_code="EMPTY_RESULT"
        )
    return value


async def _bundle(
    skill_name: str, skill_dir: Path, share_turn_files: bool
) -> tuple[bytes | None, list[InputFile], list[tuple[str, str]], UnifiedToolOutput | None]:
    """The skill and, when they may travel, the turn's files — or a refusal."""
    ceiling = settings.skill_command_max_input_mb * 1024 * 1024
    files = skill_turn_files() if share_turn_files else ()
    try:
        bundle, inputs, left = await asyncio.to_thread(_prepare, skill_dir, files, ceiling)
    except BundleTooLarge:
        skill_commands_total.labels(outcome="refused").inc()
        refusal = UnifiedToolOutput.failure(
            message=(
                f"The skill and the attached files exceed "
                f"{settings.skill_command_max_input_mb} MB"
            ),
            error_code="CONSTRAINT_VIOLATION",
        )
        return None, [], [], refusal
    except OSError as exc:
        # A file changed or went between its check and its read.
        logger.warning(
            "skill_command_bundle_unreadable", skill_name=skill_name, error_type=type(exc).__name__
        )
        skill_commands_total.labels(outcome="unavailable").inc()
        refusal = UnifiedToolOutput.failure(
            message="The skill's files or the attached files could not be read",
            error_code="DEPENDENCY_ERROR",
        )
        return None, [], [], refusal
    return bundle, inputs, left, None


async def _execute(
    skill_name: str, command: str, bundle: bytes, user_id: str, network: CommandNetwork | None
) -> tuple[CommandOutput | None, UnifiedToolOutput | None]:
    """Run the command, offline or on its network — or say why it did not run."""

    async def run(egress: EgressSpec | None) -> CommandOutput:
        return await run_command(
            skill_name=skill_name,
            command=command,
            bundle=bundle,
            settings=settings,
            user_id=user_id,
            egress=egress,
        )

    try:
        output = await run(None) if network is None else await run_on_network(network, run)
    except EgressProxyUnavailable as exc:
        logger.warning("skill_command_egress_unavailable", skill_name=skill_name, reason=str(exc))
        skill_command_egress_total.labels(outcome=OUTCOME_PROXY_UNAVAILABLE).inc()
        return None, UnifiedToolOutput.failure(
            message="The network proxy is unavailable: the command did not run.",
            error_code="CONFIGURATION_ERROR",
        )
    except SandboxTimeout:
        skill_commands_total.labels(outcome="timed_out").inc()
        budget = settings.skill_command_timeout_seconds + SKILL_COMMAND_KILL_AFTER_SECONDS
        return None, UnifiedToolOutput.failure(
            message=f"The command did not finish within {budget} s", error_code="TIMEOUT"
        )
    except SandboxUnavailable:
        skill_commands_total.labels(outcome="unavailable").inc()
        return None, UnifiedToolOutput.failure(
            message="The command sandbox is unavailable", error_code="DEPENDENCY_ERROR"
        )
    except UnreadableOutput:
        # The run wrote something that is not the bootstrap's archive: the
        # command's doing (it may write where the bootstrap does), not ours.
        logger.warning("skill_command_output_unreadable", skill_name=skill_name)
        skill_commands_total.labels(outcome="failed").inc()
        return None, UnifiedToolOutput.failure(
            message="The command ran, but its output could not be read", error_code="SCRIPT_ERROR"
        )
    if network is not None:
        skill_command_egress_total.labels(outcome=OUTCOME_ALLOWED).inc()
        await mark_relied_grants(UUID(user_id), network.plan.statuses)
    return output, None


async def _network(
    hosts: list[str] | None,
    *,
    skill_name: str,
    command: str,
    entry: dict[str, Any],
    runtime: Any,
) -> tuple[CommandNetwork | None, UnifiedToolOutput | None]:
    """The command's network run, when it declared hosts — or the refusal or question."""
    if not hosts:
        return None, None
    context = tool_runtime_context(runtime)
    if context is None:
        skill_command_egress_total.labels(outcome=OUTCOME_REFUSED).inc()
        return None, UnifiedToolOutput.failure(
            message="A network run needs the conversation's context: declare no hosts.",
            error_code="CONFIGURATION_ERROR",
        )
    decided = await plan_command_network(
        hosts,
        skill_name=skill_name,
        command=command,
        context=context,
        third_party=is_third_party(entry),
        turn_files=len(skill_turn_files()),
    )
    if isinstance(decided, NetworkRefusal):
        skill_command_egress_total.labels(outcome=decided.outcome).inc()
        return None, decided.output
    return decided, None


@tool
@track_tool_metrics(
    tool_name="run_skill_command",
    agent_name=AGENT_QUERY,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: settings.skill_command_rate_limit_calls,
    window_seconds=lambda: settings.skill_command_rate_limit_window_seconds,
    scope="user",
)
async def run_skill_command(
    skill_name: Annotated[str, "Name of the skill whose folder the command runs in"],
    command: Annotated[str, COMMAND_DESCRIPTION],
    hosts: Annotated[list[str] | None, HOSTS_DESCRIPTION] = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Run one of a skill's shell commands in a copy of its folder.

    Offline, unless ``hosts`` names the hosts it reaches. Files the command
    writes under out/ are handed to the user.
    """
    command = command.strip()
    if (refusal := _gate_refusal(skill_name, command)) is not None:
        return refusal
    config = validate_runtime_config(runtime, "run_skill_command")
    if isinstance(config, UnifiedToolOutput):
        return config

    from src.domains.skills.cache import SkillsCache

    user_id = str(config.user_id)
    entry = SkillsCache.get_by_name_for_user(skill_name, user_id)
    if entry is None:
        return UnifiedToolOutput.failure(
            message=f"Skill '{skill_name}' not found", error_code="NOT_FOUND"
        )
    network, refusal = await _network(
        hosts, skill_name=skill_name, command=command, entry=entry, runtime=runtime
    )
    if refusal is not None:
        # A question or a refusal started no container.
        return refusal
    share = network is None or network.share_turn_files
    staged, inputs, left, refusal = await _bundle(
        skill_name, Path(entry["source_path"]).parent, share
    )
    bundle = _produced(refusal, staged)
    if isinstance(bundle, UnifiedToolOutput):
        return bundle
    ran, refusal = await _execute(skill_name, command, bundle, user_id, network)
    output = _produced(refusal, ran)
    if isinstance(output, UnifiedToolOutput):
        return output
    context = tool_runtime_context(runtime)
    delivery = await deliver_outputs(
        output.files,
        user_id=UUID(config.user_id),
        conversation_id=context.conversation_id if context is not None else "",
    )
    logger.info(
        "skill_command_ran",
        skill_name=skill_name,
        user_id=user_id,
        exit_code=output.exit_code,
        command_length=len(command),
        delivered=len(delivery.delivered),
        skipped=len(output.skipped) + len(delivery.skipped),
        hosts=len(network.plan.run.hosts) if network is not None else 0,
    )
    report = _report(output, delivery, inputs, left, network)
    return _answer(skill_name, output, report, reads_as_external(entry), delivery)
