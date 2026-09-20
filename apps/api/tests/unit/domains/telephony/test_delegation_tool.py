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
    def __init__(self, fail_create: bool = False) -> None:
        self.created: list[dict[str, Any]] = []
        self.deleted: list[str] = []
        self.fail_create = fail_create

    async def create_tool(self, body: dict[str, Any]) -> str:
        if self.fail_create:
            raise ElevenLabsAgentsError(500, "boom")
        self.created.append(body)
        return f"tool_{len(self.created)}"

    async def delete_tool(self, tool_id: str) -> None:
        self.deleted.append(tool_id)


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
