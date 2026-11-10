"""The agent's voicemail message stays configured through the provider's portal."""

from __future__ import annotations

import json
from typing import Literal

import httpx
import pytest

from src.domains.telephony.agent_prompt import build_agent_config
from src.domains.telephony.client import ElevenLabsAgentsClient


@pytest.mark.unit
@pytest.mark.parametrize("operation", ["create", "update"])
async def test_agent_requests_enable_voicemail_without_writing_its_portal_message(
    operation: Literal["create", "update"],
) -> None:
    """Inspect the actual HTTP payload; the message stays owned by the portal."""
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"agent_id": "agent_test"})

    client = ElevenLabsAgentsClient(api_key="test-key", transport=httpx.MockTransport(handle))
    config = build_agent_config("fr", "Alex")
    if operation == "create":
        await client.create_agent(
            name=config.name,
            system_prompt=config.system_prompt,
            first_message=config.first_message,
            data_collection=config.data_collection,
        )
    else:
        await client.update_agent(
            "agent_test",
            name=config.name,
            system_prompt=config.system_prompt,
            first_message=config.first_message,
            data_collection=config.data_collection,
        )

    [request] = requests
    body = json.loads(request.content)
    tools = body["conversation_config"]["agent"]["prompt"]["built_in_tools"]
    assert tools["voicemail_detection"] == {"name": "voicemail_detection"}
    assert "voicemail_message" not in request.content.decode()
