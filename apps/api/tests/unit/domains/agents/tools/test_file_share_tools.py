"""The assistant shares a file, on Drive and OneDrive: a card first (ADR-369, lot 6, D2).

Sharing reaches a third party, whom the drive tells, so no native tool does it unasked: the tool
drafts, the card is the confirmation, and the executor acts from what the card read. A role is
read from the vocabulary and an address is checked before anyone is asked anything.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drive.share_manifest import (
    FILE_SHARE_ROLES,
    SHARE_ROLE_DESCRIPTION,
    share_file_catalogue_manifest,
)
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.file_share_tools import (
    ShareFileTool,
    execute_file_share_draft,
    share_file_tool,
)

pytestmark = pytest.mark.unit

USER = uuid4()
TOOLS = "src.domains.agents.tools.file_share_tools"


def _client(**answers: Any) -> Any:
    client = MagicMock(
        get_file_metadata=AsyncMock(return_value={"id": "f1", "name": "Report.pdf"}),
        share_with=AsyncMock(return_value=None),
    )
    client.configure_mock(**answers)
    return client


async def _run(client: Any, **kwargs: Any) -> dict[str, Any]:
    return await ShareFileTool().execute_api_call(client, USER, **kwargs)


class TestTheContract:
    def test_it_drafts_a_card_it_never_acts_alone(self) -> None:
        assert share_file_catalogue_manifest.mutation_policy == "draft"

    def test_the_roles_are_published_as_the_tool_reads_them(self) -> None:
        role = next(p for p in share_file_catalogue_manifest.parameters if p.name == "role")
        assert tuple(role.constraints[0].value) == FILE_SHARE_ROLES

    def test_manifest_and_schema_read_one_wording(self) -> None:
        schema = share_file_tool.tool_call_schema.model_json_schema()
        assert schema["properties"]["role"]["description"] == SHARE_ROLE_DESCRIPTION


class TestTheDraft:
    async def test_it_names_the_file_and_asks_nothing_of_the_drive_yet(self) -> None:
        client = _client()

        result = await _run(client, file_id="f1", email="ana@x.org", role="writer")

        assert result == {
            "file_id": "f1",
            "email": "ana@x.org",
            "role": "writer",
            "name": "Report.pdf",
        }
        client.share_with.assert_not_awaited()

    async def test_a_reader_by_default(self) -> None:
        result = await _run(_client(), file_id="f1", email="ana@x.org")

        assert result["role"] == "reader"

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"email": "ana@x.org"},
            {"file_id": "f1"},
            {"file_id": "f1", "email": "not an address"},
            {"file_id": "f1", "email": "ana@x.org", "role": "owner"},
        ],
    )
    async def test_what_lacks_is_said_before_anyone_is_asked(self, kwargs: dict[str, str]) -> None:
        client = _client()

        result = await _run(client, **kwargs)

        assert result["error_code"] == ToolErrorCode.INVALID_INPUT.value
        client.get_file_metadata.assert_not_awaited()

    def test_a_refusal_is_a_failure(self) -> None:
        refused = ShareFileTool().format_registry_response(
            {"error_code": "INVALID_INPUT", "message": "no"}
        )

        assert refused.success is False


class TestTheExecution:
    CARD = {"file_id": "f1", "email": "ana@x.org", "role": "writer", "name": "Report.pdf"}

    async def _execute(self, client: Any, card: dict[str, Any]) -> dict[str, Any]:
        with patch(
            "src.domains.connectors.provider_resolver.resolve_client_for_category",
            AsyncMock(return_value=(client, None)),
        ) as resolved:
            answer = await execute_file_share_draft(card, USER, MagicMock())
        assert resolved.await_args.args[0] == "files"
        return answer

    async def test_it_acts_from_what_the_card_read(self) -> None:
        client = _client()

        answer = await self._execute(client, self.CARD)

        client.share_with.assert_awaited_once_with("f1", "ana@x.org", "writer")
        assert answer == {"success": True, "file_id": "f1"}

    async def test_a_role_off_the_vocabulary_shares_nothing(self) -> None:
        client = _client()

        with pytest.raises(ValueError):
            await self._execute(client, {**self.CARD, "role": "owner"})

        client.share_with.assert_not_awaited()


class TestTheCard:
    def test_the_draft_type_is_declared(self) -> None:
        assert DraftType.FILE_SHARE.value == "file_share"
