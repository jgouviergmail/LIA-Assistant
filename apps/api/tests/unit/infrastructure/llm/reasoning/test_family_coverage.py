"""The family must never be wrong; the ladder may only narrow.

T2 of the validation harness, made permanent. A catalogue model the seed
declares reasoning but whose family resolves to ``none`` is a gap that would
send no reasoning kwarg at all; the reverse is a widening. Each known
divergence is allowlisted with its evidence, in both directions.

The claim compared used to be ``reasoning_widget``. That column was dropped
with ADR-245, and the comparison moved to ``is_reasoning_model`` — which
answers a slightly different question ("does it reason" rather than "can its
depth be chosen"), hence the one always-on entry below.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.infrastructure.llm.reasoning.profiles import (
    _RULES,
    FAMILIES,
    ReasoningProfile,
    resolve_reasoning_profile,
)

pytestmark = pytest.mark.unit

#: Models the family rules say reason while the catalogue's
#: ``is_reasoning_model`` says they do not. Every one is a derivative or a dated preview of a model the
#: catalogue itself declares reasoning, so the row is a stale copy that lost the
#: attribute -- not a rule that is too broad:
#:
#:   o3                    enum  <->  o3-deep-research                       none
#:   o4-mini               enum  <->  o4-mini-deep-research                  none
#:   sonar-deep-research   enum  <->  sonar-reasoning / -pro                 none
#:   gemini-2.5-flash budget_int <->  gemini-2.5-flash[-lite]-preview-09-2025 none
#:
#: Shrink-only: an entry leaves when its row is corrected, and none may be added
#: without the same side-by-side check.
KNOWN_WIDENINGS: frozenset[str] = frozenset(
    {
        "o3-deep-research",
        "o4-mini-deep-research",
        "sonar-reasoning",
        "sonar-reasoning-pro",
        "gemini-2.5-flash-preview-09-2025",
        "gemini-2.5-flash-lite-preview-09-2025",
    }
)

#: Models that genuinely reason with NO configurable depth, so no family rule
#: places them and none should. ``deepseek-reasoner`` (V3 / R1) is the case:
#: the adapter gives it its own branch and sends no reasoning kwarg at all, so
#: ``family="none"`` is the correct answer, not a gap. Shrink-only, same rule as
#: the widenings: an entry leaves when a family starts covering the model.
KNOWN_ALWAYS_ON: frozenset[str] = frozenset({"deepseek-reasoner"})

_SEED = (
    Path(__file__).resolve().parents[7]
    / "infrastructure"
    / "database"
    / "seeds"
    / "llm_pricing_seed.sql"
)


def _split_values(row: str) -> list[str]:
    """Split one SQL VALUES tuple on top-level commas.

    Quote-aware on purpose: a JSONB literal such as ``'["low", "medium"]'`` puts
    commas inside a quoted field, and a naive split shifts every column after it.
    """
    fields, current, in_quote = [], [], False
    for char in row:
        if char == "'":
            in_quote = not in_quote
        if char == "," and not in_quote:
            fields.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    fields.append("".join(current).strip())
    return fields


def _catalogue_rows() -> list[dict[str, str]]:
    """Parse the llm_models VALUES rows into dicts, keyed by the INSERT's own columns.

    Driven by the column list the seed declares rather than by positions, so a
    future column insertion cannot silently shift what this guard reads -- the
    failure mode that made the first draft report 44 contradictions instead of 4.
    """
    text = _SEED.read_text(encoding="utf-8")
    header = text[text.index("INSERT INTO llm_models (") : text.index(") VALUES")]
    columns = [line.strip().rstrip(",") for line in header.splitlines()[1:] if line.strip()]

    rows: list[dict[str, str]] = []
    for match in re.finditer(r"^\s*\('([a-z]+)',(.*)\),?\s*$", text, re.MULTILINE):
        fields = _split_values(f"'{match.group(1)}',{match.group(2)}")
        if len(fields) != len(columns):
            continue
        rows.append({name: value.strip("'") for name, value in zip(columns, fields, strict=True)})
    return rows


def test_the_seed_parser_finds_rows() -> None:
    """A parser that matched nothing would make the coverage test vacuous."""
    rows = _catalogue_rows()
    assert len(rows) >= 100
    # and it must read the right columns, not merely some columns
    by_name = {row["model_name"]: row for row in rows}
    assert by_name["o3"]["is_reasoning_model"] == "true"
    assert by_name["gpt-4.1"]["is_reasoning_model"] == "false"
    assert by_name["o3"]["kind"] == "chat"
    # a JSONB literal contains commas; the splitter must not shift on it
    assert by_name["o3"]["reasoning_enum_values"].startswith('["low"')


def test_every_rule_produces_a_declared_family() -> None:
    """An unknown family would silently translate to nothing."""
    for _provider, _prefixes, profile in _RULES:
        assert profile.family in FAMILIES, profile.family


def test_a_known_model_resolves_to_its_family() -> None:
    assert resolve_reasoning_profile("openai", "gpt-5.2").family == "openai"
    assert resolve_reasoning_profile("anthropic", "claude-opus-4-6").family == "anthropic_adaptive"
    assert resolve_reasoning_profile("deepseek", "deepseek-v4-flash").family == "deepseek_toggle"


def test_a_negative_rule_wins_over_a_broad_one() -> None:
    """``gpt-4.1`` must not inherit the ``gpt-5``-era OpenAI family."""
    assert resolve_reasoning_profile("openai", "gpt-4.1").family == "none"
    assert resolve_reasoning_profile("openai", "gpt-5-chat-latest").family == "none"
    assert resolve_reasoning_profile("anthropic", "claude-3-5-haiku-20241022").family == "none"


def test_an_unknown_model_never_raises() -> None:
    """The catalogue is an optimisation, not a prerequisite."""
    profile = resolve_reasoning_profile("openai", "gpt-5.9-nova-unreleased")
    assert isinstance(profile, ReasoningProfile)
    assert profile.family == "openai"
    assert profile.source == "family"


def test_a_catalogue_ladder_narrows_but_never_widens() -> None:
    base = resolve_reasoning_profile("openai", "gpt-5.2")
    narrowed = resolve_reasoning_profile("openai", "gpt-5.2", model_levels=("low", "high"))
    assert set(narrowed.levels) < set(base.levels)
    assert narrowed.source == "model_refined"

    widened = resolve_reasoning_profile(
        "openai", "gpt-5.2", model_levels=("low", "high", "telepathic")
    )
    assert "telepathic" not in widened.levels


def test_an_empty_narrowing_is_ignored() -> None:
    """A catalogue row that intersects to nothing must not disarm the model."""
    profile = resolve_reasoning_profile("openai", "gpt-5.2", model_levels=("telepathic",))
    assert profile.levels == resolve_reasoning_profile("openai", "gpt-5.2").levels
    assert profile.source == "family"


def test_the_family_covers_every_reasoning_model_in_the_catalogue() -> None:
    """T2, against the shipped seed so the test is deterministic and DB-free."""
    gaps, widenings = [], []
    for row in _catalogue_rows():
        if row["kind"] != "chat":
            continue
        provider, model = row["provider"], row["model_name"]
        declared = row["is_reasoning_model"] == "true"
        family = resolve_reasoning_profile(provider, model).family
        if declared and family == "none" and model not in KNOWN_ALWAYS_ON:
            gaps.append(f"{provider}/{model}")
        elif not declared and family != "none" and model not in KNOWN_WIDENINGS:
            widenings.append(f"{provider}/{model}")
    assert gaps == [], (
        f"the catalogue says these reason, the rules say they do not: {gaps}. "
        "Either a family rule is missing, or the model reasons with no "
        "configurable depth and belongs in KNOWN_ALWAYS_ON with its evidence."
    )
    assert widenings == [], (
        f"the rules say these reason, the catalogue says they do not: {widenings}. "
        "Check the provider's documentation: if the rules are right, the CATALOGUE "
        "row is stale and the model belongs in KNOWN_WIDENINGS with its evidence."
    )


def test_a_family_that_can_disable_offers_a_way_to_say_so() -> None:
    """Structural coherence of the rules themselves.

    ``can_disable=True`` with no ``none`` on the ladder is a contradiction: the
    profile claims reasoning can be switched off while offering no level that
    expresses it, and the translator then emits a value the provider rejects.
    Perplexity carried exactly that inconsistency until this test existed.
    """
    offenders = [
        profile.family
        for _provider, _prefixes, profile in _RULES
        if profile.family != "none" and profile.can_disable and "none" not in profile.levels
    ]
    assert (
        offenders == []
    ), f"these families claim they can disable but offer no 'none': {offenders}"


def test_a_family_that_cannot_disable_does_not_offer_none() -> None:
    """The mirror image, and just as incoherent."""
    offenders = [
        profile.family
        for _provider, _prefixes, profile in _RULES
        if profile.family != "none" and not profile.can_disable and "none" in profile.levels
    ]
    assert (
        offenders == []
    ), f"these families offer 'none' but claim they cannot disable: {offenders}"
