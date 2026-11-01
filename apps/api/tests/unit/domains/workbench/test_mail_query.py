"""A mail listing as ONE Gmail-style query the three clients translate (ADR-369, F12).

The person's words pass as written — the Gmail-style syntax is the search
language of the screen, so ``from:alice`` means the sender on every provider —
then the chips, then the FOLDER, last: Graph and IMAP read the last folder a
query names, so the pane's folder stays the scope whatever the words say. A
Gmail label of the person's own is read by its id (``labelIds``, documented),
never by a ``label:`` term Gmail is not known to read ids in. A day is the
person's: Gmail reads ``after:YYYY/MM/DD`` at Pacific midnight, so it is given
the instant itself. What a provider cannot carry is refused before anything
is sent — never dropped in silence.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.core.constants import WORKBENCH_MAIL_QUERY_MAX_CHARS
from src.core.exceptions import BaseAPIException
from src.domains.connectors.models import ConnectorType
from src.domains.workbench.mail_query import MailSearch, compose_query
from src.domains.workbench.schemas.mail import MailListing

pytestmark = pytest.mark.unit

GMAIL, OUTLOOK, ICLOUD = (
    ConnectorType.GOOGLE_GMAIL,
    ConnectorType.MICROSOFT_OUTLOOK,
    ConnectorType.APPLE_EMAIL,
)
PARIS = ZoneInfo("Europe/Paris")


def _search(provider: ConnectorType, **listing: object) -> MailSearch:
    return compose_query(provider, MailListing.model_validate(listing), PARIS)


def _query(provider: ConnectorType, **listing: object) -> str:
    search = _search(provider, **listing)
    assert search.label_ids == ()
    return search.query


def _refusal(provider: ConnectorType, **listing: object) -> object:
    with pytest.raises(BaseAPIException) as refused:
        _search(provider, **listing)
    return refused.value.detail


class TestTheChips:
    def test_they_compose_before_the_folder(self) -> None:
        query = _query(
            OUTLOOK,
            folder="system:inbox",
            unread=True,
            attachments=True,
            after="2026-10-01",
            before="2026-10-08",
        )
        assert query == "is:unread has:attachment after:2026/10/01 before:2026/10/08 in:inbox"

    def test_gmail_is_given_the_person_s_midnight_itself(self) -> None:
        query = _query(GMAIL, after="2026-10-01", before="2026-10-08")
        start = int(datetime(2026, 10, 1, tzinfo=PARIS).timestamp())
        end = int(datetime(2026, 10, 8, tzinfo=PARIS).timestamp())
        assert query == f"after:{start} before:{end} in:inbox"

    def test_the_attachments_chip_is_refused_where_the_query_cannot_carry_it(self) -> None:
        """IMAP has no criterion for it: the translator would drop it in silence."""
        assert _refusal(ICLOUD, attachments=True) == {"code": "not_supported_by_provider"}


class TestTheFolder:
    @pytest.mark.parametrize(
        ("folder", "operator"),
        [
            ("system:inbox", "in:inbox"),
            ("system:starred", "is:starred"),
            ("system:sent", "in:sent"),
            ("system:drafts", "in:drafts"),
            ("system:archive", "in:archive"),
            ("system:spam", "in:spam"),
            ("system:trash", "in:trash"),
        ],
    )
    def test_a_system_place_is_its_role(self, folder: str, operator: str) -> None:
        assert _query(OUTLOOK, folder=folder) == operator

    def test_a_place_the_provider_does_not_have_is_refused(self) -> None:
        assert _refusal(GMAIL, folder="system:archive") == {"code": "not_supported_by_provider"}

    def test_a_gmail_label_is_read_by_its_id(self) -> None:
        search = _search(GMAIL, folder="Label_12", unread=True)
        assert (search.query, search.label_ids) == ("is:unread", ("Label_12",))

    def test_a_folder_elsewhere_is_named_between_quotes_when_it_has_spaces(self) -> None:
        assert _query(ICLOUD, folder="Old mail") == 'label:"Old mail"'
        assert _query(OUTLOOK, folder="Projets") == "label:Projets"

    def test_a_name_the_language_cannot_carry_is_refused(self) -> None:
        assert _refusal(OUTLOOK, folder='Say "hi"') == {"code": "invalid_request"}


class TestThePersonsWords:
    def test_they_pass_as_written_and_the_folder_stays_the_scope(self) -> None:
        query = _query(OUTLOOK, folder="system:sent", q='from:alice "annual report"')
        assert query == 'from:alice "annual report" in:sent'

    def test_blank_words_add_nothing(self) -> None:
        assert _query(GMAIL, q="   ") == "in:inbox"


class TestTheListing:
    def test_a_range_ends_after_it_starts(self) -> None:
        with pytest.raises(ValueError):
            MailListing(after=date(2026, 10, 8), before=date(2026, 10, 1))

    def test_words_are_bounded_and_read_before_they_are_sent(self) -> None:
        with pytest.raises(ValueError):
            MailListing(q="x" * (WORKBENCH_MAIL_QUERY_MAX_CHARS + 1))
        with pytest.raises(ValueError):
            MailListing(q="a\nb")
