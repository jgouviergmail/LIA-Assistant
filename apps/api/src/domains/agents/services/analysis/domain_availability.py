"""The menu of domains the query analyzer is allowed to choose from.

Extracted verbatim from ``query_analyzer_service`` (frozen at its audited size
by the file-size ratchet, so it may only shrink). The concern is cohesive on
its own: it answers "what can this deployment route to right now", combining
the static taxonomy with the two deployment flags and the per-request MCP
context. It is also the single list the analyzer's output is validated against,
which is what stops a disabled domain from re-entering through a hallucinated
answer or through semantic expansion.
"""

from __future__ import annotations

from typing import Final

from src.core.config import settings

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
    "telephony": "telephony_enabled",  # ADR-127
    "document": "rag_spaces_enabled",  # P1, ADR-141
    "peer": "peers_enabled",  # ADR-180
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


def build_available_domains() -> list[dict[str, str]]:
    """Build the list of available domains for the query analyzer prompt.

    Includes routable domains enriched with semantic types, plus admin and user MCP
    per-server domains (filtered by user preferences).

    Returns:
        List of dicts with 'name' and 'description' keys.
    """
    from src.core.context import admin_mcp_disabled_ctx, user_mcp_tools_ctx
    from src.domains.agents.registry.domain_taxonomy import (
        DOMAIN_REGISTRY,
        collect_all_mcp_domains,
        get_routable_domains,
    )
    from src.infrastructure.mcp.registration import get_admin_mcp_domains

    # NOTE: Semantic types (provides: ...) are omitted — they are only useful for the
    # planner's tool selection, not for the query analyzer's routing decision.
    available_domains: list[dict[str, str]] = []

    for domain_name in get_routable_domains():
        config = DOMAIN_REGISTRY.get(domain_name)
        if config:
            available_domains.append({"name": domain_name, "description": config.description})

    # Deployment-flag gating (telephony, documents, peers) — same
    # runtime-filtering chokepoint as MCP below.
    available_domains = _withdraw_disabled_domains(available_domains)

    # F2.2+F2.5: Unified MCP per-server domain injection (admin + user).
    mcp_domains = collect_all_mcp_domains(
        admin_domains=get_admin_mcp_domains(),
        admin_disabled=admin_mcp_disabled_ctx.get(),
        user_ctx=user_mcp_tools_ctx.get(),
    )
    if mcp_domains:
        available_domains = [d for d in available_domains if d["name"] != "mcp"]
        available_domains.extend(mcp_domains)

    return available_domains
