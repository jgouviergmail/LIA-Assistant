"""Tests for turn_type helpers — case-insensitive, composite-aware."""

import pytest

from src.domains.agents.constants import (
    TURN_TYPE_ACTION,
    TURN_TYPE_CONVERSATIONAL,
    TURN_TYPE_REFERENCE,
)
from src.domains.agents.utils.turn_type import (
    is_action_turn,
    is_conversational_turn,
    is_reference_turn,
    normalize_turn_type,
)

# ------- is_reference_turn -------


@pytest.mark.parametrize(
    "value",
    [
        "reference",
        "REFERENCE",
        "reference_pure",
        "REFERENCE_PURE",
        "reference_action",
        "REFERENCE_ACTION",
        "  Reference_Action  ",  # whitespace and mixed case
    ],
)
def test_is_reference_turn_accepts_all_variants(value: str) -> None:
    assert is_reference_turn(value) is True


@pytest.mark.parametrize("value", ["action", "ACTION", "conversational", "", None, "other"])
def test_is_reference_turn_rejects_non_reference(value: str | None) -> None:
    assert is_reference_turn(value) is False


# ------- is_action_turn -------


@pytest.mark.parametrize("value", ["action", "ACTION", " Action "])
def test_is_action_turn_accepts(value: str) -> None:
    assert is_action_turn(value) is True


@pytest.mark.parametrize("value", ["reference", "REFERENCE_ACTION", "conversational", "", None])
def test_is_action_turn_rejects_others(value: str | None) -> None:
    assert is_action_turn(value) is False


# ------- is_conversational_turn -------


@pytest.mark.parametrize("value", ["conversational", "CONVERSATIONAL", "Conversational"])
def test_is_conversational_turn_accepts(value: str) -> None:
    assert is_conversational_turn(value) is True


@pytest.mark.parametrize("value", ["action", "reference", "REFERENCE_ACTION", "", None])
def test_is_conversational_turn_rejects_others(value: str | None) -> None:
    assert is_conversational_turn(value) is False


# ------- normalize_turn_type -------


def test_normalize_lowercases() -> None:
    assert normalize_turn_type("REFERENCE_ACTION") == "reference_action"
    assert normalize_turn_type("Action") == "action"


def test_normalize_defaults_to_action_when_empty() -> None:
    assert normalize_turn_type(None) == TURN_TYPE_ACTION
    assert normalize_turn_type("") == TURN_TYPE_ACTION
    assert normalize_turn_type("   ") == TURN_TYPE_ACTION


def test_normalize_preserves_known_lowercase_values() -> None:
    assert normalize_turn_type(TURN_TYPE_REFERENCE) == TURN_TYPE_REFERENCE
    assert normalize_turn_type(TURN_TYPE_CONVERSATIONAL) == TURN_TYPE_CONVERSATIONAL
