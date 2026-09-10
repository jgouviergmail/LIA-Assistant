"""Where the context window a turn works with actually came from (B8, lot 7.4).

ADR-278 made the window a property of the configured SLOT, resolved from three
places in order: the operator's own override, a catalogue row whose capabilities
somebody vouched for, and the hand-maintained table that is the safety net.
The number was published; **which of the three answered was not**.

That matters for live debugging in the one case it is easiest to get wrong: a
window that comes from the table is a DEFAULT, not a measurement — the table is
wrong on 10 of its 56 entries — so a reader who takes it for the model's own
declaration draws the wrong conclusion about why compaction fired.

The resolution has ONE implementation: `get_effective_context_window_for_slot`
returns this function's ``tokens``. Two would eventually disagree, and the panel
would name a window no reader ever used.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.core.llm_config_helper import (
    get_effective_context_window_for_slot,
    resolve_context_window_for_slot,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def slot(monkeypatch: pytest.MonkeyPatch):
    """Configure one slot's model and override, and nothing else."""

    def configure(*, model: str, context_window: int | None) -> None:
        monkeypatch.setattr(
            "src.core.llm_config_helper.get_llm_config_for_agent",
            lambda _settings, _agent: SimpleNamespace(model=model, context_window=context_window),
        )

    return configure


@pytest.fixture
def catalogue(monkeypatch: pytest.MonkeyPatch):
    """What the capabilities cache answers for a model."""

    def configure(caps: object | None) -> None:
        monkeypatch.setattr(
            "src.infrastructure.llm.model_capabilities_cache.ModelCapabilitiesCache.get",
            staticmethod(lambda _model: caps),
        )

    return configure


class TestWhichSourceAnswered:
    def test_an_operator_override_is_named_as_one(self, slot, catalogue) -> None:
        catalogue(SimpleNamespace(max_input_tokens=8192, capability_provenance="imported"))
        slot(model="gpt-5-mini", context_window=64000)

        resolution = resolve_context_window_for_slot("response")

        assert resolution.tokens == 64000
        assert resolution.source == "slot_override"

    def test_a_vouched_catalogue_row_is_named_as_the_catalogue(self, slot, catalogue) -> None:
        catalogue(SimpleNamespace(max_input_tokens=272000, capability_provenance="imported"))
        slot(model="gpt-5.2", context_window=None)

        resolution = resolve_context_window_for_slot("response")

        assert resolution.tokens == 272000
        assert resolution.source == "catalogue"

    def test_a_row_nobody_vouched_for_falls_back_to_the_table(self, slot, catalogue) -> None:
        # `declared` is the column default nobody curated: it was 8 192 on 89 of
        # 114 rows. Trusting it would publish a window smaller than the model's
        # real one and make every long turn look over budget.
        catalogue(SimpleNamespace(max_input_tokens=8192, capability_provenance="declared"))
        slot(model="gpt-5.2", context_window=None)

        resolution = resolve_context_window_for_slot("response")

        assert resolution.source == "table"
        assert resolution.tokens != 8192

    def test_a_model_outside_the_catalogue_falls_back_to_the_table(self, slot, catalogue) -> None:
        catalogue(None)
        slot(model="some-unknown-model", context_window=None)

        resolution = resolve_context_window_for_slot("response")

        assert resolution.source == "table"
        assert resolution.tokens > 0


class TestTheResolutionHasOneImplementation:
    def test_the_published_window_is_the_one_every_reader_uses(self, slot, catalogue) -> None:
        catalogue(None)
        slot(model="gpt-5-mini", context_window=48000)

        assert (
            get_effective_context_window_for_slot("response")
            == resolve_context_window_for_slot("response").tokens
        )

    def test_a_zero_override_is_refused_rather_than_honoured(self, slot, catalogue) -> None:
        # The write path refuses a zero; honouring one here would make every
        # turn look over budget, on a number nobody typed.
        catalogue(None)
        slot(model="gpt-5-mini", context_window=0)

        resolution = resolve_context_window_for_slot("response")

        assert resolution.source != "slot_override"
        assert resolution.tokens > 0

    def test_it_names_the_slot_and_the_model_it_answered_for(self, slot, catalogue) -> None:
        # A window with no model beside it cannot be checked against anything.
        catalogue(None)
        slot(model="gpt-5-mini", context_window=None)

        resolution = resolve_context_window_for_slot("react_agent")

        assert resolution.slot == "react_agent"
        assert resolution.model == "gpt-5-mini"
