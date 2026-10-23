"""Unit tests for the e-mail body extraction the finishing step relies on.

``tools/formatters.py`` reads an e-mail message's body for
``agents/emails/message_finishing.py``. Nothing downstream re-checks it: a wrong
extraction becomes a wrong ANSWER, delivered confidently, with no error anywhere
in the logs. The body sits in a different place per provider — Gmail's MIME tree,
or the top-level text the Apple and Microsoft normalisers hand over — which is
exactly where provider asymmetries hide.
"""

import pytest

from src.domains.agents.tools.formatters import GmailFormatter

pytestmark = pytest.mark.unit


class TestGmailBodyExtraction:
    """Body location differs per provider; the extractor hides that."""

    def test_top_level_body_is_used_as_is_for_apple(self) -> None:
        message = {"_provider": "apple", "body": "Plain text body"}
        assert GmailFormatter._extract_body(message) == "Plain text body"

    def test_top_level_body_is_returned_as_is_whatever_the_provider(self) -> None:
        """Every provider hands TEXT at its client boundary (ADR-287); the
        formatter no longer converts a Graph body late."""
        message = {"_provider": "microsoft", "body": "Hello world"}
        assert GmailFormatter._extract_body(message) == "Hello world"

    def test_message_without_body_or_payload_yields_empty(self) -> None:
        assert GmailFormatter._extract_body({}) == ""
