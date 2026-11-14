"""The ONE vendor tool of a Live owner call — ``send_to_lia`` (ADR-301).

Its body is the async shape lot 0 measured, its name and description are the
browser's own declaration, it is provisioned once per connector by
fingerprint and re-created on drift, and a vendor refusal leaves the dial
without it rather than without a dial.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.core.config import settings
from src.core.constants import LIVE_DELEGATION_TOOL_NAME
from src.domains.telephony.client import ElevenLabsAgentsError
from src.domains.telephony.delegation_tool import (
    METADATA_DELEGATION_HASH,
    METADATA_DELEGATION_ID,
    delegation_tool_body,
    delegation_wait_seconds,
    ensure_vendor_delegation_tool,
)
from src.domains.telephony.live_tools import live_tool_token
from src.domains.voice_sessions.mandate import (
    delegation_request_schema,
    delegation_tool_description,
)

pytestmark = pytest.mark.unit


class _Client:
    """The workspace as the vendor keeps it: what it was sent, plus its own defaults
    (measured 2026-11-11), rewritten in place by a PATCH that replaces the config."""

    def __init__(self, fail_create: bool = False, fail_listing: bool = False) -> None:
        self.created: list[dict[str, Any]] = []
        self.deleted: list[str] = []
        self.rewritten: list[tuple[str, dict[str, Any]]] = []
        self.tools: dict[str, dict[str, Any]] = {}
        self.fail_create = fail_create
        self.fail_listing = fail_listing

    async def create_tool(self, body: dict[str, Any]) -> str:
        if self.fail_create:
            raise ElevenLabsAgentsError(500, "boom")
        self.created.append(body)
        tool_id = f"tool_{len(self.created)}"
        self.tools[tool_id] = {"execution_mode_default": "vendor", **body["tool_config"]}
        return tool_id

    async def update_tool(self, tool_id: str, body: dict[str, Any]) -> None:
        if tool_id not in self.tools:
            raise ElevenLabsAgentsError(404, "gone")
        self.rewritten.append((tool_id, body))
        self.tools[tool_id] = dict(body["tool_config"])

    async def list_tools(self, kind: str) -> list[dict[str, Any]]:
        if self.fail_listing:
            raise ElevenLabsAgentsError(500, "boom")
        return [
            {"id": tool_id, "tool_config": config}
            for tool_id, config in self.tools.items()
            if config.get("type") == kind
        ]

    async def delete_tool(self, tool_id: str) -> None:
        self.deleted.append(tool_id)
        self.tools.pop(tool_id, None)


class _DB:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


@pytest.fixture(autouse=True)
def _public_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "api_url", "https://lia-back.example.test", raising=False)
    monkeypatch.setattr(settings, "telephony_callback_base_url", None, raising=False)
    monkeypatch.setattr(settings, "telephony_delegation_timeout_seconds", 90, raising=False)


def test_the_body_is_the_async_shape_with_the_shared_name_and_description() -> None:
    body = delegation_tool_body(token="tok", user_name="Alex")
    config = body["tool_config"]
    assert config["name"] == LIVE_DELEGATION_TOOL_NAME
    assert config["description"] == delegation_tool_description("Alex")
    assert config["execution_mode"] == "async"
    assert config["pre_tool_speech"] == "force"
    assert config["response_timeout_secs"] == 90
    schema = config["api_schema"]
    assert (
        schema["url"]
        == f"https://lia-back.example.test/api/v1/telephony/tools/{LIVE_DELEGATION_TOOL_NAME}"
    )
    assert schema["request_headers"] == {"X-LIA-Tool-Secret": "tok"}
    assert set(schema["request_body_schema"]["properties"]) == {"call_id", "request"}
    assert schema["request_body_schema"]["required"] == ["call_id", "request"]
    # The vendor reads the same parameter the browser's declaration carries:
    # one description, never a second copy typed in the phone's module.
    request = schema["request_body_schema"]["properties"]["request"]
    assert (
        request["description"]
        == delegation_request_schema()["properties"]["request"]["description"]
    )


def test_the_bridge_waits_the_inner_margin_under_the_vendor_timeout() -> None:
    assert delegation_wait_seconds() == 87.0


async def test_provisioned_once_then_remembered_by_fingerprint() -> None:
    client = _Client()
    db = _DB()
    connector = SimpleNamespace(connector_metadata={"agent_id": "ag"})

    first = await ensure_vendor_delegation_tool(
        db,
        connector=connector,
        api_key="k",
        api_secret="whsec",
        user_name="Alex",
        client_factory=lambda _k: client,
    )
    assert first == "tool_1"
    assert client.created[0]["tool_config"]["api_schema"]["request_headers"] == {
        "X-LIA-Tool-Secret": live_tool_token("whsec")
    }
    meta = connector.connector_metadata
    assert meta[METADATA_DELEGATION_ID] == "tool_1"
    assert meta[METADATA_DELEGATION_HASH]
    assert meta["agent_id"] == "ag"  # a NEW dict, the old keys kept
    assert db.commits == 1

    again = await ensure_vendor_delegation_tool(
        db,
        connector=connector,
        api_key="k",
        api_secret="whsec",
        user_name="Alex",
        client_factory=lambda _k: client,
    )
    assert again == "tool_1"
    assert len(client.created) == 1 and db.commits == 1


async def test_a_drift_re_creates_the_tool_and_deletes_the_old_one() -> None:
    client = _Client()
    db = _DB()
    connector = SimpleNamespace(connector_metadata={"agent_id": "ag"})
    await ensure_vendor_delegation_tool(
        db,
        connector=connector,
        api_key="k",
        api_secret="whsec",
        user_name="Alex",
        client_factory=lambda _k: client,
    )
    # The person renamed themselves: the description drifts.
    renamed = await ensure_vendor_delegation_tool(
        db,
        connector=connector,
        api_key="k",
        api_secret="whsec",
        user_name="Alexandra",
        client_factory=lambda _k: client,
    )
    assert renamed == "tool_2"
    assert client.deleted == ["tool_1"]
    assert connector.connector_metadata[METADATA_DELEGATION_ID] == "tool_2"
    assert db.commits == 2


async def test_a_vendor_refusal_leaves_no_tool_and_no_write() -> None:
    client = _Client(fail_create=True)
    db = _DB()
    connector = SimpleNamespace(connector_metadata={"agent_id": "ag"})
    tool_id = await ensure_vendor_delegation_tool(
        db,
        connector=connector,
        api_key="k",
        api_secret="whsec",
        user_name="Alex",
        client_factory=lambda _k: client,
    )
    assert tool_id is None
    assert METADATA_DELEGATION_ID not in connector.connector_metadata
    assert db.commits == 0


async def _ensure(client: _Client, db: _DB, connector: SimpleNamespace) -> str | None:
    return await ensure_vendor_delegation_tool(
        db,
        connector=connector,
        api_key="k",
        api_secret="whsec",
        user_name="Alex",
        client_factory=lambda _k: client,
    )


async def test_a_delegation_tool_edited_on_the_portal_is_rewritten_before_the_dial() -> None:
    """Owner decision 2026-11-11: never an agent with tools out of date. The tool is
    held against what the workspace serves before every Live owner call; edited on
    the portal, it is rewritten in place under its id — nothing to record anew."""
    client = _Client()
    db = _DB()
    connector = SimpleNamespace(connector_metadata={"agent_id": "ag"})
    assert await _ensure(client, db, connector) == "tool_1"
    client.tools["tool_1"]["description"] = "Edited by hand on the portal."

    assert await _ensure(client, db, connector) == "tool_1"
    assert client.rewritten == [
        ("tool_1", delegation_tool_body(token=live_tool_token("whsec"), user_name="Alex"))
    ]
    assert len(client.created) == 1 and db.commits == 1


async def test_a_delegation_tool_the_workspace_lost_is_re_created_and_recorded() -> None:
    client = _Client()
    db = _DB()
    connector = SimpleNamespace(connector_metadata={"agent_id": "ag"})
    assert await _ensure(client, db, connector) == "tool_1"
    del client.tools["tool_1"]  # deleted on the portal

    assert await _ensure(client, db, connector) == "tool_2"
    assert connector.connector_metadata[METADATA_DELEGATION_ID] == "tool_2"
    assert db.commits == 2


async def test_a_workspace_that_cannot_be_read_leaves_the_call_without_its_tool() -> None:
    """A tool that cannot be verified is never handed to a call: the caller then
    decides what a call without it may be."""
    client = _Client()
    db = _DB()
    connector = SimpleNamespace(connector_metadata={"agent_id": "ag"})
    assert await _ensure(client, db, connector) == "tool_1"
    client.fail_listing = True

    assert await _ensure(client, db, connector) is None
    assert connector.connector_metadata[METADATA_DELEGATION_ID] == "tool_1"
