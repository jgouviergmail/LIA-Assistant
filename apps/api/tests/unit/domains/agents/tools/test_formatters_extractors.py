"""Unit tests for the field extractors that shape what the LLM reads.

``tools/formatters.py`` is the last hop between a provider payload (Google
People, Gmail, and the Apple/Microsoft normalisers that mimic them) and the
text handed to the model. Nothing downstream re-checks these values: a wrong
extraction becomes a wrong ANSWER, delivered confidently, with no error
anywhere in the logs.

Two areas get the most attention:

- **Localisation** — the date/sender/subject fallbacks are user-visible in six
  languages, and Chinese is the trap (backend canonical is ``zh-CN``).
- **Provider awareness** — the same extractor serves Gmail, Apple and
  Microsoft payloads, which is exactly where provider asymmetries hide.
"""

from typing import Any

import pytest

from src.domains.agents.tools.formatters import (
    ContactsFormatter,
    GmailFormatter,
    format_google_birthday,
    format_google_datetime,
    format_google_time_only,
)

pytestmark = pytest.mark.unit


# 2023-11-14T22:13:20Z — a fixed instant, so the timezone conversions are exact.
TIMESTAMP_MS = 1700000000000


def _message(**payload: Any) -> dict[str, Any]:
    """Gmail-shaped message with the headers under ``payload.headers``."""
    headers = payload.pop("headers", {})
    message: dict[str, Any] = {
        "payload": {"headers": [{"name": k, "value": v} for k, v in headers.items()]}
    }
    message.update(payload)
    return message


# ============================================================================
# CONTACTS EXTRACTORS
# ============================================================================


class TestContactsExtractors:
    """Google People API person → the fields the contact tools expose."""

    PERSON = {
        "names": [{"displayName": "Jane Doe", "givenName": "Jane"}],
        "emailAddresses": [
            {"value": "jane@work.com", "type": "work"},
            {"value": "", "type": "home"},
            {"type": "other"},
        ],
        "phoneNumbers": [{"value": "+33612345678", "type": "mobile"}, {"value": ""}],
        "organizations": [{"name": "ACME", "title": "CTO"}],
        "addresses": [
            {"formattedValue": "1 rue de la Paix\r\n\r\n  75002 Paris  \r\n", "type": "home"},
            {"formattedValue": "", "type": "work"},
        ],
    }

    def test_name_extraction(self) -> None:
        assert ContactsFormatter._extract_name(self.PERSON) == "Jane Doe"

    def test_missing_name_falls_back_to_a_localised_label(self) -> None:
        assert ContactsFormatter._extract_name({}) != ""

    def test_emails_without_a_value_are_dropped(self) -> None:
        emails = ContactsFormatter._extract_emails(self.PERSON)
        assert emails == [{"value": "jane@work.com", "type": "work"}]

    def test_phones_without_a_value_are_dropped(self) -> None:
        phones = ContactsFormatter._extract_phones(self.PERSON)
        assert phones == [{"value": "+33612345678", "type": "mobile"}]

    def test_addresses_are_normalised_to_clean_lines(self) -> None:
        """CRLF, blank lines and padding come straight from the provider."""
        addresses = ContactsFormatter._extract_addresses(self.PERSON)
        assert addresses == [{"formatted": "1 rue de la Paix\n75002 Paris", "type": "home"}]

    def test_organizations_expose_name_title_and_department(self) -> None:
        orgs = ContactsFormatter._extract_organizations(self.PERSON)
        assert orgs == [{"name": "ACME", "title": "CTO", "department": ""}]

    def test_empty_person_yields_empty_collections(self) -> None:
        assert ContactsFormatter._extract_emails({}) == []
        assert ContactsFormatter._extract_phones({}) == []
        assert ContactsFormatter._extract_addresses({}) == []
        assert ContactsFormatter._extract_organizations({}) == []

    def test_birthday_is_formatted_without_weekday_or_time(self) -> None:
        birthdays = ContactsFormatter._extract_birthdays(
            {"birthdays": [{"date": {"year": 1975, "month": 11, "day": 3}}]}
        )
        assert len(birthdays) == 1
        assert "1975" in birthdays[0]
        assert ":" not in birthdays[0]

    def test_birthday_entry_without_a_date_is_skipped(self) -> None:
        assert ContactsFormatter._extract_birthdays({"birthdays": [{}]}) == []


# ============================================================================
# DATE / TIME FORMATTING
# ============================================================================


class TestFormatGoogleDatetime:
    """Gmail ``internalDate`` (epoch ms) → a localized, timezone-aware string."""

    def test_converts_to_the_user_timezone(self) -> None:
        paris = format_google_datetime(TIMESTAMP_MS, "Europe/Paris", "fr-FR")
        utc = format_google_datetime(TIMESTAMP_MS, "UTC", "fr-FR")
        assert paris != utc
        assert "23:13" in paris
        assert "22:13" in utc

    @pytest.mark.parametrize(
        ("locale", "expected_fragment"),
        [
            ("fr-FR", "novembre"),
            ("en-US", "November"),
            ("de-DE", "November"),
            ("es-ES", "noviembre"),
            ("it-IT", "novembre"),
        ],
    )
    def test_month_names_are_localised(self, locale: str, expected_fragment: str) -> None:
        assert expected_fragment in format_google_datetime(TIMESTAMP_MS, "UTC", locale)

    def test_chinese_uses_its_own_date_structure(self) -> None:
        result = format_google_datetime(TIMESTAMP_MS, "UTC", "zh-CN")
        assert "年" in result and "月" in result and "日" in result

    def test_time_can_be_omitted(self) -> None:
        assert ":" not in format_google_datetime(TIMESTAMP_MS, "UTC", "fr-FR", include_time=False)

    def test_iso_string_input_is_accepted(self) -> None:
        assert "2026" in format_google_datetime("2026-07-20T09:00:00Z", "UTC", "fr-FR")

    def test_millisecond_string_input_is_accepted(self) -> None:
        assert format_google_datetime(str(TIMESTAMP_MS), "UTC", "fr-FR") == (
            format_google_datetime(TIMESTAMP_MS, "UTC", "fr-FR")
        )

    def test_missing_timestamp_returns_a_localised_placeholder(self) -> None:
        assert format_google_datetime(None, "UTC", "fr-FR") != ""

    def test_invalid_timezone_returns_a_localised_placeholder(self) -> None:
        """An unknown IANA zone must not escape as ZoneInfoNotFoundError."""
        assert format_google_datetime(TIMESTAMP_MS, "Mars/Olympus", "fr-FR") != ""

    def test_unsupported_locale_falls_back_to_the_default_language(self) -> None:
        """Locale normalisation goes through the single chokepoint, so an
        unsupported locale resolves to the configured default rather than to a
        bare two-letter code no i18n table knows about."""
        from src.core.i18n import normalize_language

        expected = format_google_datetime(None, "UTC", normalize_language("pt-BR"))
        assert format_google_datetime(None, "UTC", "pt-BR") == expected


class TestFormatGoogleTimeOnly:
    def test_returns_hours_and_minutes_in_the_user_timezone(self) -> None:
        assert format_google_time_only(TIMESTAMP_MS, "Europe/Paris") == "23:13"

    def test_iso_string_input(self) -> None:
        assert format_google_time_only("2026-07-20T09:30:00Z", "UTC") == "09:30"

    @pytest.mark.parametrize("value", [None, 0, ""])
    def test_missing_timestamp_renders_the_placeholder(self, value: Any) -> None:
        assert format_google_time_only(value, "UTC") == "--:--"

    def test_invalid_timezone_renders_the_placeholder(self) -> None:
        assert format_google_time_only(TIMESTAMP_MS, "Mars/Olympus") == "--:--"


class TestFormatGoogleBirthday:
    def test_full_date_is_formatted_without_weekday(self) -> None:
        result = format_google_birthday(1975, 11, 3, "fr-FR")
        assert "1975" in result
        assert "novembre" in result

    def test_year_less_birthday_omits_the_year(self) -> None:
        result = format_google_birthday(None, 11, 3, "fr-FR")
        assert "novembre" in result
        assert "1975" not in result

    def test_incomplete_birthday_degrades_gracefully(self) -> None:
        assert isinstance(format_google_birthday(None, None, None, "fr-FR"), str)


# ============================================================================
# GMAIL EXTRACTORS
# ============================================================================


class TestGmailHeaderExtractors:
    """Header access is case-insensitive; every provider spells them its way."""

    MESSAGE = _message(
        headers={
            "From": '"Bob Smith" <bob@example.com>',
            "To": "jane@example.com, carol@example.com",
            "Cc": "dave@example.com",
            "Subject": "Quarterly report",
        },
        internalDate=str(TIMESTAMP_MS),
        snippet="Here is the &#39;report&#39;",
        labelIds=["INBOX", "UNREAD"],
        id="abc123",
    )

    def test_headers_are_lowercased_into_a_dict(self) -> None:
        headers = GmailFormatter._extract_headers_dict(self.MESSAGE)
        assert headers["from"] == '"Bob Smith" <bob@example.com>'
        assert headers["subject"] == "Quarterly report"

    def test_header_without_a_value_is_skipped(self) -> None:
        message = _message(headers={"From": ""})
        assert "from" not in GmailFormatter._extract_headers_dict(message)

    def test_sender_full_header_is_returned_as_is(self) -> None:
        assert GmailFormatter._extract_from(self.MESSAGE) == '"Bob Smith" <bob@example.com>'

    def test_sender_email_is_parsed_out_of_the_display_name_form(self) -> None:
        assert GmailFormatter._extract_from_email(self.MESSAGE) == "bob@example.com"

    def test_bare_sender_email_is_returned_unchanged(self) -> None:
        message = _message(headers={"From": "bob@example.com"})
        assert GmailFormatter._extract_from_email(message) == "bob@example.com"

    def test_recipients_are_split_on_commas(self) -> None:
        assert GmailFormatter._extract_to(self.MESSAGE) == [
            "jane@example.com",
            "carol@example.com",
        ]
        assert GmailFormatter._extract_cc(self.MESSAGE) == ["dave@example.com"]

    def test_absent_recipients_yield_empty_lists(self) -> None:
        assert GmailFormatter._extract_to(_message()) == []
        assert GmailFormatter._extract_cc(_message()) == []

    def test_missing_sender_and_subject_fall_back_to_localised_labels(self) -> None:
        empty = _message()
        assert GmailFormatter._extract_from(empty, "fr-FR") != ""
        assert GmailFormatter._extract_subject(empty, "fr-FR") != ""

    def test_fallback_labels_differ_between_languages(self) -> None:
        empty = _message()
        assert GmailFormatter._extract_subject(empty, "fr-FR") != (
            GmailFormatter._extract_subject(empty, "en-US")
        )

    def test_chinese_fallback_uses_the_backend_canonical_table(self) -> None:
        """``zh`` and ``zh-CN`` must resolve to the SAME i18n entry."""
        empty = _message()
        assert GmailFormatter._extract_subject(empty, "zh-CN") == (
            GmailFormatter._extract_subject(empty, "zh")
        )

    def test_snippet_entities_are_decoded_and_capped(self) -> None:
        assert GmailFormatter._extract_snippet(self.MESSAGE) == "Here is the 'report'"

        long_message = _message(snippet="x" * 500)
        snippet = GmailFormatter._extract_snippet(long_message)
        assert len(snippet) == 200
        assert snippet.endswith("...")

    def test_unread_flag_reads_the_label_list(self) -> None:
        assert GmailFormatter._extract_is_unread(self.MESSAGE) is True
        assert GmailFormatter._extract_is_unread(_message(labelIds=["INBOX"])) is False

    def test_date_extraction_delegates_to_the_localised_formatter(self) -> None:
        formatted = GmailFormatter._extract_date(self.MESSAGE, "UTC", "fr-FR")
        assert "novembre" in formatted


class TestGmailWebUrl:
    """The "open in webmail" link is provider-specific."""

    def test_gmail_message_gets_a_gmail_url(self) -> None:
        url = GmailFormatter._extract_email_web_url({"id": "abc123"})
        assert url == "https://mail.google.com/mail/u/0/#all/abc123"

    def test_apple_message_has_no_web_url(self) -> None:
        assert GmailFormatter._extract_email_web_url({"id": "1", "_provider": "apple"}) == ""

    def test_microsoft_message_uses_the_graph_web_link(self) -> None:
        url = GmailFormatter._extract_email_web_url(
            {"id": "1", "_provider": "microsoft", "webLink": "https://outlook.office.com/x"}
        )
        assert url == "https://outlook.office.com/x"

    def test_message_without_id_has_no_url(self) -> None:
        assert GmailFormatter._extract_email_web_url({}) == ""


class TestGmailBodyExtraction:
    """Body location differs per provider; the extractor hides that."""

    def test_top_level_body_is_used_as_is_for_apple(self) -> None:
        message = {"_provider": "apple", "body": "Plain text body"}
        assert GmailFormatter._extract_body(message) == "Plain text body"

    def test_microsoft_html_body_is_flattened(self) -> None:
        message = {"_provider": "microsoft", "body": "<p>Hello <b>world</b></p>"}
        text = GmailFormatter._extract_body(message)
        assert "<p>" not in text
        assert "Hello" in text

    def test_message_without_body_or_payload_yields_empty(self) -> None:
        assert GmailFormatter._extract_body({}) == ""

    def test_short_body_is_not_truncated(self) -> None:
        message = {"_provider": "apple", "body": "Short body", "id": "1"}
        assert GmailFormatter._extract_body_truncated(message) == "Short body"

    def test_long_body_is_truncated_with_a_continuation_marker(self) -> None:
        from src.core.config import settings

        body = "Sentence. " * (settings.emails_body_max_length // 5)
        message = {"_provider": "apple", "body": body, "id": "1"}

        truncated = GmailFormatter._extract_body_truncated(message, "fr-FR")

        assert len(truncated) < len(body)
        assert truncated != body

    def test_gmail_truncation_offers_a_link_to_the_full_message(self) -> None:
        from src.core.config import settings

        body = "Sentence. " * (settings.emails_body_max_length // 5)
        message = {"body": body, "id": "abc123"}

        truncated = GmailFormatter._extract_body_truncated(message, "fr-FR")

        assert "abc123" in truncated

    def test_entities_in_the_body_are_decoded(self) -> None:
        message = {"_provider": "apple", "body": "caf&eacute; &amp; th&eacute;", "id": "1"}
        assert GmailFormatter._extract_body_truncated(message) == "café & thé"

    def test_empty_body_stays_empty(self) -> None:
        assert GmailFormatter._extract_body_truncated({"_provider": "apple", "body": ""}) == ""
