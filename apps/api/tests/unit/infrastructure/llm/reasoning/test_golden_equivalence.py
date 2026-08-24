"""T1, permanent: the new translator reproduces the old builders exactly.

The fixture was captured from the UNMODIFIED code before this lot began, by a
script that has since been DELETED along with the builders it drove. That is
deliberate: re-running a capture today would record the new behaviour and turn
this proof into a tautology. The fixture is the reference and it does not move.

Any divergence is a behaviour change on the hot path of every configured slot,
and this test is what makes "no behaviour change" a checkable claim rather than
an assertion.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.infrastructure.llm.reasoning.profiles import resolve_reasoning_profile
from src.infrastructure.llm.reasoning.translate import intent_from_legacy, translate

pytestmark = pytest.mark.unit

GOLDEN: list[dict] = json.loads(
    Path(__file__).with_name("golden_kwargs.json").read_text(encoding="utf-8")
)

#: The catalogue values the capture ran against, frozen alongside it so this
#: test needs no database and cannot drift with the live catalogue.
LADDERS: dict[str, tuple[str, ...]] = {
    "gpt-5.2-chat-latest": ("medium",),
}


def test_the_golden_is_not_empty() -> None:
    """A fixture that captured nothing would make this test vacuous."""
    assert len(GOLDEN) >= 50


def test_the_golden_covers_every_family_in_use() -> None:
    families = {
        resolve_reasoning_profile(record["provider"], record["model"]).family for record in GOLDEN
    }
    assert "none" in families
    assert len(families) >= 3, f"only {families} exercised"


@pytest.mark.parametrize("record", GOLDEN, ids=[r["slot"] for r in GOLDEN])
def test_the_translator_reproduces_the_builder(record: dict) -> None:
    profile = resolve_reasoning_profile(
        record["provider"],
        record["model"],
        model_levels=LADDERS.get(record["model"]),
    )
    produced = translate(
        intent_from_legacy(record["stored"]),
        profile,
        record["model"],
        record.get("max_output_tokens") or 4096,
    )
    assert produced == record["kwargs"], (
        f"{record['slot']} ({record['provider']}/{record['model']}) diverges: "
        f"was {record['kwargs']}, now {produced}"
    )


def test_the_duplicate_effort_channel_was_unused() -> None:
    """``LLMAgentConfig.effort`` produced the same Anthropic kwarg as
    ``reasoning_effort``, and ``additional_kwargs.update()`` decided which won.
    Measured at capture time: **no slot set it**, so removing it is inert."""
    assert [r["slot"] for r in GOLDEN if r["effort_field"]] == []


class TestTheAdapterSeam:
    """``kwargs_for`` is what every provider branch calls; it must agree with
    ``translate`` on the same inputs, whatever shape the stored value has."""

    @staticmethod
    def _install(model: str, **caps: object) -> None:
        from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
        from src.infrastructure.llm.model_profiles import ModelProfile

        ModelCapabilitiesCache._cache[model] = ModelProfile(model_id=model, **caps)  # type: ignore[arg-type]

    def test_it_accepts_a_legacy_dict(self) -> None:
        from src.infrastructure.llm.reasoning.translate import kwargs_for

        assert kwargs_for("openai", "gpt-5.2", {"effort": "medium"}) == {
            "reasoning_effort": "medium"
        }

    def test_it_accepts_an_object_carrying_a_legacy_shape(self) -> None:
        """The Pydantic shapes are gone, but anything with ``model_dump`` works.

        The seam does not know which class it is handed — a stored dict, an
        intent, or an object from a caller that has not been redeployed.
        """
        from types import SimpleNamespace

        from src.infrastructure.llm.reasoning.translate import kwargs_for

        legacy = SimpleNamespace(model_dump=lambda: {"effort": "medium"})
        assert kwargs_for("openai", "gpt-5.2", legacy) == {"reasoning_effort": "medium"}

    def test_it_accepts_an_intent_directly(self) -> None:
        from src.core.reasoning_intent import ReasoningIntent
        from src.infrastructure.llm.reasoning.translate import kwargs_for

        assert kwargs_for("openai", "gpt-5.2", ReasoningIntent(level="medium")) == {
            "reasoning_effort": "medium"
        }

    def test_it_accepts_none(self) -> None:
        from src.infrastructure.llm.reasoning.translate import kwargs_for

        assert kwargs_for("openai", "gpt-5.2", None) == {}

    def test_an_unknown_model_produces_no_kwarg_instead_of_raising(self) -> None:
        """The previous builders raised RuntimeError on a shape mismatch."""
        from src.infrastructure.llm.reasoning.translate import kwargs_for

        assert kwargs_for("mistral", "some-unmapped-model", {"effort": "high"}) == {}

    def test_the_catalogue_ladder_narrows_through_the_seam(self) -> None:
        from collections.abc import Generator  # noqa: F401

        from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
        from src.infrastructure.llm.reasoning.translate import kwargs_for

        saved = dict(ModelCapabilitiesCache._cache)
        try:
            self._install(
                "gpt-5.2-chat-latest", reasoning_enum_values=["medium"], max_output_tokens=16384
            )
            assert kwargs_for("openai", "gpt-5.2-chat-latest", {"effort": "high"}) == {
                "reasoning_effort": "medium"
            }
        finally:
            ModelCapabilitiesCache._cache = saved

    def test_a_partial_cache_entry_degrades_to_the_family_ladder(self) -> None:
        """This runs inside a provider adapter: it must never raise there.

        A cache entry shaped differently from ``ModelProfile`` — a stand-in in a
        test, a field renamed in a future refactor — degrades to the family's
        own ladder instead of failing the LLM instantiation.
        """
        from types import SimpleNamespace

        from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
        from src.infrastructure.llm.reasoning.translate import kwargs_for

        saved = dict(ModelCapabilitiesCache._cache)
        try:
            ModelCapabilitiesCache._cache["claude-opus-4-6"] = SimpleNamespace(  # type: ignore[assignment]
                model_id="claude-opus-4-6", reasoning_widget="enum"
            )
            assert kwargs_for("anthropic", "claude-opus-4-6", {"effort": "medium"}) == {
                "thinking": {"type": "adaptive"},
                "effort": "medium",
            }
        finally:
            ModelCapabilitiesCache._cache = saved
