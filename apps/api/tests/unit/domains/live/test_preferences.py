"""The person's live conversation reflexes (ADR-299): closed vocabularies on
the way in, a tolerant reader on the way out."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.domains.live.preferences import LivePreferences, read_live_preferences

pytestmark = pytest.mark.unit


def test_defaults() -> None:
    prefs = LivePreferences()
    assert prefs.interruptions is True
    assert prefs.end_of_speech == "normal"
    assert prefs.result_delivery == "interrupt"


def test_strict_payload_refuses_an_unknown_word() -> None:
    with pytest.raises(ValidationError):
        LivePreferences(end_of_speech="shout")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "stored",
    [
        None,
        "garbage",
        42,
        {"end_of_speech": "shout", "interruptions": "maybe"},
        # The talk mode of the first wave: a stored value nobody reads any more.
        {"talk_mode": "push_to_talk", "interruptions": False},
    ],
)
def test_reader_never_raises_and_falls_back_field_by_field(stored: object) -> None:
    prefs = read_live_preferences(stored)
    assert prefs.end_of_speech == "normal"
    assert not hasattr(prefs, "talk_mode")
    assert prefs.interruptions is (
        False if isinstance(stored, dict) and stored.get("interruptions") is False else True
    )


def test_the_provider_choice_is_read_tolerantly_and_absent_by_default() -> None:
    # The account's choice among its active live connectors (wave 2 spec A10):
    # None means the first active one; a garbage value reads as None.
    assert LivePreferences().provider is None
    assert read_live_preferences({"provider": "gemini"}).provider == "gemini"
    assert read_live_preferences({"provider": 42}).provider is None
    assert read_live_preferences({"provider": "x" * 40}).provider is None


def test_reader_keeps_what_is_valid() -> None:
    prefs = read_live_preferences({"interruptions": False, "end_of_speech": "calm", "x": 1})
    assert prefs.interruptions is False
    assert prefs.end_of_speech == "calm"
    assert prefs.result_delivery == "interrupt"
