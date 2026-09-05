"""How a register row becomes bytes, and why it must never change (ADR-263, lot 5).

This is the foundation of the whole chain: if two different rows can produce
one digest, the chain is forgeable; if one row can produce two digests across a
library upgrade, every chain in production turns red on a day nobody touched
the data.

The first draft of the design had BOTH defects, found by a cold review of my
own plan and demonstrated before a line was written:

    sha256("get_emails|ok|failed")  ==  sha256("get_emails|ok|failed")
    naive("get_emails", "ok|failed") == naive("get_emails|ok", "failed")  → True

    str(datetime) is variable-width:
    '2026-09-04 17:02:26+00:00'  vs  '2026-09-04 17:02:26.123456+00:00'

So the encoding is length-prefixed, typed, sorted, and VERSIONED. The frozen
vectors at the bottom are the part that matters most: they turn a library
upgrade into a red test here rather than a false tampering alarm in production.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.domains.agents.effects.chain_digest import (
    DIGEST_VERSION,
    canonical_bytes,
    row_digest,
)

pytestmark = [pytest.mark.unit]

_ID = uuid.UUID("11111111-2222-4333-8444-555555555555")
_WHEN = datetime(2026, 9, 4, 17, 2, 26, 123456, tzinfo=UTC)


class TestNoTwoContentsShareADigest:
    def test_the_separator_collision_cannot_happen(self) -> None:
        """The defect the design started with, pinned so it cannot return."""
        left = row_digest({"tool": "get_emails", "status": "ok|failed"})
        right = row_digest({"tool": "get_emails|ok", "status": "failed"})

        assert left != right

    def test_a_field_boundary_cannot_be_moved(self) -> None:
        assert row_digest({"a": "xy", "b": ""}) != row_digest({"a": "x", "b": "y"})

    def test_a_key_cannot_absorb_a_value(self) -> None:
        assert row_digest({"ab": "c"}) != row_digest({"a": "bc"})

    def test_absent_is_not_empty_and_not_the_word_none(self) -> None:
        digests = {
            row_digest({"x": None}),
            row_digest({"x": ""}),
            row_digest({"x": "None"}),
        }

        assert len(digests) == 3

    def test_a_number_is_not_its_text(self) -> None:
        assert row_digest({"n": 1}) != row_digest({"n": "1"})

    def test_true_is_not_one(self) -> None:
        """``isinstance(True, int)`` is True — the check order is load-bearing."""
        assert row_digest({"b": True}) != row_digest({"b": 1})

    def test_an_identifier_is_not_its_text(self) -> None:
        assert row_digest({"i": _ID}) != row_digest({"i": str(_ID)})


class TestOneContentAlwaysGivesOneDigest:
    def test_the_declaration_order_of_columns_does_not_matter(self) -> None:
        assert row_digest({"a": "1", "b": "2"}) == row_digest({"b": "2", "a": "1"})

    def test_an_identifier_is_case_folded(self) -> None:
        upper = uuid.UUID(str(_ID).upper())

        assert row_digest({"i": _ID}) == row_digest({"i": upper})

    def test_an_instant_is_rendered_in_UTC_whatever_its_offset(self) -> None:
        paris = _WHEN.astimezone(timezone(timedelta(hours=2)))

        assert row_digest({"t": _WHEN}) == row_digest({"t": paris})

    def test_microseconds_are_fixed_width(self) -> None:
        """A value with no microseconds must not render shorter."""
        without = datetime(2026, 9, 4, 17, 2, 26, 0, tzinfo=UTC)

        assert b"17:02:26.000000Z" in canonical_bytes({"t": without})

    def test_a_naive_instant_is_refused_rather_than_guessed(self) -> None:
        """Guessing a timezone would make the digest depend on the server."""
        with pytest.raises(ValueError, match="naive"):
            row_digest({"t": datetime(2026, 9, 4, 17, 2, 26)})

    def test_an_enumeration_is_digested_by_its_STORED_value(self) -> None:
        from src.domains.agents.effects.models import EffectStatus

        assert row_digest({"s": EffectStatus.SUCCEEDED}) == row_digest({"s": "succeeded"})

    def test_an_unsupported_type_is_refused_rather_than_stringified(self) -> None:
        """``str()`` on an unknown type is a rendering nobody pinned."""
        with pytest.raises(TypeError, match="Decimal"):
            row_digest({"x": Decimal("1.5")})


class TestTheEncodingIsVersioned:
    def test_the_version_is_declared(self) -> None:
        assert isinstance(DIGEST_VERSION, int)
        assert DIGEST_VERSION >= 1

    def test_the_version_travels_inside_the_bytes(self) -> None:
        """A digest that did not carry its rule could be re-read under another."""
        assert f"v{DIGEST_VERSION}".encode() in canonical_bytes({"x": "y"})


class TestFrozenVectors:
    """The vectors that turn a library upgrade into a RED TEST here.

    Every value below was computed by this implementation and frozen. If one of
    them ever changes, the encoding changed — and that is a new
    ``DIGEST_VERSION``, never an edit to these numbers. Editing a vector to
    make the suite pass would silently invalidate every chain in production.
    """

    @pytest.mark.parametrize(
        ("fields", "expected"),
        [
            ({}, "76956a9605024272ebcecfd3688f9593270938d0c2cd1987d19f654b5ce790af"),
            ({"x": None}, "7bb4ae18ebbe9a164e78bf34132f00263f63ef5251d9cc2653e5f87633e2fcd0"),
            ({"x": ""}, "e506232555a8a2aff4048650a5c371098add6f524b2182cdccb85d2ba95ecdef"),
            (
                {"tool_name": "get_emails_tool"},
                "333fd9a545c4c34cec3c1efce340f35024207b67e03550860cc9a59dc5983473",
            ),
            ({"id": _ID}, "c29aca17fc160538d4f0c0448a7bbeaeb33741032649f9ab14d038e7d5d1e2db"),
            (
                {"claimed_at": _WHEN},
                "3d0522fe0b19b42423e232964137d3b35e144a627285236dc34cbc7963ee2c2b",
            ),
            (
                {"n": 42, "b": True},
                "0b0bbb95066dc733121312e837cdbe6def8487cce16a4278a7221eb4fdc45d21",
            ),
        ],
    )
    def test_the_digest_is_exactly_what_it_has_always_been(
        self, fields: dict[str, object], expected: str
    ) -> None:
        assert row_digest(fields) == expected
