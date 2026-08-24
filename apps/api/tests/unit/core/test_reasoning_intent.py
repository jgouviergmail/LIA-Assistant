"""One value replaces four shapes, and its ladder is ordered."""

from __future__ import annotations

import dataclasses

import pytest

from src.core.reasoning_intent import LEVELS, ReasoningIntent, level_ordinal, requested_level


def test_the_ladder_is_ordered_from_off_to_max() -> None:
    assert LEVELS == (
        "provider_default",
        "none",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    )


def test_ordinals_are_strictly_increasing() -> None:
    """Coercion measures distance on this ladder; a tie must be a real tie."""
    ordinals = [level_ordinal(level) for level in LEVELS]
    assert ordinals == sorted(ordinals)
    assert len(set(ordinals)) == len(LEVELS)


def test_the_default_intent_asks_for_nothing() -> None:
    """``provider_default`` is the identity: no kwarg, whatever the model."""
    intent = ReasoningIntent()
    assert intent.level == "provider_default"
    assert intent.budget_tokens is None
    assert intent.exclude_from_output is False


def test_the_intent_is_frozen() -> None:
    intent = ReasoningIntent(level="high")
    with pytest.raises(dataclasses.FrozenInstanceError):
        intent.level = "low"  # type: ignore[misc]


def test_an_unknown_level_has_no_ordinal() -> None:
    """Never guess a rank: a silent default makes coercion pick a neighbour."""
    with pytest.raises(KeyError):
        level_ordinal("telepathic")


class TestRequestedLevel:
    """Adapters read the LEVEL, not the kwargs — and from any stored shape.

    Two adapter branches ask this question: whether a GPT-5.1+ model at ``none``
    still accepts sampling parameters, and what to put in the DeepSeek log line.
    The second read ``.effort`` after the field was retyped and printed ``None``
    on every thinking-enabled call — a log that cannot be wrong is the point of
    having one helper.
    """

    def test_it_reads_an_intent(self) -> None:
        assert requested_level(ReasoningIntent(level="high")) == "high"

    def test_it_reads_every_legacy_shape(self) -> None:
        assert requested_level({"effort": "off"}) == "none"
        assert requested_level({"effort": "medium"}) == "medium"
        assert requested_level({"enabled": False}) == "none"
        assert requested_level({"budget": 8192}) == "provider_default"

    def test_absence_reads_as_the_identity(self) -> None:
        assert requested_level(None) == "provider_default"
        assert requested_level({}) == "provider_default"

    def test_it_reads_a_duck_typed_object(self) -> None:
        from types import SimpleNamespace

        assert requested_level(SimpleNamespace(level="xhigh")) == "xhigh"
        assert requested_level(SimpleNamespace(nothing=1)) == "provider_default"

    def test_it_never_raises_on_an_unexpected_value(self) -> None:
        """It runs inside an adapter: an exception here fails an LLM call."""
        for odd in (42, "high", [1, 2], object()):
            assert isinstance(requested_level(odd), str)
