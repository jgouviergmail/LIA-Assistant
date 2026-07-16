"""Characterization net for ContactCard._render_collapsible_details (audit F015).

Pins the exact behavior of the CC-72 collapsible-details renderer BEFORE it is
decomposed into per-section helpers, so the cut can be proven behavior-preserving
(method precedent: ADR-125 / ADR-122 characterization-first extraction). Each
section is independent (``if data.get(field): ... append(render_d_row(...))``), so
the tests assert per-section presence, caps, truncation, dict-vs-str handling,
badge rendering, and the empty/wrapper contract.
"""

from __future__ import annotations

import pytest

from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.contact_card import ContactCard


@pytest.fixture
def card() -> ContactCard:
    return ContactCard()


@pytest.fixture
def ctx() -> RenderContext:
    return RenderContext(language="fr")


def _render(card: ContactCard, ctx: RenderContext, data: dict) -> str:
    return card._render_collapsible_details(data, ctx)


# --------------------------------------------------------------------------- #
# Empty / wrapper contract
# --------------------------------------------------------------------------- #


def test_no_sections_returns_empty_string(card, ctx):
    assert _render(card, ctx, {}) == ""
    # Fields present but with no renderable content also collapse to empty.
    assert _render(card, ctx, {"nicknames": [{"value": ""}], "skills": []}) == ""


def test_any_section_wraps_in_a_collapsible(card, ctx):
    out = _render(card, ctx, {"skills": [{"value": "Python"}]})
    assert out != ""
    assert "Python" in out


# --------------------------------------------------------------------------- #
# Addresses — only the extras (addresses[1:3]) render here; first is on the card
# --------------------------------------------------------------------------- #


def test_addresses_render_only_second_and_third(card, ctx):
    data = {
        "addresses": [
            {"formattedValue": "1 First St", "type": "home"},
            {"formattedValue": "2 Second Ave", "type": "work"},
            {"formatted": "3 Third Rd", "type": ""},
            {"formattedValue": "4 Fourth", "type": "home"},
        ]
    }
    out = _render(card, ctx, data)
    assert "1 First St" not in out  # first address never in details
    assert "2 Second Ave" in out
    assert "3 Third Rd" in out
    assert "4 Fourth" not in out  # sliced off ([1:3])


def test_single_address_renders_nothing(card, ctx):
    assert _render(card, ctx, {"addresses": [{"formattedValue": "Only"}]}) == ""


def test_address_string_item_is_supported(card, ctx):
    out = _render(card, ctx, {"addresses": [{"formattedValue": "A"}, "plain string addr"]})
    assert "plain string addr" in out


# --------------------------------------------------------------------------- #
# Nicknames / skills / interests / occupations — comma-joined, capped, escaped
# --------------------------------------------------------------------------- #


def test_nicknames_joined_capped_and_skip_empty(card, ctx):
    data = {"nicknames": [{"value": "Bobby"}, "Rob", {"value": ""}, {"value": "Fourth"}]}
    out = _render(card, ctx, data)
    assert "Bobby, Rob" in out  # empty skipped
    assert "Fourth" not in out  # capped at 3 (Bobby, Rob, then empty consumed slot? see cap[:3])


def test_skills_interests_occupations_render_values(card, ctx):
    out = _render(
        card,
        ctx,
        {
            "skills": [{"value": "Python"}, "SQL"],
            "interests": ["Chess"],
            "occupations": [{"value": "Engineer"}],
        },
    )
    assert "Python" in out and "SQL" in out
    assert "Chess" in out
    assert "Engineer" in out


# --------------------------------------------------------------------------- #
# Relations — capped at 5, dict-or-str, empty person skipped
# --------------------------------------------------------------------------- #


def test_relations_dict_and_string_capped(card, ctx):
    data = {
        "relations": [
            {"person": "Alice", "type": "spouse"},
            "Bob",
            {"person": "", "type": "child"},
            {"person": "Carol"},
            {"person": "Dan"},
            {"person": "Eve"},
            {"person": "SixthCappedOut"},
        ]
    }
    out = _render(card, ctx, data)
    assert "Alice" in out and "Bob" in out and "Carol" in out
    assert "SixthCappedOut" not in out  # >5 relations (empty person consumes a slot)


# --------------------------------------------------------------------------- #
# Biography — first entry, truncated at 150 chars with an ellipsis
# --------------------------------------------------------------------------- #


def test_biography_truncated_at_150(card, ctx):
    out = _render(card, ctx, {"biographies": [{"value": "y" * 200}]})
    assert ("y" * 147 + "...") in out
    assert "y" * 148 not in out


def test_short_biography_not_truncated(card, ctx):
    out = _render(card, ctx, {"biographies": [{"value": "short bio"}]})
    assert "short bio" in out
    assert "..." not in out


# --------------------------------------------------------------------------- #
# IM clients / events / locations / calendar URLs
# --------------------------------------------------------------------------- #


def test_im_clients_need_protocol_and_username(card, ctx):
    out = _render(
        card,
        ctx,
        {"imClients": [{"protocol": "Signal", "username": "alice"}, {"protocol": "X"}]},
    )
    assert "Signal: alice" in out
    assert out.count("Signal") == 1  # the incomplete second entry is dropped


def test_im_clients_snake_case_alias(card, ctx):
    out = _render(card, ctx, {"im_clients": [{"type": "XMPP", "value": "bob@x"}]})
    assert "XMPP: bob@x" in out


def test_events_render_formatted_date(card, ctx):
    out = _render(
        card,
        ctx,
        {"events": [{"type": "Anniversary", "date": {"day": 14, "month": 7, "year": 2020}}]},
    )
    assert "Anniversary" in out


def test_locations_dict_only_with_value(card, ctx):
    out = _render(
        card,
        ctx,
        {"locations": [{"type": "Desk", "value": "Building A"}, "ignored-non-dict"]},
    )
    assert "Building A" in out
    assert "ignored-non-dict" not in out


def test_calendar_urls_render_anchor(card, ctx):
    out = _render(card, ctx, {"calendarUrls": [{"label": "Work", "url": "https://cal/w"}]})
    assert 'href="https://cal/w"' in out
    assert ">Work</a>" in out


# --------------------------------------------------------------------------- #
# Byte-stability: a maximal input's full output must survive decomposition
# --------------------------------------------------------------------------- #


def _maximal_data() -> dict:
    return {
        "addresses": [
            {"formattedValue": "1 First St", "type": "home"},
            {"formattedValue": "2 Second Ave", "type": "work"},
            {"formatted": "3 Third Rd", "type": ""},
        ],
        "nicknames": [{"value": "Bobby"}, "Rob"],
        "relations": [{"person": "Alice", "type": "spouse"}, "Bob"],
        "biographies": [{"value": "x" * 200}],
        "skills": [{"value": "Python"}, "SQL"],
        "interests": ["Chess", {"value": "Go"}],
        "occupations": [{"value": "Engineer"}],
        "imClients": [{"protocol": "Signal", "username": "alice"}],
        "events": [{"type": "Anniversary", "date": {"day": 14, "month": 7, "year": 2020}}],
        "locations": [{"type": "Desk", "value": "Building A"}],
        "calendarUrls": [{"label": "Work Cal", "url": "https://cal.example/w"}],
    }


def test_maximal_output_is_nonempty_and_covers_all_sections(card, ctx):
    """Every section contributes to the maximal render (guards the byte-stability set)."""
    out = _render(card, ctx, _maximal_data())
    for needle in (
        "2 Second Ave",
        "Bobby, Rob",
        "Alice",
        ("x" * 147 + "..."),
        "Python",
        "Chess",
        "Engineer",
        "Signal: alice",
        "Anniversary",
        "Building A",
        "Work Cal",
    ):
        assert needle in out, f"section missing from maximal render: {needle!r}"


# SHA256 of the maximal render captured against the pre-decomposition code. The
# decomposition must be pure code-motion, so this hash MUST stay identical — a
# byte-level guard the per-section behavior tests above complement.
_GOLDEN_MAXIMAL_SHA256 = "2749fa88a44b7d19e3ba6ed9e0592c6f068c689e198a86701388694d1c5484b5"


def test_maximal_output_is_byte_identical_to_golden(card, ctx):
    import hashlib

    out = _render(card, ctx, _maximal_data())
    digest = hashlib.sha256(out.encode("utf-8")).hexdigest()
    assert digest == _GOLDEN_MAXIMAL_SHA256, (
        "collapsible-details output changed vs the pre-decomposition golden — the "
        "F015 extraction must be behavior-preserving (byte-identical)."
    )
