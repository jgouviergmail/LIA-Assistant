"""Request routing descriptions without overwriting stored operator text.

The capabilities a description states come from the server's declarations —
discovered over the network this turn, or read from the persisted snapshot
(spec 2026-10-21 §5.2, ADR-338 amendment for personal servers' turn
preparation only). One wording, « Declared capabilities: », is true for both;
the provenance says which, for the debug panel and the register.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from src.core.context import UserMCPToolsContext
from src.domains.agents.registry.domain_taxonomy import auto_generate_server_description
from src.infrastructure.mcp.catalogue_fingerprint import canonical_fingerprint


@dataclass(frozen=True)
class UserServerCatalogue:
    description: str
    fingerprint: str
    source: Literal["stored+discovered", "discovered", "stored+snapshot", "snapshot"]


def describe_user_server(
    server_name: str,
    stored_description: str | None,
    tools: Sequence[Mapping[str, object]],
    *,
    from_snapshot: bool = False,
) -> UserServerCatalogue:
    """Preserve operator text and state the server's currently usable declared capabilities.

    Args:
        server_name: User-facing server identity.
        stored_description: Existing description, whose provenance is not assumed.
        tools: Only declarations whose adapters and manifests were built successfully.
        from_snapshot: The declarations come from the persisted snapshot, not the network.

    Returns:
        A deterministic description and fingerprint for this request's catalogue.
    """
    names = [str(tool.get("name", "")) for tool in tools]
    descriptions = [
        value if isinstance(value := tool.get("description"), str) else None for tool in tools
    ]
    fresh = auto_generate_server_description(descriptions, server_name, tool_names=names)
    description = (
        f"{stored_description}\nDeclared capabilities: {fresh}" if stored_description else fresh
    )
    return UserServerCatalogue(
        description=description,
        fingerprint=canonical_fingerprint(
            {"tools": list(tools), "stored_description": stored_description}
        ),
        source=_source(stored=bool(stored_description), from_snapshot=from_snapshot),
    )


def _source(
    *, stored: bool, from_snapshot: bool
) -> Literal["stored+discovered", "discovered", "stored+snapshot", "snapshot"]:
    if from_snapshot:
        return "stored+snapshot" if stored else "snapshot"
    return "stored+discovered" if stored else "discovered"


def publish_user_server(
    ctx: UserMCPToolsContext,
    server_name: str,
    domain: str,
    catalogue: UserServerCatalogue,
) -> None:
    """Publish a server only after its usable tools and manifests exist."""
    ctx.server_domains[server_name] = domain
    ctx.server_descriptions[server_name] = catalogue.description
    ctx.server_catalogue_fingerprints[server_name] = catalogue.fingerprint
    ctx.server_description_sources[server_name] = catalogue.source
