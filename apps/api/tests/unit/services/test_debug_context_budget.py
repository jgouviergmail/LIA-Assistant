"""What the panel says about the room a turn actually had (B8, lot 7.4).

`token_budget` published four instance-wide thresholds — 'safe', 'warning',
'critical', 'max' — read from settings and **independent of the model actually
configured**. A person debugging a live exchange therefore saw a turn sitting
comfortably inside a « safe » zone while the model it ran on had a smaller
window than the zone's ceiling, or, more often, saw « critical » on a model with
ten times the room.

Two numbers decide what really happens to a long conversation, and neither was
on the screen:

- **the context window the configured slot works with** (ADR-278) and WHICH of
  the three sources answered — a window from the hand-maintained table is a
  default, not a measurement;
- **the instant compaction fires**, which is that window times a ratio unless an
  operator pinned an absolute value. The compaction section only ever appeared
  AFTER a compaction ran, so the threshold that did not fire was invisible.

Both are published beside the value they constrain (ADR-184).
"""

from __future__ import annotations

import pytest

from src.domains.agents.services.streaming import debug_metrics_stages as stages

pytestmark = pytest.mark.unit


def _budget(existing: dict | None = None) -> dict:
    """The context block this run produces, on top of an existing token budget."""
    payload: dict = {"token_budget": dict(existing or {})}
    stages.build_context_window(payload)
    return payload["token_budget"]


class TestTheWindowTheTurnActuallyHad:
    def test_it_publishes_the_effective_window_of_the_response_slot(self) -> None:
        from src.core.llm_config_helper import get_effective_context_window_for_slot

        budget = _budget({"current_tokens": 1000})

        # The slot that carries the conversation: the same number compaction,
        # the ReAct budget and the summarisation middleware all read.
        assert budget["context_window"] == get_effective_context_window_for_slot("response")

    def test_it_names_the_source_that_answered(self) -> None:
        budget = _budget()

        assert budget["context_window_source"] in {"slot_override", "catalogue", "table"}

    def test_it_names_the_model_the_window_belongs_to(self) -> None:
        # A window with no model beside it cannot be checked against anything.
        budget = _budget()

        assert budget["context_window_model"]

    def test_it_says_how_much_of_the_window_the_turn_used(self) -> None:
        window = _budget()["context_window"]
        budget = _budget({"current_tokens": window // 2})

        assert 45 <= budget["context_used_percent"] <= 55

    def test_a_turn_that_counted_nothing_used_nothing(self) -> None:
        # Never a division by an unknown: a percentage invented from a missing
        # count is a figure nobody measured.
        assert _budget()["context_used_percent"] == 0


class TestTheInstantCompactionFires:
    def test_the_threshold_is_published_even_when_it_never_fired(self) -> None:
        # The compaction SECTION only exists after a compaction ran, so the
        # bound that did not fire was invisible — the exact shape of ADR-184's
        # trap.
        budget = _budget({"current_tokens": 10})

        assert budget["compaction_threshold"] > 0

    def test_the_threshold_sits_inside_the_window(self) -> None:
        budget = _budget()

        assert budget["compaction_threshold"] <= budget["context_window"]

    def test_an_absolute_override_wins_and_is_named(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.config import settings as app_settings

        monkeypatch.setattr(app_settings, "compaction_token_threshold", 12345, raising=False)

        budget = _budget()

        assert budget["compaction_threshold"] == 12345
        assert budget["compaction_threshold_source"] == "absolute"

    def test_a_ratio_threshold_is_named_as_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.config import settings as app_settings

        monkeypatch.setattr(app_settings, "compaction_token_threshold", 0, raising=False)

        budget = _budget()

        assert budget["compaction_threshold_source"] == "ratio"


class TestItNeverBreaksTheSectionItEnriches:
    def test_the_thresholds_the_panel_already_showed_are_untouched(self) -> None:
        budget = _budget({"current_tokens": 42, "zone": "safe", "strategy": "full_catalogue"})

        assert budget["current_tokens"] == 42
        assert budget["zone"] == "safe"
        assert budget["strategy"] == "full_catalogue"

    def test_it_writes_nothing_when_there_is_no_budget_to_enrich(self) -> None:
        # The token budget failed to build: inventing a block for it would say
        # the turn had room nobody measured.
        payload: dict = {}
        stages.build_context_window(payload)

        assert payload == {}
