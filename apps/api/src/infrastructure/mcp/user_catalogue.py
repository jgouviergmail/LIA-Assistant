"""Fresh request routing descriptions without overwriting stored operator text."""

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
    source: Literal["stored+discovered", "discovered"]


def describe_user_server(
    server_name: str,
    stored_description: str | None,
    tools: Sequence[Mapping[str, object]],
) -> UserServerCatalogue:
    """Preserve operator text and state the currently usable discovered capabilities.

    Args:
        server_name: User-facing server identity.
        stored_description: Existing description, whose provenance is not assumed.
        tools: Only declarations whose adapters and manifests were built successfully.

    Returns:
        A deterministic description and fingerprint for this request's catalogue.
    """
    names = [str(tool.get("name", "")) for tool in tools]
    descriptions = [
        value if isinstance(value := tool.get("description"), str) else None for tool in tools
    ]
    fresh = auto_generate_server_description(descriptions, server_name, tool_names=names)
    description = (
        f"{stored_description}\nCurrent discovered capabilities: {fresh}"
        if stored_description
        else fresh
    )
    return UserServerCatalogue(
        description=description,
        fingerprint=canonical_fingerprint(
            {"tools": list(tools), "stored_description": stored_description}
        ),
        source="stored+discovered" if stored_description else "discovered",
    )


def publish_user_server(
    ctx: UserMCPToolsContext,
    server_name: str,
    domain: str,
    catalogue: UserServerCatalogue,
    reference_content: str | None,
) -> None:
    """Publish a server only after its usable tools and manifests exist."""
    ctx.server_domains[server_name] = domain
    ctx.server_descriptions[server_name] = catalogue.description
    ctx.server_catalogue_fingerprints[server_name] = catalogue.fingerprint
    ctx.server_description_sources[server_name] = catalogue.source
    if reference_content:
        ctx.server_reference_content[server_name] = reference_content
