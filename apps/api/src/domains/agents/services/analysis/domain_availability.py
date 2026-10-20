"""The menu of domains the query analyzer is allowed to choose from.

Extracted from ``query_analyzer_service`` (frozen at its audited size
by the file-size ratchet, so it may only shrink). The concern is cohesive on
its own: it answers "what can this deployment route to right now", combining
the static taxonomy with deployment flags, the turn's catalogue snapshot (a
domain it withholds entirely is not offered) and the per-request MCP
context. It is also the single list the analyzer's output is validated against,
which is what stops a disabled domain from re-entering through a hallucinated
answer or through semantic expansion.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Final

from src.core.application_tools import APPLICATION_DOMAINS, APPLICATION_TOOL_NAMES
from src.core.config import settings

if TYPE_CHECKING:
    from src.domains.agents.registry.catalogue import ToolManifest

# Domains whose availability is a DEPLOYMENT decision, mapped to the settings
# flag that decides it. Each flag already gates that domain's tools and REST
# surface elsewhere; this table is what stops the router from being offered a
# domain whose tools are unreachable — a plan over nothing, which never raises
# and simply answers badly. `peer` was missing here until 2026-07-30.
#
# A table rather than three near-identical `if` blocks: adding a gated domain
# is one line of data, and the taxonomy-coherence test reads THIS mapping
# instead of restating it.
FLAG_GATED_DOMAINS: Final[dict[str, str]] = {
    "sms": "sms_enabled",
    "setting": "application_tools_enabled",
    "telephony": "telephony_enabled",  # ADR-127
    "document": "rag_spaces_enabled",  # P1, ADR-141
    "peer": "peers_enabled",  # ADR-180
    # Declared ``feature_flag: workboard_enabled`` since ADR-276 and enforced by
    # nobody here until the test below read the table in both directions.
    "ticket": "workboard_enabled",  # ADR-276
    "journal": "journals_enabled",  # ADR-318
}


def _withdraw_disabled_domains(domains: list[dict[str, str]]) -> list[dict[str, str]]:
    """Drop every flag-gated domain whose flag is off on this deployment.

    Args:
        domains: Candidate domains, as built from the static taxonomy.

    Returns:
        The domains this deployment can actually serve.
    """
    disabled = {
        domain for domain, flag in FLAG_GATED_DOMAINS.items() if not getattr(settings, flag, False)
    }
    return [d for d in domains if d["name"] not in disabled]


def _withdraw_unoffered_domains(
    domains: list[dict[str, str]], offered: Sequence[ToolManifest]
) -> list[dict[str, str]]:
    """Drop every domain the turn's catalogue withholds entirely.

    Two kinds of domain lose ALL their tools to the turn catalogue
    (``services/turn_catalogue``) while the deployment still allows them: an
    application domain whose operations the account may not use, and a domain
    whose agents a switched-off capability withholds (``CapabilitySpec.agents``,
    e.g. journal, document, telephony). Left in the menu, the router picks a
    domain the planner then plans over nothing. Every other domain stays: a
    connector category's tools remain offered without a connector — « no provider
    is connected » is the honest answer there.

    Args:
        domains: Candidate domains, already gated by the deployment flags.
        offered: The turn's catalogue snapshot (``request_tool_manifests_ctx``).

    Returns:
        The domains the turn can serve, in their order.
    """
    from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY
    from src.domains.feature_switches.registry import PlatformCapability, disabled_agent_names

    application_agents = {m.agent for m in offered if m.name in APPLICATION_TOOL_NAMES}
    offered_agents = {m.agent for m in offered}
    # Every agent a capability switch can withhold: the agents of all of them.
    switchable_agents = disabled_agent_names(frozenset(PlatformCapability))

    def served(name: str) -> bool:
        if name in APPLICATION_DOMAINS:
            return f"{name}_agent" in application_agents
        config = DOMAIN_REGISTRY.get(name)
        agents = set(config.agent_names) if config else set()
        return not agents or not agents <= switchable_agents or bool(agents & offered_agents)

    return [item for item in domains if served(item["name"])]


def build_available_domains() -> list[dict[str, str]]:
    """Build the list of available domains for the query analyzer prompt.

    Includes routable domains enriched with semantic types, plus admin and user MCP
    per-server domains (filtered by user preferences).

    Returns:
        List of dicts with 'name' and 'description' keys.
    """
    from src.core.context import (
        admin_mcp_disabled_ctx,
        request_tool_manifests_ctx,
        user_mcp_tools_ctx,
    )
    from src.domains.agents.registry.domain_taxonomy import (
        DOMAIN_REGISTRY,
        collect_all_mcp_domains,
        get_routable_domains,
    )
    from src.infrastructure.mcp.registration import (
        get_admin_mcp_domains,
        get_admin_mcp_server_domains,
    )

    # NOTE: Semantic types (provides: ...) are omitted — they are only useful for the
    # planner's tool selection, not for the query analyzer's routing decision.
    available_domains: list[dict[str, str]] = []

    for domain_name in get_routable_domains():
        config = DOMAIN_REGISTRY.get(domain_name)
        if config:
            available_domains.append({"name": domain_name, "description": config.description})

    # Deployment-flag gating (FLAG_GATED_DOMAINS) — same runtime-filtering
    # chokepoint as MCP below.
    available_domains = _withdraw_disabled_domains(available_domains)
    offered = request_tool_manifests_ctx.get()
    if offered is not None:
        available_domains = _withdraw_unoffered_domains(available_domains, offered)

    # F2.2+F2.5: Unified MCP per-server domain injection (admin + user).
    mcp_domains = collect_all_mcp_domains(
        admin_domains=get_admin_mcp_domains(),
        admin_disabled=admin_mcp_disabled_ctx.get(),
        user_ctx=user_mcp_tools_ctx.get(),
        admin_server_domains=get_admin_mcp_server_domains(),
    )
    # The virtual base domain is not proof of a usable MCP server.
    available_domains = [d for d in available_domains if d["name"] != "mcp"]
    if offered is not None:
        offered_agents = {manifest.agent for manifest in offered}
        mcp_domains = [item for item in mcp_domains if f"{item['name']}_agent" in offered_agents]
        if not mcp_domains and "mcp_agent" in offered_agents and not admin_mcp_disabled_ctx.get():
            config = DOMAIN_REGISTRY["mcp"]
            available_domains.append({"name": "mcp", "description": config.description})
    available_domains.extend(mcp_domains)

    return available_domains
