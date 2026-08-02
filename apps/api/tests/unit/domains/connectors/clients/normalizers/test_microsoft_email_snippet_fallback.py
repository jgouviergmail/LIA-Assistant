"""Outlook search results came back with an EMPTY snippet — always.

`search_emails` asks Graph for `_MESSAGE_LIST_SELECT_FIELDS`, which requests
`bodyPreview` and NOT `body`; the normalizer then built the snippet from
`msg["body"]["content"]`, a field that `$select` never asked for. Every Outlook
search and list therefore produced `snippet=""` (and `body=""`), while the
preview Graph had already returned — and billed — sat unused in the payload.

Only the DETAIL path selects `body`, so its output must stay byte-identical:
the fallback fires solely when the body is absent.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.connectors.clients.microsoft_outlook_client import (
    _MESSAGE_LIST_SELECT_FIELDS,
    _MESSAGE_SELECT_FIELDS,
)
from src.domains.connectors.clients.normalizers.microsoft_email_normalizer import (
    normalize_graph_message,
)

pytestmark = pytest.mark.unit

PREVIEW = "Bonjour, on se voit jeudi ?"
BODY_HTML = "<html><body><p>Bonjour, on se voit jeudi ?</p></body></html>"


def _graph_message(*, with_body: bool, preview: str | None = PREVIEW) -> dict[str, Any]:
    """A Graph message as returned for one of the two $select sets."""
    message: dict[str, Any] = {
        "id": "AAMk1",
        "conversationId": "cv1",
        "subject": "Jeudi",
        "from": {"emailAddress": {"name": "Marie", "address": "marie@x.com"}},
        "toRecipients": [{"emailAddress": {"address": "moi@x.com"}}],
        "receivedDateTime": "2026-07-30T09:12:00Z",
        "isRead": False,
        "hasAttachments": False,
    }
    if preview is not None:
        message["bodyPreview"] = preview
    if with_body:
        message["body"] = {"content": BODY_HTML, "contentType": "html"}
    return message


class TestSelectSetsAreWhatTheyClaim:
    """The premise of the whole test: LIST asks for the preview, not the body."""

    def test_list_select_has_preview_but_no_body(self) -> None:
        assert "bodyPreview" in _MESSAGE_LIST_SELECT_FIELDS
        assert "body," not in _MESSAGE_LIST_SELECT_FIELDS

    def test_detail_select_has_the_body(self) -> None:
        assert "body," in _MESSAGE_SELECT_FIELDS


class TestSearchResultsCarryAnExcerpt:
    def test_snippet_falls_back_to_body_preview(self) -> None:
        result = normalize_graph_message(_graph_message(with_body=False))

        assert result["snippet"] == PREVIEW

    def test_html_in_the_preview_is_stripped(self) -> None:
        result = normalize_graph_message(
            _graph_message(with_body=False, preview="<b>Salut</b> Marie")
        )

        assert result["snippet"] == "Salut Marie"

    def test_preview_is_capped_like_a_body_snippet(self) -> None:
        long_preview = "a" * 500
        result = normalize_graph_message(_graph_message(with_body=False, preview=long_preview))

        assert 0 < len(result["snippet"]) < 500


class TestNothingIsFabricated:
    @pytest.mark.parametrize("preview", [None, "", "   "])
    def test_no_body_and_no_preview_yields_no_snippet(self, preview: str | None) -> None:
        """An empty message gets an ABSENT excerpt, never a blank line."""
        result = normalize_graph_message(_graph_message(with_body=False, preview=preview))

        assert result["snippet"] == ""

    def test_body_is_not_faked_from_the_preview(self) -> None:
        """`body` means the full body. Filling it with a 255-char preview would
        make every downstream reader believe it holds the whole message."""
        result = normalize_graph_message(_graph_message(with_body=False))

        assert result["body"] == ""


class TestDetailPathUnchanged:
    def test_detail_output_is_identical_to_before_the_fallback(self) -> None:
        """When `body` IS selected, the fallback must not touch anything."""
        result = normalize_graph_message(_graph_message(with_body=True))

        assert result["snippet"] == PREVIEW
        assert result["body"] == BODY_HTML

    def test_body_wins_over_a_divergent_preview(self) -> None:
        """Graph truncates bodyPreview; the real body is the better source."""
        message = _graph_message(with_body=True, preview="tronqué…")

        assert normalize_graph_message(message)["snippet"] == PREVIEW
