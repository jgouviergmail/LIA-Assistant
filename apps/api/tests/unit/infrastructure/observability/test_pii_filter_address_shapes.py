"""Every shape an address takes in a log line is withheld above DEBUG (2026-10-25).

The filter pseudonymised the address it recognised — a well-formed ASCII address,
in a string or a list of strings — and let every other shape through, measured on
the filter itself:

* a full address inside a tuple, a set, or a list of lists or of tuples: the
  dict sanitiser kept those containers as they were;
* a masked address (``fir***@mail.test``, ``f…@m….test``): the unverified-account
  sweep logged three characters and the whole domain of every account it deleted,
  at INFO, and nothing stopped it;
* an address outside ASCII: ``zoë@mail.test`` and ``contact@café.fr`` went through
  whole, ``andré.martin@exemple.fr`` kept its first name;
* a field named for an address beyond four exact names (``recipient_email``,
  ``sample_emails``) had no rule of its own.

A fact under such a name — a count, a flag, an absence, a message id — stays.
"""

from __future__ import annotations

import pytest

from src.infrastructure.observability.pii_filter import add_pii_filter, sanitize_string
from tests.support.cpu_growth import CEILING_SECONDS, measure_growth

pytestmark = pytest.mark.unit

ADDRESS = "first.signup@mail.test"


def _logged(**fields: object) -> dict[str, object]:
    """What an INFO line keeps of ``fields``."""
    record = add_pii_filter(None, "info", {"event": "probe", **fields})
    record.pop("event")
    return record


@pytest.mark.parametrize(
    "value",
    [
        (ADDRESS,),
        {ADDRESS},
        frozenset({ADDRESS}),
        [(ADDRESS, 1)],
        [[ADDRESS]],
        ({"contact": ADDRESS},),
    ],
    ids=["tuple", "set", "frozenset", "list of tuples", "list of lists", "dict in a tuple"],
)
def test_an_address_in_any_container_is_pseudonymized(value: object) -> None:
    logged = repr(_logged(addressees=value))

    assert "@" not in logged and "first.signup" not in logged
    assert "email_hash_" in logged


@pytest.mark.parametrize(
    "masked",
    ["fir***@mail.test", "f…@m….test", "f•••@mail.test", "fi***@ma***.test", "***@mail.test"],
)
def test_a_masked_address_is_pseudonymized(masked: str) -> None:
    logged = repr(_logged(contact=masked, detail=f"notified {masked} of the change"))

    assert "@" not in logged and ".test" not in logged
    assert "notified email_hash_" in logged


@pytest.mark.parametrize(
    ("address", "fragment"),
    [
        ("zoë@mail.test", "zoë"),
        ("contact@café.fr", "café"),
        ("andré.martin@exemple.fr", "andré"),
        ("用户@例子.中国", "用户"),
    ],
)
def test_an_address_outside_ascii_is_pseudonymized_whole(address: str, fragment: str) -> None:
    logged = sanitize_string(f"sent to {address}", redact_content=True)

    assert "@" not in logged and fragment not in logged
    assert logged.startswith("sent to email_hash_")


@pytest.mark.parametrize(
    "fields",
    [
        {"recipient_email": "first.signup"},
        {"sample_emails": ["first.signup", "second.signup"]},
        {"emails": ("first.signup",)},
        {"owner_email_address": "first signup at mail dot test"},
    ],
)
def test_a_field_named_for_an_address_withholds_its_text(fields: dict[str, object]) -> None:
    logged = repr(_logged(**fields))

    assert "first" not in logged and "signup" not in logged
    assert "email_hash_" in logged


@pytest.mark.parametrize(
    "fields",
    [
        {"emails_count": 3},
        {"total_emails": 4},
        {"has_email": True},
        {"recipient_email": None},
        {"email_id": "18c2f0a9b7d3e1f4"},
        {"email_ids": ["18c2f0a9b7d3e1f4"]},
        {"emails_sent": 2},
    ],
)
def test_a_fact_under_an_address_name_stays_readable(fields: dict[str, object]) -> None:
    assert _logged(**fields) == fields


@pytest.mark.parametrize(
    "text", ["@property", "user@host", "react@18.3.1", "3 @ 4.50 each", "icon@2x"]
)
def test_text_that_is_no_address_is_left_alone(text: str) -> None:
    assert sanitize_string(text, redact_content=True) == text


@pytest.mark.parametrize(
    "unit",
    ["a*b.c+d-", "a@", "ab.cd@" + "e." * 3, "é•…*"],
    ids=["local-part run", "at signs", "dotted domains", "marks"],
)
def test_the_address_pattern_stays_linear_on_hostile_input(unit: str) -> None:
    """ADR-326: every string of every log line goes through it."""
    small = unit * (40_000 // len(unit))

    growth = measure_growth(
        lambda text: sanitize_string(text, redact_content=True), small, small * 4
    )

    assert growth.elapsed < CEILING_SECONDS, growth.describe()
    assert growth.linear, growth.describe()
