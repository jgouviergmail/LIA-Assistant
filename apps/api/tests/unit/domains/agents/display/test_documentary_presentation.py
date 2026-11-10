"""Illustrative surfaces preserve unknown state and visible presentation limits."""

import pytest
from bs4 import BeautifulSoup

from src.core.i18n_cards import card_label
from src.domains.agents.data_registry.mcp_metadata import mcp_source_display
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.mcp_details import MAX_MCP_DISPLAY_CHARS
from src.domains.agents.display.components.mcp_result_card import McpResultCard
from src.domains.agents.display.components.snapshot_cards import HueLightCard

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("state", "expected"),
    [(True, "on"), (False, "off"), (None, "unknown"), ("false", "unknown"), (0, "unknown")],
)
def test_lamp_illustration_never_turns_missing_or_malformed_state_into_off(
    state: object, expected: str
) -> None:
    """The silhouette is decorative; the original meter remains the readable fact."""
    soup = BeautifulSoup(
        HueLightCard().render(
            {"name": "Desk lamp", "is_on": state, "brightness": 0},
            RenderContext(language="en"),
        ),
        "html.parser",
    )
    scene = soup.select_one(".lia-hues__scene")
    assert scene is not None
    assert f"lia-hues__scene--{expected}" in scene.get("class", [])
    assert scene.get("aria-hidden") == "true"
    assert not soup.select("button, input, select")
    meter = soup.find("meter")
    assert meter is not None and meter.get("value") == "0"
    assert meter.get("aria-label") == card_label("brightness", "en")
    if expected == "unknown":
        assert card_label("light_off", "en") not in soup.get_text()
        assert card_label("light_on", "en") not in soup.get_text()


@pytest.mark.parametrize("structured", [True, False])
def test_mcp_display_limit_is_visible_before_opening_the_received_result(structured: bool) -> None:
    """A folded receipt cannot conceal that its displayed data was bounded."""
    content = "x" * (MAX_MCP_DISPLAY_CHARS + 1)
    payload: dict[str, object] = {
        **mcp_source_display("Records", "read_items", "https://mcp.test/private-key"),
        **(
            {"_mcp_structured": True, "description": content} if structured else {"result": content}
        ),
    }
    soup = BeautifulSoup(
        McpResultCard().render(payload, RenderContext(language="en")), "html.parser"
    )
    notice = soup.select_one(".lia-card__limit-notice")
    assert notice is not None
    assert card_label("display_limited", "en") in notice.get_text()
    assert notice.find_parent("details") is None
    result = soup.select_one(".lia-mcp__receipt details")
    assert result is not None and not result.has_attr("open")
    origin = soup.select_one(".lia-mcp__metadata a")
    assert origin is not None and origin.get("href") == "https://mcp.test"
    assert "private-key" not in soup.get_text()
