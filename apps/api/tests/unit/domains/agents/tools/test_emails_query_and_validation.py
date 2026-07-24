"""Unit tests for the pure query/validation helpers of ``emails_tools``.

These four helpers decide *what the user gets* and *what leaves the mailbox*,
and none of them raise on a wrong outcome — a defect here is silent:

- ``normalize_gmail_query`` rewrites every Gmail search. It decides the SCOPE
  (received vs sent vs inbox) and whether **trashed** mail is included. A
  regression silently changes the result set.
- ``_extract_email_from_address`` / ``_validate_email_addresses`` /
  ``_validate_send_email_inputs`` gate outbound mail. A regression sends to the
  wrong address or lets a malformed recipient through.

All are pure (no connector, no network), so they are exercised directly.
Date-sensitive assertions pass ``default_days_back=0`` to switch the default
``after:`` window off and keep the expected query deterministic.
"""

from __future__ import annotations

import pytest

from src.domains.agents.tools.emails_tools import (
    _extract_email_from_address,
    _validate_email_addresses,
    _validate_send_email_inputs,
    normalize_gmail_query,
)
from src.domains.agents.tools.exceptions import EmailValidationError

pytestmark = pytest.mark.unit


# ============================================================================
# normalize_gmail_query — scope (received / sent / inbox)
# ============================================================================


class TestNormalizeGmailQueryScope:
    def test_plain_query_defaults_to_received_scope(self) -> None:
        """No scope operator → exclude sent and drafts (user asked for mail
        they RECEIVED)."""
        result = normalize_gmail_query("from:john", default_days_back=0)
        assert "-in:sent" in result
        assert "-in:draft" in result

    def test_existing_in_operator_preserves_scope(self) -> None:
        """An explicit in:/label: scope must never be overridden."""
        result = normalize_gmail_query("from:john in:inbox", default_days_back=0)
        assert "-in:sent" not in result
        assert "in:inbox" in result

    def test_existing_label_operator_preserves_scope(self) -> None:
        result = normalize_gmail_query("label:starred", default_days_back=0)
        assert "-in:sent" not in result

    @pytest.mark.parametrize(
        ("raw", "expected_fragment"),
        [
            ("inbox", "-in:sent"),  # LLM mistake for "latest emails"
            ("received", "-in:sent"),
            ("sent", "in:sent"),
        ],
    )
    def test_llm_error_normalizations(self, raw: str, expected_fragment: str) -> None:
        """Whole-query search terms the LLM emits instead of operators."""
        assert expected_fragment in normalize_gmail_query(raw, default_days_back=0)

    def test_sent_normalization_does_not_exclude_sent(self) -> None:
        """'sent' → in:sent, and the received-scope default must NOT also fire."""
        result = normalize_gmail_query("sent", default_days_back=0)
        assert "in:sent" in result
        assert "-in:sent" not in result

    def test_empty_query_gets_received_scope(self) -> None:
        result = normalize_gmail_query("", default_days_back=0)
        assert "-in:sent" in result and "-in:draft" in result


# ============================================================================
# normalize_gmail_query — TRASH exclusion (silent data-exposure surface)
# ============================================================================


class TestNormalizeGmailQueryTrash:
    def test_trash_is_excluded_by_default(self) -> None:
        assert "-in:trash" in normalize_gmail_query("from:john", default_days_back=0)

    @pytest.mark.parametrize("operator_query", ["in:trash", "label:trash", "label:TRASH"])
    def test_explicit_trash_operator_is_honoured(self, operator_query: str) -> None:
        """The operator form is what the tool teaches the LLM to emit for
        "corbeille"/"trash"/"deleted" — it must keep trash in scope."""
        result = normalize_gmail_query(operator_query, default_days_back=0)
        assert "-in:trash" not in result

    @pytest.mark.parametrize(
        "content_query",
        [
            "deleted invoices",
            "subject:trash collection",
            "from:john deleted files",
            "subject:deleted",
        ],
    )
    def test_content_words_do_not_disable_trash_exclusion(self, content_query: str) -> None:
        """Regression: a CONTENT word ('deleted', 'trash') inside a legitimate
        search must not silently pull trashed mail into the results.

        Before the fix, GMAIL_TRASH_KEYWORDS matched these bare words as
        substrings, so ``-in:trash`` was dropped and deleted messages surfaced
        as if they were live mail — with no error anywhere.
        """
        assert "-in:trash" in normalize_gmail_query(content_query, default_days_back=0)

    @pytest.mark.parametrize("bare", ["trash", "deleted"])
    def test_bare_trash_word_as_whole_query_maps_to_operator(self, bare: str) -> None:
        """A whole-query 'trash'/'deleted' is the natural-language ask for the
        trash folder — normalized to the operator (same pattern as 'sent')."""
        result = normalize_gmail_query(bare, default_days_back=0)
        assert "in:trash" in result
        assert "-in:trash" not in result


# ============================================================================
# normalize_gmail_query — quotes & default date window
# ============================================================================


class TestNormalizeGmailQueryQuotesAndDate:
    def test_enclosing_quotes_are_stripped(self) -> None:
        assert normalize_gmail_query('"from:john"', default_days_back=0).startswith("from:john")

    def test_inner_phrase_quotes_are_preserved(self) -> None:
        """Gmail phrase syntax (subject:"exact phrase") must survive."""
        result = normalize_gmail_query('subject:"exact phrase"', default_days_back=0)
        assert 'subject:"exact phrase"' in result

    def test_default_date_window_is_added_when_absent(self) -> None:
        assert "after:" in normalize_gmail_query("from:john", default_days_back=90)

    @pytest.mark.parametrize(
        "dated_query",
        [
            "after:2026/01/01 from:x",
            "before:2026/01/01",
            "newer_than:7d",
            "older_than:7d",
        ],
    )
    def test_existing_date_operator_suppresses_default_window(self, dated_query: str) -> None:
        """Adding a second window on top of a user-specified one would silently
        narrow the search."""
        result = normalize_gmail_query(dated_query, default_days_back=90)
        assert "after:2" not in result.replace(dated_query, "")

    def test_zero_days_back_disables_default_window(self) -> None:
        assert "after:" not in normalize_gmail_query("from:john", default_days_back=0)


# ============================================================================
# _extract_email_from_address
# ============================================================================


class TestExtractEmailFromAddress:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("a@x.com", "a@x.com"),
            ("Jean Dupont <jean@x.com>", "jean@x.com"),
            ("<b@x.com>", "b@x.com"),
            ("  c@x.com  ", "c@x.com"),
            ("Nomé Accentué <e@x.com>", "e@x.com"),
        ],
    )
    def test_extraction(self, raw: str, expected: str) -> None:
        assert _extract_email_from_address(raw) == expected

    def test_unclosed_bracket_returns_input(self) -> None:
        """No closing '>' → nothing to extract; the caller's validation then
        rejects it rather than silently sending to a malformed address."""
        assert _extract_email_from_address("broken <a@x.com") == "broken <a@x.com"


# ============================================================================
# _validate_email_addresses / _validate_send_email_inputs
# ============================================================================


class TestValidateEmailAddresses:
    def test_valid_plain_list_passes(self) -> None:
        _validate_email_addresses("a@x.com, b@y.com", "to")

    def test_valid_rfc5322_list_passes(self) -> None:
        _validate_email_addresses("Jean <a@x.com>, Marie <b@y.com>", "to")

    def test_blank_entries_are_skipped(self) -> None:
        """A trailing comma must not be reported as an invalid address."""
        _validate_email_addresses("a@x.com, , b@y.com,", "to")

    @pytest.mark.parametrize("bad", ["not-an-email", "a@", "@x.com", "a@x.com, broken"])
    def test_invalid_address_raises(self, bad: str) -> None:
        with pytest.raises(EmailValidationError) as exc:
            _validate_email_addresses(bad, "to")
        assert exc.value.field == "to"


class TestValidateSendEmailInputs:
    def test_valid_inputs_pass(self) -> None:
        _validate_send_email_inputs(to="a@x.com", subject="Hi", body="Body")

    def test_missing_recipient_raises(self) -> None:
        with pytest.raises(EmailValidationError) as exc:
            _validate_send_email_inputs(to=None, subject="Hi", body="Body")
        assert exc.value.field == "to"

    def test_empty_recipient_raises(self) -> None:
        with pytest.raises(EmailValidationError):
            _validate_send_email_inputs(to="", subject="Hi", body="Body")

    @pytest.mark.parametrize(("subject", "body"), [(None, "Body"), ("Hi", None), ("", "Body")])
    def test_missing_subject_or_body_raises(self, subject: str | None, body: str | None) -> None:
        with pytest.raises(EmailValidationError):
            _validate_send_email_inputs(to="a@x.com", subject=subject, body=body)

    def test_invalid_cc_raises(self) -> None:
        with pytest.raises(EmailValidationError) as exc:
            _validate_send_email_inputs(to="a@x.com", subject="Hi", body="B", cc="bad")
        assert exc.value.field == "cc"

    def test_invalid_bcc_raises(self) -> None:
        with pytest.raises(EmailValidationError) as exc:
            _validate_send_email_inputs(to="a@x.com", subject="Hi", body="B", bcc="bad")
        assert exc.value.field == "bcc"

    def test_valid_cc_and_bcc_pass(self) -> None:
        _validate_send_email_inputs(
            to="a@x.com", subject="Hi", body="B", cc="c@x.com", bcc="Marie <d@x.com>"
        )
