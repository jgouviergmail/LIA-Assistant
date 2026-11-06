"""Deleting a Gmail filter from the chat (ADR-369, D2).

The person's own hands delete a filter, so the assistant does too, through the
whole HITL draft. It reads the filter Gmail holds, never the one a model named,
and the card says what that filter matches and does: two filters on one sender
differ only by what they do.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.drafts.card_spec import to_markdown_lines
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.preview_renderer import _render_email_filter_delete
from src.domains.agents.tools.mailbox_settings_tools import (
    DeleteEmailFilterTool,
    execute_email_filter_delete_draft,
)
from src.domains.shared.markdown_literal import read_as_markdown

pytestmark = pytest.mark.unit

_FILTERS = {
    "filter": [
        {
            "id": "f1",
            "criteria": {"from": "news@example.org"},
            "action": {"addLabelIds": ["Label_7"]},
        },
        {
            "id": "f2",
            "criteria": {"from": "news@example.org", "hasAttachment": True},
            "action": {
                "addLabelIds": ["Label_8", "STARRED"],
                "removeLabelIds": ["INBOX", "UNREAD"],
                "forward": "archive@example.org",
            },
        },
    ]
}


def _gmail() -> Any:
    return SimpleNamespace(
        list_filters=AsyncMock(return_value=_FILTERS),
        label_names=AsyncMock(return_value={"Label_7": "Newsletters", "Label_8": "Receipts"}),
    )


def _card(content: dict[str, Any], language: str = "en") -> str:
    labels = get_draft_preview_labels(language)
    lines = _render_email_filter_delete(content, labels, lambda value: value or "")
    return read_as_markdown("\n".join(to_markdown_lines(lines, labels["separator"])))


class TestTheToolReadsWhatGmailHolds:
    async def test_the_draft_describes_the_filter_gmail_holds(self) -> None:
        result = await DeleteEmailFilterTool().execute_api_call(_gmail(), uuid4(), filter_id="f2")

        assert result == {
            "success": True,
            "filter_id": "f2",
            "criteria": {"from": "news@example.org", "hasAttachment": True},
            # A label nobody listed keeps its id: the card never drops what it does.
            "label_names": ["Receipts", "STARRED"],
            "archive": True,
            "mark_as_read": True,
            "forward": "archive@example.org",
        }

    async def test_an_id_gmail_does_not_hold_is_refused(self) -> None:
        result = await DeleteEmailFilterTool().execute_api_call(
            _gmail(), uuid4(), filter_id="invented"
        )

        assert result == {"success": False, "error": "filter_not_found"}

    async def test_a_filter_with_no_label_reads_no_label_name(self) -> None:
        gmail = _gmail()
        gmail.list_filters.return_value = {
            "filter": [
                {
                    "id": "f3",
                    "criteria": {"to": "me@example.org"},
                    "action": {"removeLabelIds": ["INBOX"]},
                }
            ]
        }

        result = await DeleteEmailFilterTool().execute_api_call(gmail, uuid4(), filter_id="f3")

        assert result["label_names"] == []
        assert result["archive"] is True
        assert result["mark_as_read"] is False
        gmail.label_names.assert_not_awaited()

    def test_a_refusal_files_no_draft(self) -> None:
        output = DeleteEmailFilterTool().format_registry_response(
            {"success": False, "error": "filter_not_found"}
        )

        assert output.success is False
        assert output.error_code == "filter_not_found"
        assert not output.metadata.get("requires_confirmation")

    def test_a_filter_read_files_the_draft_of_its_deletion(self) -> None:
        output = DeleteEmailFilterTool().format_registry_response(
            {
                "success": True,
                "filter_id": "f2",
                "criteria": {"from": "news@example.org"},
                "label_names": ["Receipts"],
                "archive": True,
                "mark_as_read": False,
                "forward": "",
            }
        )

        assert output.metadata["requires_confirmation"] is True
        assert output.metadata["draft_type"] == DraftType.EMAIL_FILTER_DELETE.value
        content = next(iter(output.registry_updates.values())).payload["content"]
        assert content["filter_id"] == "f2"
        assert content["filter_summary"] == "from:news@example.org → Receipts"


class TestTheCard:
    _WHOLE = {
        "criteria": {
            "from": "news@example.org",
            "to": "me@example.org",
            "subject": "promo",
            "query": "larger:5M",
            "hasAttachment": True,
        },
        "label_names": ["Receipts", "STARRED"],
        "archive": True,
        "mark_as_read": True,
        "forward": "archive@example.org",
    }

    def test_it_says_what_the_filter_matches_and_does(self) -> None:
        labels = get_draft_preview_labels("en")

        shown = _card(self._WHOLE)

        for fact in (
            "news@example.org",
            "me@example.org",
            "promo",
            "larger:5M",
            "Receipts, STARRED",
            "archive@example.org",
            labels["filter_with_attachment"],
            labels["filter_does_archive"],
            labels["filter_does_mark_read"],
            labels["filter_delete_effect"],
        ):
            assert fact in shown

    def test_what_the_filter_does_not_do_is_not_said(self) -> None:
        labels = get_draft_preview_labels("en")

        shown = _card({"criteria": {"from": "news@example.org"}, "label_names": ["Receipts"]})

        for absent in (
            labels["filter_with_attachment"],
            labels["filter_does_archive"],
            labels["filter_does_mark_read"],
            labels["filter_forward"],
        ):
            assert absent not in shown
        assert labels["filter_delete_effect"] in shown

    def test_it_never_reads_as_a_filter_about_to_act(self) -> None:
        labels = get_draft_preview_labels("en")

        shown = _card(self._WHOLE)

        assert labels["filter_archive"] not in shown
        assert labels["filter_mark_read"] not in shown


class TestTheExecutor:
    @staticmethod
    def _deps() -> MagicMock:
        service = MagicMock()
        service.get_connector_credentials = AsyncMock(return_value=MagicMock())
        deps = MagicMock()
        deps.get_connector_service = AsyncMock(return_value=service)
        return deps

    async def test_the_filter_is_deleted_and_its_client_closed(self) -> None:
        client = MagicMock(delete_filter=AsyncMock(), close=AsyncMock())

        with patch(
            "src.domains.agents.tools.mailbox_settings_tools.GoogleGmailSettingsClient",
            return_value=client,
        ):
            result = await execute_email_filter_delete_draft(
                {"filter_id": "f2"}, uuid4(), self._deps()
            )

        assert result == {"success": True, "filter_id": "f2"}
        client.delete_filter.assert_awaited_once_with("f2")
        client.close.assert_awaited_once()

    async def test_a_failed_delete_is_no_success_and_closes_its_client(self) -> None:
        client = MagicMock(delete_filter=AsyncMock(side_effect=OSError), close=AsyncMock())

        with (
            patch(
                "src.domains.agents.tools.mailbox_settings_tools.GoogleGmailSettingsClient",
                return_value=client,
            ),
            pytest.raises(OSError),
        ):
            await execute_email_filter_delete_draft({"filter_id": "f2"}, uuid4(), self._deps())

        client.close.assert_awaited_once()
