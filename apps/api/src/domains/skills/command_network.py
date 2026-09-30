"""A skill's command on the network (ADR-327 lot 3, through ADR-298's proxy).

41 % of the surveyed skills make the agent RUN something, and a third install
a package or call a service first. A command that declares ``hosts`` runs on
the sandbox network instead of none: HTTPS only, through the egress proxy,
to exactly the hosts that are permitted — by the operator's list, the
person's own grants, and, for the person's own skills alone, their connectors.
The rule is the Python sandbox's own (``egress.tool_path``): one question for
an unknown host, asked where the ReAct loop can settle it and refused
elsewhere with where the person allows it; one register row per network act;
one scope for the turn's data — allowed « without the turn's data », the
files the person attached never enter the container.

A skill written elsewhere (ADR-327) never reaches the person's connectors: no
token is minted for it, and a connector's host is reachable only as the
operator's or the person's grant.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Final

import structlog

from src.core.config import settings
from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.core.text_clip import clip_on_word
from src.domains.agents.effects.in_turn_effects import SKILL_COMMAND_NETWORK_CAPABILITY
from src.domains.agents.python_sandbox.egress.offer import ReachableHost, offer_for_account
from src.domains.agents.python_sandbox.egress.run import NetworkRunPlan, serving
from src.domains.agents.python_sandbox.egress.tool_path import (
    NetworkRefusal,
    authorize_network,
)
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.skills.command_bundle import HOSTS_DESCRIPTION, CommandOutput

logger = structlog.get_logger(__name__)

#: The tool's registered name, named on the egress card.
COMMAND_TOOL_NAME: Final = "run_skill_command"

#: How much of the command the card shows as the run's purpose.
_PURPOSE_MAX_CHARS: Final = 300


@dataclass(frozen=True)
class CommandNetwork:
    """A command's permitted network run.

    Attributes:
        plan: What the proxy serves and the sandbox is handed.
    """

    plan: NetworkRunPlan

    @property
    def share_turn_files(self) -> bool:
        """Whether the files the person attached may enter the container."""
        return self.plan.share_turn_data


def _purpose(skill_name: str, command: str) -> str:
    """What the card says the run is for: the skill and the command it runs."""
    return clip_on_word(f"{skill_name}: {command}", _PURPOSE_MAX_CHARS)


async def plan_command_network(
    hosts: list[str],
    *,
    skill_name: str,
    command: str,
    context: Any,
    third_party: bool,
    turn_files: int,
) -> CommandNetwork | NetworkRefusal:
    """Decide whether a command may run on the network, and with what.

    Args:
        hosts: What the model declared.
        skill_name: The skill whose command runs.
        command: The command — shown on the card as the purpose.
        context: The typed runtime context.
        third_party: Whether the skill was written elsewhere (no connectors).
        turn_files: How many files the person attached — counted on the card.

    Returns:
        The permitted run, or the refusal (or question) the tool returns.
    """
    if not settings.skill_command_network_enabled:
        return NetworkRefusal(
            UnifiedToolOutput(
                success=False,
                message="Skill commands run offline on this instance: declare no hosts.",
                error_code=ToolErrorCode.CONFIGURATION_ERROR,
            ),
            "refused",
        )
    decided = await authorize_network(
        hosts,
        context=context,
        purpose=_purpose(skill_name, command),
        items={f"input_{index}": {"type": "FILE"} for index in range(turn_files)},
        tool_name=COMMAND_TOOL_NAME,
        third_party_skill=third_party,
    )
    return decided if isinstance(decided, NetworkRefusal) else CommandNetwork(decided)


async def run_on_network(network: CommandNetwork, run: Any) -> CommandOutput:
    """Claim the act, publish the run, run the command, close the act.

    Args:
        network: The permitted run.
        run: A coroutine factory running the command with the run's egress —
            called once, while the proxy serves the run.

    Returns:
        The command's output.

    Raises:
        EgressProxyUnavailable: The proxy could not serve the run; nothing ran.
    """
    async with serving(network.plan, capability=SKILL_COMMAND_NETWORK_CAPABILITY) as effect:
        output: CommandOutput = await run(network.plan.spec)
        effect.succeeded = output.exit_code == 0
    return output


async def network_available() -> bool:
    """Whether a command may reach the network at all this turn — read at the act.

    The skills' own switch, the scripts' and the container sandbox's (a
    command runs nowhere else), and the sandbox's egress capability (ADR-280:
    flipping it takes effect without a restart). A capability that cannot be
    read is off: the prompt then promises nothing the run would refuse.
    """
    if not (
        settings.skill_command_network_enabled
        and settings.skills_scripts_enabled
        and str(settings.skills_script_sandbox).lower() == "container"
    ):
        return False
    from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled

    try:
        return await is_capability_enabled(PlatformCapability.PYTHON_SANDBOX_EGRESS)
    except Exception as exc:  # noqa: BLE001 — a blind switch reads as off
        logger.warning("skill_command_network_switch_unreadable", error_type=type(exc).__name__)
        return False


@lru_cache(maxsize=1)
def _lines() -> dict[str, str]:
    return dict(parse_prompt_sections(read_prompt_file("skill_command_network_lines"), 2))


def _render_host(host: ReachableHost, lines: dict[str, str]) -> str:
    """One reachable host — with the token a command reads when the person's key travels."""
    credential = host.credential
    if credential is None:
        return lines["host_plain"].format(host=host.host)
    if credential.auth_method == "header":
        prefix = f"{credential.auth_prefix} " if credential.auth_prefix else ""
        carrier = lines["carrier_header"].format(name=credential.auth_name, prefix=prefix)
    else:
        carrier = lines["carrier_query"].format(name=credential.auth_name)
    return lines["host_with_key"].format(host=host.host, env=host.token_env, carrier=carrier)


async def runner_network_line(*, third_party: bool, context: Any) -> str:
    """The skill runner's network line: offline, or what a command reaches without asking.

    Args:
        third_party: Whether the runner runs a skill written elsewhere — its
            commands never reach the person's connectors, so none is offered.
        context: The run's typed context (the account and its connectors), or None.

    Returns:
        One line of the runner's prompt.
    """
    lines = _lines()
    if context is None or not await network_available():
        return lines["offline"]
    gate = None
    if not third_party:
        try:
            gate = await context.deps.get_connector_service()
        except Exception as exc:  # noqa: BLE001 — the operator's hosts are still offered
            logger.warning("skill_command_network_gate_unavailable", error_type=type(exc).__name__)
    offer = await offer_for_account(context.user_id, gate)
    hosts = ", ".join(_render_host(h, lines) for h in offer.hosts) or lines["no_hosts"]
    # What becomes of a host nobody permitted: the instance's own rule (ADR-184),
    # never a door that is shut on it.
    unknown = lines["unknown_settings" if offer.ask_enabled else "unknown_refused"]
    return lines["online"].format(
        max_hosts=settings.python_sandbox_max_hosts_per_run, hosts=hosts, unknown=unknown
    )


def network_lines(network: CommandNetwork) -> list[str]:
    """What the model reads of the network the command had."""
    hosts = ", ".join(network.plan.run.hosts)
    lines = [f"Network: HTTPS through the proxy to {hosts} only."]
    if not network.share_turn_files:
        lines.append(
            "The person allowed these hosts WITHOUT the turn's data: the attached files "
            "were not sent to the command."
        )
    return lines


__all__ = [
    "COMMAND_TOOL_NAME",
    "HOSTS_DESCRIPTION",
    "CommandNetwork",
    "network_available",
    "network_lines",
    "plan_command_network",
    "run_on_network",
    "runner_network_line",
]
