"""T6, permanent: every stored shape reads as an intent, and the "off"s collapse."""

from __future__ import annotations

import pytest

from src.core.reasoning_intent import ReasoningIntent
from src.infrastructure.llm.reasoning.translate import intent_from_legacy

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "stored",
    [
        {"effort": "off"},
        {"effort": "none"},
        {"enabled": False},
        {"enabled": False, "budget": None},
        {"budget": 0},
    ],
)
def test_every_encoding_of_off_collapses_to_one(stored: dict) -> None:
    """Measured over the 54 configured slots: 21 said it one way, 6 another."""
    assert intent_from_legacy(stored) == ReasoningIntent(level="none")


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (None, ReasoningIntent()),
        ({}, ReasoningIntent()),
        ({"budget": -1}, ReasoningIntent()),
        ({"effort": "medium"}, ReasoningIntent(level="medium")),
        ({"effort": "minimal"}, ReasoningIntent(level="minimal")),
        ({"effort": "high"}, ReasoningIntent(level="high")),
        ({"budget": 8192}, ReasoningIntent(budget_tokens=8192)),
        ({"enabled": True, "budget": 4096}, ReasoningIntent(budget_tokens=4096)),
    ],
)
def test_the_other_shapes_read_as_themselves(
    stored: dict | None, expected: ReasoningIntent
) -> None:
    assert intent_from_legacy(stored) == expected


def test_an_enabled_toggle_without_a_budget_takes_the_provider_floor() -> None:
    from src.core.constants import ANTHROPIC_MIN_THINKING_BUDGET_TOKENS

    assert intent_from_legacy({"enabled": True}) == ReasoningIntent(
        budget_tokens=ANTHROPIC_MIN_THINKING_BUDGET_TOKENS
    )


def test_an_unrecognised_shape_reads_as_provider_default() -> None:
    """The migration must be total: a shape nobody planned for cannot abort it."""
    assert intent_from_legacy({"telepathy": True}) == ReasoningIntent()


def test_every_code_default_is_already_an_intent() -> None:
    """The code defaults were migrated with the DB rows -- no legacy shape left.

    ``LLM_DEFAULTS`` is the fallback every unconfigured slot resolves to, so a
    legacy dict surviving here would reach the translator on a path no stored
    row covers.
    """
    from src.domains.llm_config.constants import LLM_DEFAULTS

    for name, config in LLM_DEFAULTS.items():
        stored = config.reasoning_effort
        assert stored is None or isinstance(stored, ReasoningIntent), name


def test_reading_an_already_migrated_value_is_idempotent() -> None:
    """The mapper is total on its own output: re-running the migration is safe.

    Migration ``d3e4f5a6b7c8`` skips rows already in the intent shape, but an
    operator replaying a seed, or a row written by a newer instance before an
    older one migrates, must not be re-encoded into something else.
    """
    from dataclasses import asdict

    for intent in (
        ReasoningIntent(),
        ReasoningIntent(level="none"),
        ReasoningIntent(level="high"),
        ReasoningIntent(budget_tokens=8192),
        ReasoningIntent(level="medium", exclude_from_output=True),
    ):
        assert intent_from_legacy(asdict(intent)) == intent
