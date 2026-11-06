"""How a message says it can be left (ADR-369, lot 3; RFC 2369, RFC 8058).

A sender's header is a stranger's words: only an https page and a mail address are
kept, one-click needs the sender's own ``List-Unsubscribe-Post`` AND an https page,
and a header too long to be honest reads as none.
"""

from __future__ import annotations

import pytest

from src.domains.connectors.clients.mail_unsubscribe import (
    ONE_CLICK_BODY,
    Unsubscribe,
    read_unsubscribe,
)

pytestmark = pytest.mark.unit


class TestReadUnsubscribe:
    def test_nothing_said_is_no_way_out(self) -> None:
        assert read_unsubscribe(None, None) is None
        assert read_unsubscribe("", None) is None

    def test_a_page_and_an_address_are_kept(self) -> None:
        found = read_unsubscribe(
            "<mailto:leave@example.org?subject=stop>, <https://example.org/leave?u=1>", None
        )

        assert found == Unsubscribe(
            web_url="https://example.org/leave?u=1",
            mail_to="leave@example.org?subject=stop",
            one_click=False,
        )

    def test_one_click_needs_the_sender_s_word_and_a_page(self) -> None:
        with_word = read_unsubscribe("<https://example.org/leave>", ONE_CLICK_BODY)
        assert with_word is not None and with_word.one_click

        other_word = read_unsubscribe("<https://example.org/leave>", "List-Unsubscribe=Maybe")
        assert other_word is not None and not other_word.one_click

        no_page = read_unsubscribe("<mailto:leave@example.org>", ONE_CLICK_BODY)
        assert no_page is not None and not no_page.one_click

    def test_the_word_is_read_whatever_its_case_and_spaces(self) -> None:
        found = read_unsubscribe("<https://example.org/leave>", " list-unsubscribe=one-click ")

        assert found is not None and found.one_click

    @pytest.mark.parametrize(
        "header",
        [
            "<http://example.org/leave>",
            "<javascript:alert(1)>",
            "<data:text/html,x>",
            "<ftp://example.org/leave>",
            "<https://user:secret@example.org/leave>",
            "<https:///leave>",
            "https://example.org/leave",
        ],
    )
    def test_nothing_else_is_followed(self, header: str) -> None:
        assert read_unsubscribe(header, ONE_CLICK_BODY) is None

    def test_the_first_of_each_kind_stands(self) -> None:
        found = read_unsubscribe(
            "<https://a.example.org/x>, <https://b.example.org/y>, "
            "<mailto:a@example.org>, <mailto:b@example.org>",
            None,
        )

        assert found == Unsubscribe(
            web_url="https://a.example.org/x", mail_to="a@example.org", one_click=False
        )

    def test_folded_headers_read_as_one_line(self) -> None:
        found = read_unsubscribe("<https://example.org/\r\n leave>", None)

        assert found is not None and found.web_url == "https://example.org/leave"

    def test_a_header_past_any_honest_length_reads_as_none(self) -> None:
        assert read_unsubscribe("<https://example.org/" + "a" * 5000 + ">", None) is None

    def test_a_mail_address_with_no_mailbox_is_no_address(self) -> None:
        assert read_unsubscribe("<mailto:>", None) is None
        assert read_unsubscribe("<mailto:?subject=stop>", None) is None
