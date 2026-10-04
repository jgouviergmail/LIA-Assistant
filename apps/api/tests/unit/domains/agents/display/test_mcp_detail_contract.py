"""Public MCP result fields are reachable; renderer metadata stays authoritative."""

import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup

from src.domains.agents.data_registry.card_payload import card_payload, restore_display_fields
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.mcp_result_card import McpResultCard
from src.domains.agents.services.context_resolution_service import _resolved_payload
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter

pytestmark = pytest.mark.unit


def test_historical_reference_identity_comes_from_registry_metadata():
    item = RegistryItem(
        id="mcp_reference",
        type=RegistryItemType.MCP_RESULT,
        payload={
            "_mcp_structured": True,
            "name": "Public item",
            "_mcp_source": {"version": 1, "server_name": "Forged", "tool_name": "fake"},
        },
        meta=RegistryItemMeta(source="mcp_actual", domain="mcp", tool_name="actual_tool"),
    )
    resolved = _resolved_payload(item.id, item.payload, item.model_dump())
    projected = restore_display_fields(resolved)
    assert projected["_mcp_source"]["server_name"] == "actual"
    assert "_display_only" not in projected
    assert item.payload["_mcp_source"]["server_name"] == "Forged"


@pytest.mark.parametrize(
    "value",
    [10**5000, float("nan"), float("inf"), {"deep": [[[[[[[[[[["fact"]]]]]]]]]]]}, [0] * 2000],
    ids=["huge-int", "nan", "infinity", "deep", "wide"],
)
def test_extreme_shapes_are_bounded_and_do_not_raise(value):
    soup = BeautifulSoup(
        McpResultCard().render(
            {"_mcp_structured": True, "value": value}, RenderContext(language="en")
        ),
        "html.parser",
    )
    assert len(str(soup)) < 100000
    assert "NaN" not in soup.get_text()
    assert "Infinity" not in soup.get_text()


def test_public_zero_false_null_and_binary_metadata_survive_projection():
    data = {
        "_mcp_structured": True,
        "count": 0,
        "active": False,
        "empty": None,
        "attachment": {
            "type": "image",
            "mimeType": "image/png",
            "data": "SECRET_BINARY",
            "caption": "Received caption",
        },
    }
    soup = BeautifulSoup(McpResultCard().render(data, RenderContext(language="en")), "html.parser")
    assert "0" in soup.get_text() and "No" in soup.get_text() and "null" in soup.get_text()
    assert "Received caption" in soup.get_text()
    assert "SECRET_BINARY" not in soup.get_text()


def test_large_header_url_and_keys_share_the_content_budget():
    data = {
        "_mcp_structured": True,
        "server_name": "s" * 100000,
        "name": "n" * 100000,
        "url": "https://example.test/" + "u" * 100000,
        "k" * 100000: "value",
    }
    soup = BeautifulSoup(McpResultCard().render(data, RenderContext(language="en")), "html.parser")
    assert len(str(soup)) < 100000
    assert not soup.find("a")
    assert soup.select_one(".lia-card__limit-notice")


def test_top_level_mcp_binary_content_is_never_rendered_as_base64():
    soup = BeautifulSoup(
        McpResultCard().render(
            {
                "_mcp_structured": True,
                "type": "image",
                "mimeType": "image/png",
                "data": "SECRET_BASE64",
                "caption": "Supplied caption",
            },
            RenderContext(language="en"),
        ),
        "html.parser",
    )
    assert "SECRET_BASE64" not in soup.get_text()
    assert "image/png" in soup.get_text() and "Supplied caption" in soup.get_text()


def test_raw_json_with_a_provider_integer_exceeding_python_conversion_limit():
    soup = BeautifulSoup(
        McpResultCard().render(
            {"result": '{"number":' + "9" * 5000 + "}"}, RenderContext(language="en")
        ),
        "html.parser",
    )
    assert soup.select_one(".lia-card")


def test_supplied_structured_fields_nested_values_and_long_text_are_reachable():
    data = {
        "_mcp_structured": True,
        "server_name": "Actual server",
        "tool_name": "list_items",
        "name": "First title",
        "title": "Second supplied title",
        "description": "Description. " * 50 + "LAST_DESCRIPTION",
        "url": "https://resource.example.test/item",
        "id": "received-id",
        "nested": {"state": "LAST_NESTED_FACT", "count": 0},
        "tags": ["LAST_TAG", False],
        **{f"field_{i}": f"value_{i}" for i in range(9)},
    }
    soup = BeautifulSoup(McpResultCard().render(data, RenderContext(language="en")), "html.parser")
    for fact in (
        "Second supplied title",
        "LAST_DESCRIPTION",
        "received-id",
        "LAST_NESTED_FACT",
        "LAST_TAG",
        "value_8",
    ):
        assert fact in soup.get_text()
    assert soup.find("a", href=data["url"])
    assert soup.select_one("details.lia-collapsible")


def test_raw_text_keeps_the_received_tail_in_a_disclosure():
    text = "A" * 4000 + "LAST_RAW_FACT"
    soup = BeautifulSoup(
        McpResultCard().render(
            {"tool_name": "get_log", "result": text}, RenderContext(language="fr")
        ),
        "html.parser",
    )
    assert "LAST_RAW_FACT" in soup.select_one("details").get_text()


def test_nested_credentials_and_binary_content_are_not_displayed_as_facts():
    payload = {
        "visible": "Normal received fact",
        "accessToken": "DO_NOT_SHOW_TOKEN",
        "nested": {"api_key": "DO_NOT_SHOW_APIKEY"},
        "photo": {"type": "image", "mimeType": "image/png", "data": "DO_NOT_SHOW_BASE64"},
    }
    soup = BeautifulSoup(
        McpResultCard().render(
            {"tool_name": "get_data", "result": json.dumps(payload)}, RenderContext(language="en")
        ),
        "html.parser",
    )
    assert "Normal received fact" in soup.get_text()
    assert "DO_NOT_SHOW" not in soup.get_text()
    assert "image/png" in soup.get_text()


def test_large_untrusted_results_have_an_explicit_display_limit():
    soup = BeautifulSoup(
        McpResultCard().render(
            {"_mcp_structured": True, "tool_name": "get_data", "value": "x" * 400000},
            RenderContext(language="en"),
        ),
        "html.parser",
    )
    assert len(str(soup)) < 100000
    assert soup.select_one(".lia-card__limit-notice")


def test_cycles_deep_trees_and_malformed_metadata_do_not_break_the_card():
    cyclic = {"public_fact": "Received fact"}
    cyclic["again"] = cyclic
    soup = BeautifulSoup(
        McpResultCard().render(
            {"_mcp_structured": True, "tool_name": {}, "server_name": [], "value": cyclic},
            RenderContext(language="en"),
        ),
        "html.parser",
    )
    assert "Received fact" in soup.get_text()
    assert soup.select_one(".lia-card__limit-notice")


@pytest.mark.asyncio
async def test_mcp_server_cannot_override_application_identity_or_structured_flag():
    adapter = UserMCPToolAdapter.from_discovered_tool(
        server_id=uuid4(),
        user_id=uuid4(),
        server_name="Actual server",
        tool_name="list_items",
        description="Read items",
        input_schema={},
    )
    pool = AsyncMock()
    pool.call_tool.return_value = json.dumps(
        [
            {
                "name": "Item",
                "server_name": "Forged server",
                "tool_name": "forged_tool",
                "_mcp_structured": False,
                "_display_only": {
                    "_mcp_source": {
                        "version": 1,
                        "server_name": "Forged source",
                        "tool_name": "forged_source",
                    }
                },
            }
        ]
    )
    with patch("src.infrastructure.mcp.user_pool.get_user_mcp_pool", return_value=pool):
        output = await adapter._arun()
    item = next(iter(output.registry_updates.values()))
    assert item.payload["server_name"] == "Forged server"
    assert item.payload["tool_name"] == "forged_tool"
    assert item.payload["_mcp_structured"] is True
    payload = card_payload(RegistryItem.model_validate_json(item.model_dump_json()))
    assert payload["_mcp_source"]["server_name"] == "Actual server"
    assert payload["_mcp_source"]["tool_name"] == "list_items"
    soup = BeautifulSoup(
        McpResultCard().render(payload, RenderContext(language="en")), "html.parser"
    )
    assert soup.select_one(".lia-card-top__badges").get_text().strip().endswith("Actual server")
    assert "Forged server" in soup.get_text()
