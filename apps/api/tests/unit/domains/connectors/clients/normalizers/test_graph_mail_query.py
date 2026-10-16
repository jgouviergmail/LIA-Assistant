"""A Gmail-style query becomes ONE request Microsoft Graph accepts (RC3.1).

Graph's documented constraints: on ``/messages`` a ``$search`` combines with
neither ``$filter`` nor ``$orderby``, and a ``$filter`` with ``$orderby`` must
be LED by the sort property (``InefficientFilter`` otherwise). The translation
used to hand the client a search AND a filter, and the client dropped the
SEARCH — the very criterion naming the mail: « Marie's unread mails » listed
every unread mail, and a filter alone (« my unread mails ») was refused for its
order.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.connectors.clients.normalizers.graph_mail_query import graph_mail_query

pytestmark = pytest.mark.unit

ORDER = "receivedDateTime desc"
EARLIEST = "receivedDateTime ge 1900-01-01T00:00:00Z"


def _message(**fields: Any) -> dict[str, Any]:
    return {"receivedDateTime": "2026-10-05T09:00:00Z", "isRead": False, **fields}


class TestAFilterAlone:
    def test_is_led_by_the_sort_property(self) -> None:
        query = graph_mail_query("is:unread")

        assert query.params == {"$filter": f"{EARLIEST} and isRead eq false", "$orderby": ORDER}

    def test_its_dates_lead_whatever_the_order_of_the_operators(self) -> None:
        query = graph_mail_query("has:attachment before:2026/10/08 after:2026/10/01")

        assert query.params["$filter"] == (
            "receivedDateTime lt 2026-10-08T00:00:00Z"
            " and receivedDateTime ge 2026-10-01T00:00:00Z"
            " and hasAttachments eq true"
        )

    @pytest.mark.parametrize(
        "text",
        ["is:unread", "is:read has:attachment", "is:unread after:2026/10/01", "before:2026/1/5"],
    )
    def test_every_filter_meets_the_documented_ordering_rule(self, text: str) -> None:
        params = graph_mail_query(text).params

        assert params["$orderby"] == ORDER
        assert params["$filter"].startswith("receivedDateTime ")
        assert "$search" not in params

    def test_the_server_applies_everything_so_the_page_is_whole(self) -> None:
        query = graph_mail_query("is:unread after:2026/10/01")

        assert query.screen([_message(isRead=True)]) == ([_message(isRead=True)], 0)


class TestASearch:
    def test_keeps_the_terms_that_name_the_mail(self) -> None:
        query = graph_mail_query("from:Marie is:unread after:2026/10/01")

        assert query.params == {"$search": '"from:Marie"'}

    def test_carries_the_attachment_condition_in_kql(self) -> None:
        query = graph_mail_query("from:Marie has:attachment budget")

        assert query.params == {"$search": '"from:Marie budget hasAttachments:true"'}

    def test_checks_on_its_page_what_kql_cannot_say(self) -> None:
        query = graph_mail_query("report is:unread after:2026/10/01")

        kept, set_aside = query.screen(
            [
                _message(id="kept"),
                _message(id="read", isRead=True),
                _message(id="older", receivedDateTime="2026-09-30T23:59:59Z"),
            ]
        )

        assert [message["id"] for message in kept] == ["kept"]
        assert set_aside == 2

    def test_a_read_state_asked_for_is_the_one_kept(self) -> None:
        query = graph_mail_query("report is:read")

        kept, _ = query.screen([_message(id="unread"), _message(id="read", isRead=True)])

        assert [message["id"] for message in kept] == ["read"]

    def test_before_excludes_the_day_it_names(self) -> None:
        query = graph_mail_query("report before:2026/10/05")

        kept, _ = query.screen(
            [
                _message(id="that day", receivedDateTime="2026-10-05T00:00:00Z"),
                _message(id="the day before", receivedDateTime="2026-10-04T23:59:59Z"),
            ]
        )

        assert [message["id"] for message in kept] == ["the day before"]

    def test_a_message_without_a_readable_date_is_not_claimed_to_match(self) -> None:
        query = graph_mail_query("report after:2026/10/01")

        kept, set_aside = query.screen([_message(receivedDateTime=None), _message(id="dated")])

        assert [message.get("id") for message in kept] == ["dated"]
        assert set_aside == 1


class TestASenderAddress:
    def test_alone_beside_conditions_is_the_servers_filter(self) -> None:
        query = graph_mail_query("from:marie@example.com is:unread")

        assert query.params == {
            "$filter": (
                f"{EARLIEST} and isRead eq false"
                " and from/emailAddress/address eq 'marie@example.com'"
            ),
            "$orderby": ORDER,
        }

    def test_its_quote_is_escaped(self) -> None:
        query = graph_mail_query("from:o'brien@example.com is:unread")

        assert query.params["$filter"].endswith("eq 'o''brien@example.com'")

    def test_without_a_condition_stays_a_search(self) -> None:
        assert graph_mail_query("from:marie@example.com").params == {
            "$search": '"from:marie@example.com"'
        }

    def test_beside_other_terms_stays_a_search(self) -> None:
        query = graph_mail_query("from:marie@example.com subject:budget is:unread")

        assert query.params == {"$search": '"from:marie@example.com subject:budget"'}


class TestTheSortProperty:
    def test_a_listing_sorted_on_another_date_filters_on_it(self) -> None:
        query = graph_mail_query("after:2026/10/01", sort_property="lastModifiedDateTime")

        assert query.params == {
            "$filter": "lastModifiedDateTime ge 2026-10-01T00:00:00Z",
            "$orderby": "lastModifiedDateTime desc",
        }

    def test_its_page_checks_read_the_same_date(self) -> None:
        query = graph_mail_query("to:marie after:2026/10/01", sort_property="lastModifiedDateTime")

        kept, _ = query.screen(
            [
                {
                    "lastModifiedDateTime": "2026-10-02T08:00:00Z",
                    "receivedDateTime": "2026-09-01T08:00:00Z",
                }
            ]
        )

        assert len(kept) == 1


class TestTheRestOfTheQuery:
    def test_defaults_to_the_inbox_folder(self) -> None:
        """Graph /me/messages spans every folder; Gmail and IMAP default to INBOX."""
        assert graph_mail_query("report").folder == "inbox"

    @pytest.mark.parametrize(
        ("text", "folder"),
        [
            ("in:sent", "sentitems"),
            ("in:trash", "deleteditems"),
            ("label:spam", "junkemail"),
            ("in:archive", "archive"),
            ("in:drafts", "drafts"),
        ],
    )
    def test_folder_operators_route_to_well_known_folders(self, text: str, folder: str) -> None:
        assert graph_mail_query(text).folder == folder

    def test_a_folder_alone_is_a_sorted_listing(self) -> None:
        assert graph_mail_query("in:sent").params == {"$orderby": ORDER}

    def test_an_empty_query_is_a_sorted_listing(self) -> None:
        assert graph_mail_query("").params == {"$orderby": ORDER}

    def test_people_and_words_become_kql_terms(self) -> None:
        query = graph_mail_query("from:john subject:meeting cc:anna to:paul quarterly report")

        assert query.params == {
            "$search": '"from:john subject:meeting cc:anna to:paul quarterly report"'
        }

    def test_a_quoted_operator_value_loses_its_quotes(self) -> None:
        assert graph_mail_query('subject:"meeting notes"').params == {
            "$search": '"subject:meeting notes"'
        }

    def test_a_negated_folder_never_leaks_into_kql(self) -> None:
        """Graph ``$search`` has no usable NOT; reading the inbox excludes the spam."""
        assert graph_mail_query("-in:spam report").params == {"$search": '"report"'}

    @pytest.mark.parametrize("text", ["after:yesterday", "report before:soon"])
    def test_a_date_that_cannot_be_read_is_refused(self, text: str) -> None:
        """Dropped, it would widen the answer in silence; refused, it says so."""
        with pytest.raises(ValueError, match="YYYY/MM/DD"):
            graph_mail_query(text)

    def test_an_iso_date_is_read_as_its_day(self) -> None:
        query = graph_mail_query("after:2026-10-01T09:30:00+02:00")

        assert query.params["$filter"] == "receivedDateTime ge 2026-10-01T00:00:00Z"

    def test_unix_seconds_name_an_instant(self) -> None:
        """Gmail's own documented form of a date operator."""
        query = graph_mail_query("after:1790000000")

        assert query.params["$filter"] == "receivedDateTime ge 2026-09-21T14:13:20Z"

    @pytest.mark.parametrize(
        ("text", "clause"),
        [("is:UNREAD", "isRead eq false"), ("has:Attachment", "hasAttachments eq true")],
    )
    def test_a_value_is_read_whatever_its_case(self, text: str, clause: str) -> None:
        assert graph_mail_query(text).params["$filter"].endswith(clause)


class TestStarred:
    """Gmail's star is Outlook's flag. ``label:STARRED`` — what the catalogue
    tells the planner to write — used to be read as a folder Graph does not
    have, and the inbox was listed whole as « starred »."""

    @pytest.mark.parametrize("text", ["label:STARRED", "is:starred"])
    def test_the_flag_is_checked_on_the_page(self, text: str) -> None:
        query = graph_mail_query(text)

        kept, set_aside = query.screen(
            [
                _message(id="flagged", flag={"flagStatus": "flagged"}),
                _message(id="done", flag={"flagStatus": "complete"}),
                _message(id="plain"),
            ]
        )

        assert query.folder == "inbox"
        assert [message["id"] for message in kept] == ["flagged"]
        assert set_aside == 2

    def test_beside_a_search_it_is_checked_too(self) -> None:
        query = graph_mail_query("from:Marie is:starred")

        assert query.params == {"$search": '"from:Marie"'}
        assert query.screen([_message()]) == ([], 1)


class TestCcOperator:
    """`cc:` is a KQL search term, not leftover free text.

    Microsoft's `$search` honours `cc:` natively; leaving it in the remaining
    text made it a bare keyword — matching the address anywhere in the message
    instead of the copy line.
    """

    def test_cc_becomes_a_search_term(self) -> None:
        query = graph_mail_query("in:sent cc:alice@example.com")

        assert query.params == {"$search": '"cc:alice@example.com"'}
        assert query.folder == "sentitems"


class TestANegation:
    """A negated operator used to be STRIPPED: « my mails, not the newsletter »
    listed the newsletter too (2026-10-13). A negation now holds — on the
    server when Graph documents its clause, on the page otherwise, the count
    set aside stated (``set_aside_on_page``)."""

    @pytest.mark.parametrize(
        ("text", "clause"),
        [
            ("-is:unread", "isRead eq true"),
            ("-is:read", "isRead eq false"),
            ("-has:attachment", "hasAttachments eq false"),
        ],
    )
    def test_a_state_is_the_server_s_opposite_clause(self, text: str, clause: str) -> None:
        assert graph_mail_query(text).params == {
            "$filter": f"{EARLIEST} and {clause}",
            "$orderby": ORDER,
        }

    @pytest.mark.parametrize(
        ("text", "clause"),
        [
            ("-after:2026/10/01", "receivedDateTime lt 2026-10-01T00:00:00Z"),
            ("-before:2026/10/01", "receivedDateTime ge 2026-10-01T00:00:00Z"),
        ],
    )
    def test_a_date_is_the_other_side_of_its_day(self, text: str, clause: str) -> None:
        assert graph_mail_query(text).params["$filter"] == clause

    @pytest.mark.parametrize(
        ("text", "kept", "set_aside"),
        [
            ("-from:news@shop.example", "bob@example.com", "news@shop.example"),
            ("report -from:shop", "bob@example.com", "news@shop.example"),
        ],
    )
    def test_a_sender_is_set_aside_on_the_page(self, text: str, kept: str, set_aside: str) -> None:
        query = graph_mail_query(text)

        assert "shop" not in str(query.params)
        messages = [
            _message(**{"from": {"emailAddress": {"name": "Bob", "address": kept}}}),
            _message(**{"from": {"emailAddress": {"name": "Shop", "address": set_aside}}}),
        ]
        assert query.screen(messages) == ([messages[0]], 1)

    def test_a_recipient_in_copy_is_set_aside_on_the_page(self) -> None:
        query = graph_mail_query("-cc:alice")
        copied = {"ccRecipients": [{"emailAddress": {"name": "Alice", "address": "a@x.org"}}]}

        assert query.screen([_message(), _message(**copied)]) == ([_message()], 1)

    def test_a_subject_is_set_aside_on_the_page_whatever_its_case(self) -> None:
        query = graph_mail_query("-subject:promo")
        promo = _message(subject="Big PROMO today")

        assert query.screen([_message(subject="Invoice"), promo]) == (
            [_message(subject="Invoice")],
            1,
        )

    def test_the_star_is_the_flag_left_unset(self) -> None:
        flagged = _message(flag={"flagStatus": "flagged"})

        assert graph_mail_query("-label:starred").screen([_message(), flagged]) == (
            [_message()],
            1,
        )

    def test_another_folder_is_excluded_by_reading_one(self) -> None:
        query = graph_mail_query("in:inbox -in:sent")

        assert query.folder == "inbox"
        assert query.excludes_its_folder is False

    @pytest.mark.parametrize(
        "text", ["-in:inbox", "in:trash -in:Trash", "label:Factures -label:factures"]
    )
    def test_excluding_the_folder_read_is_said(self, text: str) -> None:
        assert graph_mail_query(text).excludes_its_folder is True

    def test_a_hyphenated_word_is_never_a_negation(self) -> None:
        assert graph_mail_query("reply-to:bob").params == {"$search": '"reply-to:bob"'}
