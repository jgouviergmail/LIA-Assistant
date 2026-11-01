"""The assistant marks e-mails read or unread, on any provider (ADR-369, owner decision D2).

What the clients gained for the « Tools » section reaches the assistant in the
same lot: one neutral tool over ``mark_read``, the active provider resolved by
category. It acts without a card (a read state is undone by the same call with
the other boolean), names what it could not change, and its bound is published
in the words BOTH the planner's manifest and the ReAct schema read (ADR-184,
ADR-310).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.constants import EMAIL_READ_STATE_MAX_MESSAGES
from src.domains.agents.emails.read_state_manifest import (
    READ_STATE_IDS_DESCRIPTION,
    set_email_read_state_catalogue_manifest,
)
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.email_read_state_tools import (
    SetEmailReadStateTool,
    set_email_read_state_tool,
)

pytestmark = pytest.mark.unit

USER = uuid4()


def _client(result: dict[str, Any]) -> Any:
    client = MagicMock()
    client.mark_read = AsyncMock(return_value=result)
    return client


class TestTheManifest:
    def test_it_acts_without_a_card_for_a_written_reason(self) -> None:
        manifest = set_email_read_state_catalogue_manifest
        assert manifest.name == "set_email_read_state_tool"
        assert manifest.mutation_policy == "reversible"
        assert manifest.mutation_policy_reason
        assert manifest.agent == "email_agent"

    def test_the_bound_is_published_to_both_readers(self) -> None:
        """The planner reads the manifest, the ReAct loop the tool schema (ADR-310)."""
        ids = next(
            p for p in set_email_read_state_catalogue_manifest.parameters if p.name == "message_ids"
        )
        assert ids.description == READ_STATE_IDS_DESCRIPTION
        assert str(EMAIL_READ_STATE_MAX_MESSAGES) in READ_STATE_IDS_DESCRIPTION
        schema = set_email_read_state_tool.tool_call_schema.model_json_schema()
        assert schema["properties"]["message_ids"]["description"] == READ_STATE_IDS_DESCRIPTION


class TestTheCall:
    async def test_it_marks_the_named_messages_once_each(self) -> None:
        client = _client({"updated": ["m1", "m2"], "failed": []})

        result = await SetEmailReadStateTool().execute_api_call(
            client, USER, message_ids=["m1", "m2", "m1"], read=False
        )

        client.mark_read.assert_awaited_once_with(["m1", "m2"], False)
        assert result == {
            "updated": ["m1", "m2"],
            "failed": [],
            "read": False,
            "more_remaining": False,
            "not_attempted": [],
        }

    async def test_a_selection_past_the_bound_is_served_up_to_it_and_says_so(self) -> None:
        ids = [f"m{i}" for i in range(EMAIL_READ_STATE_MAX_MESSAGES + 3)]
        client = _client({"updated": ids[:EMAIL_READ_STATE_MAX_MESSAGES], "failed": []})

        result = await SetEmailReadStateTool().execute_api_call(
            client, USER, message_ids=ids, read=True
        )

        assert client.mark_read.await_args.args[0] == ids[:EMAIL_READ_STATE_MAX_MESSAGES]
        assert result["more_remaining"] is True
        assert result["not_attempted"] == ids[EMAIL_READ_STATE_MAX_MESSAGES:]
        output = SetEmailReadStateTool().format_registry_response(result)
        assert f"3 not attempted (at most {EMAIL_READ_STATE_MAX_MESSAGES} per call)" in (
            output.message
        ), "the cut is stated where the model reads first, never a bare boolean"

    async def test_no_message_named_is_refused_without_a_call(self) -> None:
        client = _client({"updated": [], "failed": []})

        result = await SetEmailReadStateTool().execute_api_call(
            client, USER, message_ids=[], read=True
        )

        client.mark_read.assert_not_awaited()
        assert result["error_code"] == ToolErrorCode.INVALID_INPUT.value


class TestWhatTheModelReads:
    def test_messages_all_gone_are_a_failure_that_says_to_list_again(self) -> None:
        output = SetEmailReadStateTool().format_registry_response(
            {
                "updated": [],
                "failed": [{"id": "m1", "status": "not_found"}],
                "read": True,
                "more_remaining": False,
            }
        )
        assert output.success is False
        assert output.error_code == ToolErrorCode.NOT_FOUND.value

    def test_a_partial_change_is_a_success_that_names_the_rest(self) -> None:
        output = SetEmailReadStateTool().format_registry_response(
            {
                "updated": ["m1"],
                "failed": [{"id": "m2", "status": "not_found"}],
                "read": False,
                "more_remaining": False,
            }
        )
        assert output.success is True
        assert "1 marked unread" in output.message
        assert output.structured_data["failed"] == [{"id": "m2", "status": "not_found"}]
