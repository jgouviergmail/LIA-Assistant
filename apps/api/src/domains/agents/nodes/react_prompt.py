"""The ReAct system prompt — assembled from what the turn can actually run.

Extracted from ``react_nodes`` (file-size ratchet): the functions that turn
the versioned ``react_agent_prompt`` into the turn's system message. The
prompt promises only the tools the turn carries — the ``<Computation>`` block
is rendered iff ``run_python_tool`` is bound AND the capability is switched on
(ADR-284, prompt audit 2026-09-12: the public demonstrator read a promise of a
tool it never registered), and its network section only under an OFFER
(ADR-298): the egress capability on, and the hosts read from what the account
holds at the start of the turn.
"""

import re
from collections.abc import Sequence

import structlog

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE, PYTHON_SANDBOX_TOOL_NAME
from src.core.i18n import get_language_name
from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.core.time_utils import get_prompt_datetime_formatted
from src.domains.agents.analysis.query_intelligence_helpers import get_qi_attr
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.models import MessagesState
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.python_sandbox.egress.offer import (
    NetworkOffer,
    ReachableHost,
    offer_for_account,
)
from src.domains.agents.python_sandbox.libraries import render_libraries
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled

logger = structlog.get_logger(__name__)

__all__ = ["build_system_prompt", "network_available", "sandbox_available"]


async def sandbox_available(tool_names: Sequence[str]) -> bool:
    """Can this turn actually run ``run_python_tool``?

    Bound for the turn AND switched on right now: the sandbox is a switchable
    capability (off on the public demonstrator, and an operator may flip it
    without a restart), and the tool refuses at call time when it is off. A
    prompt that promises it anyway makes the model announce a script it
    cannot run (prompt audit 2026-09-12, A.5).

    Args:
        tool_names: Names of the tools bound for this turn.

    Returns:
        True only when the tool is bound and the capability is enabled.
    """
    if PYTHON_SANDBOX_TOOL_NAME not in tool_names:
        return False
    return await is_capability_enabled(PlatformCapability.PYTHON_SANDBOX)


async def network_available(tool_names: Sequence[str]) -> NetworkOffer | None:
    """What this turn may promise about the network — or nothing.

    Mirrors :func:`sandbox_available`: the tool must be bound and the egress
    capability switched on, and the hosts are read from the ACCOUNT running
    the turn (its active connectors, the operator's list). Outside a graph
    run there is no account, so nothing is promised.

    Args:
        tool_names: Names of the tools bound for this turn.

    Returns:
        The offer, or ``None`` when no network section may be rendered.
    """
    if PYTHON_SANDBOX_TOOL_NAME not in tool_names:
        return None
    if not await is_capability_enabled(PlatformCapability.PYTHON_SANDBOX_EGRESS):
        return None
    context = runtime_context_if_running()
    user_id = getattr(context, "user_id", None)
    deps = getattr(context, "deps", None)
    if context is None or user_id is None:
        return None
    gate = None
    if deps is not None:
        try:
            gate = await deps.get_connector_service()
        except Exception as exc:  # noqa: BLE001 — best-effort context block
            logger.warning(
                "sandbox_egress_offer_gate_unavailable",
                user_id=str(user_id),
                error=type(exc).__name__,
            )
    return await offer_for_account(user_id, gate)


def _lines() -> dict[str, str]:
    return dict(parse_prompt_sections(read_prompt_file("react_computation_lines"), 2))


def _render_host(host: ReachableHost, lines: dict[str, str]) -> str:
    """One host line — with its carrier when the person's key travels."""
    credential = host.credential
    if credential is None:
        return lines["host_plain"].format(host=host.host)
    if credential.auth_method == "header":
        prefix = f"{credential.auth_prefix} " if credential.auth_prefix else ""
        carrier = lines["carrier_header"].format(name=credential.auth_name, prefix=prefix)
    else:
        carrier = lines["carrier_query"].format(name=credential.auth_name)
    return lines["host_with_key"].format(host=host.host, env=host.token_env, carrier=carrier)


def _render_network_block(offer: NetworkOffer) -> str:
    """The network section of ``<Computation>``, with the bounds the run enforces."""
    lines = _lines()
    hosts = "\n".join(_render_host(h, lines) for h in offer.hosts) or lines["no_hosts"]
    rule = lines["unknown_ask"] if offer.ask_enabled else lines["unknown_refuse"]
    return load_prompt("react_computation_network_prompt").format(
        reachable_hosts=hosts,
        unknown_host_rule=rule,
        max_hosts=settings.python_sandbox_max_hosts_per_run,
        max_body_kb=settings.python_sandbox_egress_max_body_bytes // 1024,
        network_timeout_seconds=settings.python_sandbox_network_timeout_seconds,
    )


def _render_computation_block(computation: bool, network: NetworkOffer | None) -> str:
    """The ephemeral-Python section, with every bound the code enforces.

    Args:
        computation: Whether the turn can run the sandbox (see ``sandbox_available``).
        network: What the turn may promise about the network (see
            ``network_available``) — the section is absent without an offer.

    Returns:
        The rendered ``<Computation>`` block, or an empty string.
    """
    if not computation:
        return ""
    return load_prompt("react_computation_prompt").format(
        python_sandbox_max_runs_per_turn=settings.python_sandbox_max_runs_per_turn,
        script_timeout_seconds=settings.skills_script_timeout_seconds,
        script_memory_mb=settings.skills_script_max_memory_mb,
        script_stdout_kb=settings.skills_script_max_output_kb,
        libraries=render_libraries(),
        network_block=_render_network_block(network).strip() if network is not None else "",
    )


def build_system_prompt(
    state: MessagesState, *, computation: bool = False, network: NetworkOffer | None = None
) -> str:
    """Build the ReAct agent system prompt with context variables.

    Args:
        state: Current graph state.
        computation: Whether the turn can run the Python sandbox — the prompt
            promises the tool only then.
        network: What the turn may promise about the network; ignored without
            ``computation``, absent from the prompt when ``None``.

    Returns:
        Formatted system prompt string.
    """
    personality = state.get("personality_instruction") or "a helpful, friendly assistant"
    user_tz = state.get("user_timezone", DEFAULT_USER_DISPLAY_TIMEZONE)
    user_lang = state.get("user_language", "fr")

    # Cross-domain type links (same section the pipeline planner receives,
    # ontology ∪ live manifests). Without it, the ReAct LLM has no signal
    # that e.g. a route destination should come from a contact's exact
    # address rather than an approximate memory value.
    from src.domains.agents.semantic.expansion_service import (
        generate_semantic_dependencies_for_prompt,
    )

    domains = get_qi_attr(state, "domains", default=[]) or []
    semantic_deps = generate_semantic_dependencies_for_prompt(
        domains, include_jinja2_patterns=False
    )

    template = load_prompt("react_agent_prompt")
    prompt = template.format(
        personnalite=personality,
        current_datetime=get_prompt_datetime_formatted(),
        user_timezone=user_tz,
        # Human-readable name ("French") — clearer language directive for the
        # LLM than a raw code ("fr"); same convention as get_response_prompt.
        user_language=get_language_name(user_lang),
        semantic_dependencies=semantic_deps,
        computation_block=_render_computation_block(computation, network),
    )
    # An absent block leaves its two blank lines behind; the model reads one.
    return re.sub(r"(\r?\n){3,}", r"\1\1", prompt)
