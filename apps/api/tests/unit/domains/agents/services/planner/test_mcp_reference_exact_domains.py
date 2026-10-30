"""The planner finds a personal server's reference through its EXACT domain (M1b, E9).

The injection matched ``name.lower()`` against the domain slug minus ``mcp_``,
while the slug replaces every non-alphanumeric character and may carry a
collision suffix: « My Notion » (``mcp_my_notion``) or « GitHub-Perso » never
received their reference. The registration already wrote the exact mapping
(``ctx.server_domains``); the reference sources carry the same domain.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
import structlog

from src.domains.agents.registry.mcp_domains import deduplicate_mcp_slugs
from src.domains.agents.services.planner.mcp_reference import build_mcp_reference
from tests.helpers.mcp_reference_sources import reference_context, reference_source

pytestmark = pytest.mark.unit

NOW = datetime.now(UTC)
NAMES = ["My Notion", "GitHub-Perso", "Notes", "notes"]


async def _build(selected: list[str]) -> str:
    with patch("src.infrastructure.mcp.client_manager.get_mcp_client_manager", return_value=None):
        return await build_mcp_reference(
            selected,
            truncated_marker=lambda: "[cut]",
            render_reference=lambda name, text: f"<{name}>{text}</{name}>",
            logger=structlog.get_logger(__name__),
        )


async def test_reference_found_for_slugified_names() -> None:
    domains = deduplicate_mcp_slugs(NAMES)
    assert domains["notes"].endswith("_2")  # the collision is real, not assumed
    sources = {
        name: reference_source(domains[name], reference=f"guide:{name}", fetched_at=NOW)
        for name in NAMES
    }

    with reference_context(sources):
        built = await _build([domains["My Notion"], domains["GitHub-Perso"], domains["notes"]])

    assert "<My Notion>guide:My Notion</My Notion>" in built
    assert "<GitHub-Perso>guide:GitHub-Perso</GitHub-Perso>" in built
    assert "<notes>guide:notes</notes>" in built
    assert "guide:Notes" not in built


async def test_a_collision_never_serves_the_neighbour() -> None:
    domains = deduplicate_mcp_slugs(NAMES)
    sources = {
        name: reference_source(domains[name], reference=f"guide:{name}", fetched_at=NOW)
        for name in NAMES
    }

    with reference_context(sources):
        built = await _build([domains["Notes"]])

    assert built == "<Notes>guide:Notes</Notes>"
