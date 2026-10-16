"""Gmail's address headers refuse what they cannot read.

Python's address parser answers ``('', '')`` for an address it cannot read
(strict since 3.13), and the encoder skipped empty addresses: ``marie@`` became
an empty ``To`` and ``a@b.com, marie@`` lost its second recipient in silence —
on a send and on a draft alike (found while building the mailbox drafts,
ADR-344).
"""

from __future__ import annotations

import pytest

from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("addresses", ["marie@", "a@b.com, marie@", '"Marie" <>'])
def test_an_address_that_cannot_be_read_is_refused(addresses: str) -> None:
    with pytest.raises(ValueError):
        GoogleGmailClient._encode_email_header(addresses)


def test_a_display_name_outside_ascii_is_encoded() -> None:
    assert GoogleGmailClient._encode_email_header(
        '"Élodie Exemple" <elodie@example.com>, bob@example.com'
    ) == ("=?utf-8?q?=C3=89lodie_Exemple?= <elodie@example.com>, bob@example.com")
