"""How a memory reaches the model — label, and hint versus obligation.

The psychological profile is assembled from the user's memories and injected
into the system prompt. Two coupled decisions govern what the model sees:

- an emotional band label, from the -10..+10 weight;
- whether the memory's ``usage_nuance`` is phrased as an informational hint
  (``→ *…*``) or as a **binding obligation**.

They must agree: a memory the user flagged as painful and which the label calls
negative must also arrive as an obligation. If the two thresholds ever drift
apart, a trauma-adjacent nuance degrades into a suggestion the model is free to
ignore — and nothing in the system reports it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.domains.agents.middleware.memory_injection import (
    _format_memory_item,
    _get_emotional_label,
)

pytestmark = pytest.mark.unit

NEGATIVE_LABELS = {"[TRAUMA/DOULEUR]", "[NÉGATIF]"}


def _memory(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "content": "aime la randonnée",
        "emotional_weight": 0,
        "usage_nuance": "",
        "category": "personal",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestEmotionalLabel:
    """Band boundaries, stated one by one."""

    @pytest.mark.parametrize(
        "weight,expected",
        [
            (-10, "[TRAUMA/DOULEUR]"),
            (-8, "[TRAUMA/DOULEUR]"),
            (-7, "[TRAUMA/DOULEUR]"),  # inclusive lower band
            (-6, "[NÉGATIF]"),
            (-3, "[NÉGATIF]"),  # inclusive
            (-2, "[NEUTRE]"),
            (0, "[NEUTRE]"),
            (2, "[NEUTRE]"),
            (3, "[POSITIF]"),  # inclusive
            (6, "[POSITIF]"),
            (7, "[TRÈS POSITIF]"),  # inclusive
            (10, "[TRÈS POSITIF]"),
        ],
    )
    def test_each_band_boundary(self, weight: int, expected: str) -> None:
        assert _get_emotional_label(weight) == expected

    def test_the_bands_partition_the_whole_range(self) -> None:
        """No weight in -10..10 may fall through to nothing."""
        labels = {_get_emotional_label(w) for w in range(-10, 11)}

        assert labels == NEGATIVE_LABELS | {"[NEUTRE]", "[POSITIF]", "[TRÈS POSITIF]"}

    def test_the_scale_is_monotonic(self) -> None:
        """A more positive weight never yields a more negative band."""
        order = ["[TRAUMA/DOULEUR]", "[NÉGATIF]", "[NEUTRE]", "[POSITIF]", "[TRÈS POSITIF]"]
        ranks = [order.index(_get_emotional_label(w)) for w in range(-10, 11)]

        assert ranks == sorted(ranks)


class TestMemoryLine:
    """The line the model actually reads."""

    def test_the_label_prefixes_the_content(self) -> None:
        line = _format_memory_item(_memory(content="aime le jazz", emotional_weight=5), 0.9)

        assert line == "- [POSITIF] aime le jazz"

    def test_no_nuance_means_no_suffix(self) -> None:
        line = _format_memory_item(_memory(usage_nuance=""), 0.9)

        assert "→" not in line
        assert "OBLIGATION" not in line

    def test_a_neutral_nuance_is_an_informational_hint(self) -> None:
        line = _format_memory_item(
            _memory(emotional_weight=1, usage_nuance="en parler légèrement"), 0.9
        )

        assert "→ *en parler légèrement*" in line
        assert "OBLIGATION" not in line

    def test_a_sensitivity_memory_is_an_obligation_whatever_its_weight(self) -> None:
        """The category alone binds the model, even on a positive weight."""
        line = _format_memory_item(
            _memory(emotional_weight=8, category="sensitivity", usage_nuance="ne jamais aborder"),
            0.9,
        )

        assert "**⚠ OBLIGATION :** ne jamais aborder" in line
        assert "→" not in line

    @pytest.mark.parametrize("weight", [-3, -5, -10])
    def test_a_negative_memory_is_an_obligation(self, weight: int) -> None:
        line = _format_memory_item(
            _memory(emotional_weight=weight, usage_nuance="rester délicat"), 0.9
        )

        assert "**⚠ OBLIGATION :** rester délicat" in line

    def test_missing_content_and_nuance_do_not_break_the_line(self) -> None:
        """Nullable columns: the profile must still be assemblable."""
        line = _format_memory_item(
            _memory(content=None, usage_nuance=None, category=None, emotional_weight=0), 0.9
        )

        assert line == "- [NEUTRE] "


class TestLabelAndObligationAgree:
    """The coupling: every negatively-labelled memory binds the model."""

    @pytest.mark.parametrize("weight", list(range(-10, 11)))
    def test_a_negative_label_always_comes_with_an_obligation(self, weight: int) -> None:
        line = _format_memory_item(_memory(emotional_weight=weight, usage_nuance="nuance"), 0.9)
        label = _get_emotional_label(weight)

        if label in NEGATIVE_LABELS:
            assert "OBLIGATION" in line, (
                f"weight {weight} reads as {label} but its nuance is only a hint — "
                "the two thresholds have drifted apart"
            )
        else:
            assert "OBLIGATION" not in line
