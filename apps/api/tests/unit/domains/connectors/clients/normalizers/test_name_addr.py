"""One readable mailbox form, whichever provider handed the parts (ADR-287 amendment).

Outlook's normaliser built the sender with ``email.utils.formataddr``, which
RFC 2047-encodes every non-ASCII display name: « Jérôme Dupont » reached the
model, the card and the reference matcher as ``=?utf-8?b?…?=``. The IMAP
normaliser read ``imap_tools``' ``from_``, which is the bare address: the name
never reached anyone. Both now go through :func:`name_addr`.
"""

from __future__ import annotations

import pytest

from src.infrastructure.email.recipients import name_addr, read_recipients

pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize(
    ("name", "address", "expected"),
    [
        ("Jérôme Dupont", "jd@example.com", "Jérôme Dupont <jd@example.com>"),
        ("李雷", "li@example.cn", "李雷 <li@example.cn>"),
        ("Dupont, Jérôme", "jd@example.com", '"Dupont, Jérôme" <jd@example.com>'),
        ("=?utf-8?b?SsOpcsO0bWUgRHVwb250?=", "jd@example.com", "Jérôme Dupont <jd@example.com>"),
        ("", "jd@example.com", "jd@example.com"),
        (None, "jd@example.com", "jd@example.com"),
        ("jd@example.com", "jd@example.com", "jd@example.com"),
        ("  Alice   Martin ", " alice@example.com ", "Alice Martin <alice@example.com>"),
    ],
)
def test_the_mailbox_reads_as_a_person_writes_it(
    name: str | None, address: str, expected: str
) -> None:
    assert name_addr(name, address) == expected


def test_an_address_it_cannot_read_is_kept_as_the_provider_gave_it() -> None:
    # A display form must never DROP the only part a reply can use.
    assert name_addr("Alice", "not an address") == "not an address"


def test_no_address_keeps_the_name_alone() -> None:
    assert name_addr("Alice", "") == "Alice"
    assert name_addr("", None) == ""


def test_a_line_break_in_a_name_never_reaches_the_header() -> None:
    value = name_addr("Eve\r\nBcc: spy@example.net", "eve@example.com")

    assert "\r" not in value and "\n" not in value
    assert read_recipients(value) == [("Eve Bcc: spy@example.net", "eve@example.com")]


@pytest.mark.parametrize(
    ("name", "address"),
    [
        ("Dupont, Jérôme", "jd@example.com"),
        ("Jérôme G", "jg@example.com"),
        ("李雷", "li@example.cn"),
    ],
)
def test_the_form_reads_back_as_one_recipient(name: str, address: str) -> None:
    assert read_recipients(name_addr(name, address)) == [(name, address)]
