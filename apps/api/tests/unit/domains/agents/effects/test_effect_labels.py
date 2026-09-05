"""A register nobody can read is a log file (ADR-263).

The row knows the tool name and a digest; a human needs *"Sent an email to
Marie"*. That sentence is built at CLAIM time — the arguments are there and
nowhere else — but stored as ``{i18n_key, values}`` rather than as a sentence,
for two independent reasons:

- the reader's language may change after the fact, and a frozen sentence would
  keep the language of the day the action happened;
- the frontend resolves the same keys itself (``apps/web/CLAUDE.md``: the API
  ships structured data, never a translation).

Natives declare their builder; a third-party MCP tool cannot (its name is its
server's business), so its label is DERIVED — the same split as the mutation
policy, and for the same reason.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.effects.labels import (
    EFFECT_LABEL_BUILDERS,
    assert_effect_label_completeness,
    build_effect_label,
)

pytestmark = [pytest.mark.unit]


class TestTheLabelSaysWhatHappened:
    def test_a_native_tool_uses_its_declared_builder(self) -> None:
        """An ACTING tool — a draft-building one never claims, its executor does."""
        label = build_effect_label("control_hue_light_tool", {"room": "Salon"})
        assert label is not None
        assert label["i18n_key"] == "effects.labels.control_hue_light_tool"
        assert label["values"]["target"] == "Salon"

    def test_a_draft_executor_is_labelled_by_its_family(self) -> None:
        label = build_effect_label("draft:email", {"draft": {"to": "marie@example.com"}})
        assert label is not None
        assert label["i18n_key"] == "effects.labels.draft.email"

    def test_a_third_party_tool_is_derived_not_declared(self) -> None:
        """A server names its own tools; the register still reads."""
        label = build_effect_label("mcp_era_billing__cancel_subscription", {"plan": "premium"})
        assert label is not None
        assert label["i18n_key"] == "effects.labels.mcp"
        assert label["values"]["tool"] == "era: billing cancel subscription"

    def test_an_unknown_native_tool_still_produces_a_label(self) -> None:
        """Doubt degrades the wording, never the record."""
        label = build_effect_label("some_future_tool", {})
        assert label is not None
        assert label["i18n_key"] == "effects.labels.generic"
        # ``_readable_tool_name`` drops the ``_tool`` suffix, as on the card.
        assert label["values"]["tool"] == "some future"


class TestTheValuesCarryNoSurprises:
    def test_values_are_json_serialisable(self) -> None:
        """The label is encrypted as JSON: a stray object would raise at write."""
        import json

        for tool_name, builder in EFFECT_LABEL_BUILDERS.items():
            values = builder({"anything": object()})
            json.dumps(values, default=str)  # must not raise on the SHAPE
            assert isinstance(values, dict), tool_name

    def test_a_missing_argument_never_raises(self) -> None:
        """A builder reads what the model chose to send — often not everything."""
        for tool_name in EFFECT_LABEL_BUILDERS:
            assert build_effect_label(tool_name, {}) is not None, tool_name

    def test_long_values_are_capped(self) -> None:
        """A card is a sentence, not a payload — and the column is encrypted."""
        label = build_effect_label("draft:email", {"draft": {"to": "x" * 500}})
        assert label is not None
        assert len(label["values"]["recipient"]) <= 120


@pytest.fixture
def _loaded_catalogue() -> Any:
    """What the boot has done by the time the assert runs.

    The guard reads the GLOBAL registry and the executor registry; against
    empty ones it would pass on anything, which is exactly the vacuity the
    codebase's other completeness asserts warn about.
    """
    from src.domains.agents.registry import reset_global_registry, set_global_registry
    from src.domains.agents.registry.agent_registry import AgentRegistry
    from src.domains.agents.registry.catalogue_loader import initialize_catalogue
    from src.domains.agents.services.draft_executor_registry import ensure_executors_registered
    from src.domains.agents.tools import tool_registry

    tool_registry.ensure_tools_loaded()
    registry = AgentRegistry()
    initialize_catalogue(registry)
    set_global_registry(registry)
    ensure_executors_registered()
    try:
        yield
    finally:
        # The global is shared by every test in this xdist worker: leaving a
        # registry behind turns this file into another file's flake.
        reset_global_registry()


class TestCompleteness:
    def test_every_acting_tool_and_executor_has_a_builder(self, _loaded_catalogue: None) -> None:
        """The ADR-085 idiom: the omission is refused, not inferred."""
        assert_effect_label_completeness()

    def test_the_guard_catches_an_omission(self, _loaded_catalogue: None) -> None:
        """Anti-vacuity: the assert above is not vacuously true."""
        from unittest.mock import patch

        with patch.dict(EFFECT_LABEL_BUILDERS, {}, clear=True):
            with pytest.raises(AssertionError) as caught:
                assert_effect_label_completeness()
        assert "label" in str(caught.value).lower()

    def test_it_covers_both_families(self, _loaded_catalogue: None) -> None:
        """Acting tools AND draft executors — losing either half is a hole."""
        from unittest.mock import patch

        without_tools = {k: v for k, v in EFFECT_LABEL_BUILDERS.items() if k.startswith("draft:")}
        with patch.dict(EFFECT_LABEL_BUILDERS, without_tools, clear=True):
            with pytest.raises(AssertionError) as tools_missing:
                assert_effect_label_completeness()
        assert "control_hue_light_tool" in str(tools_missing.value)

        without_drafts = {
            k: v for k, v in EFFECT_LABEL_BUILDERS.items() if not k.startswith("draft:")
        }
        with patch.dict(EFFECT_LABEL_BUILDERS, without_drafts, clear=True):
            with pytest.raises(AssertionError) as drafts_missing:
                assert_effect_label_completeness()
        assert "draft:email" in str(drafts_missing.value)


class TestEveryKeyExistsInAllSixLanguages:
    def test_the_backend_table_is_complete(self) -> None:
        """Same key set under every language — the shape of ``i18n_drafts``."""
        from src.core.i18n_effects import EFFECT_LABELS, SUPPORTED_LABEL_LANGUAGES

        assert set(EFFECT_LABELS) == set(SUPPORTED_LABEL_LANGUAGES)
        reference = set(EFFECT_LABELS["en"])
        for language, table in EFFECT_LABELS.items():
            assert set(table) == reference, (
                f"{language} differs from en: "
                f"missing={sorted(reference - set(table))} extra={sorted(set(table) - reference)}"
            )

    def test_every_produced_key_is_translated(self) -> None:
        from src.core.i18n_effects import EFFECT_LABELS

        produced = {
            build_effect_label(tool_name, {})["i18n_key"]  # type: ignore[index]
            for tool_name in EFFECT_LABEL_BUILDERS
        }
        produced |= {"effects.labels.mcp", "effects.labels.generic"}
        missing = sorted(produced - set(EFFECT_LABELS["en"]))
        assert not missing, f"labels produced but never translated: {missing}"


class TestRendering:
    @pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
    def test_a_label_renders_in_every_language(self, language: str) -> None:
        from src.core.i18n_effects import render_effect_label

        rendered = render_effect_label(
            {"i18n_key": "effects.labels.draft.email", "values": {"recipient": "Marie"}},
            language,
        )
        assert "Marie" in rendered
        assert "{" not in rendered, "an unsubstituted placeholder survived"

    def test_an_unknown_key_degrades_instead_of_raising(self) -> None:
        from src.core.i18n_effects import render_effect_label

        rendered = render_effect_label({"i18n_key": "effects.labels.nope", "values": {}}, "fr")
        assert rendered

    def test_a_missing_value_degrades_instead_of_raising(self) -> None:
        """An older row may lack a value a newer wording expects."""
        from src.core.i18n_effects import render_effect_label

        rendered = render_effect_label(
            {"i18n_key": "effects.labels.draft.email", "values": {}}, "fr"
        )
        assert rendered

    def test_a_malformed_label_degrades_instead_of_raising(self) -> None:
        from src.core.i18n_effects import render_effect_label

        for malformed in (None, {}, {"values": {}}, "not a dict"):
            assert isinstance(render_effect_label(malformed, "fr"), str)  # type: ignore[arg-type]


class TestTheLanguageIsTheReadersNotTheWriters:
    def test_the_same_row_reads_differently_per_language(self) -> None:
        from src.core.i18n_effects import render_effect_label

        stored: dict[str, Any] = {
            "i18n_key": "effects.labels.draft.email",
            "values": {"recipient": "Marie"},
        }
        assert render_effect_label(stored, "fr") != render_effect_label(stored, "de")
