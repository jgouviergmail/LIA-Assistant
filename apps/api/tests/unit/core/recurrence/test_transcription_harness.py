"""The measurement's own arithmetic, checked without a provider.

`measure_transcription.py` calls a real model, so it is a script and never a
gate. But the half that DECIDES — turning what a model produced into wall
clocks and comparing them — is pure, and a comparator that is wrong would
publish a wrong number with a date and a model name beside it, which is worse
than publishing nothing.

Two properties matter more than the rest:

- **the oracle is the instants**, so a parameter set that says the same thing
  differently counts as right;
- **a parameter set the translation refuses reads as a miss**, never as a
  crash that would abort the run halfway through the corpus.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = (
    Path(__file__).resolve().parents[4] / "scripts" / "recurrence" / "measure_transcription.py"
)


def _harness() -> Any:
    """Load the script as a module — it lives outside the package on purpose."""
    spec = importlib.util.spec_from_file_location("measure_transcription", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HARNESS = _harness()
CORPUS = json.loads(
    (Path(__file__).parent / "transcription_corpus.json").read_text(encoding="utf-8")
)
FAMILIES = {f["id"]: f for f in CORPUS["families"]}


class TestTheComparatorIsHonest:
    def test_the_corpus_own_parameters_score_exact(self) -> None:
        """The floor: what the corpus says is right must read as right."""
        for family in CORPUS["families"]:
            got = HARNESS._instants_of(dict(family["params"]), family, CORPUS)
            assert got == family["expect"], family["id"]

    def test_a_different_wording_of_the_same_schedule_also_scores_exact(self) -> None:
        """A model that says weekdays explicitly where the corpus says 'daily'
        is not wrong. Comparing FIELDS would report a failure for a right
        answer — the invented diagnosis ADR-182 removed."""
        family = FAMILIES["weekdays-named-set"]
        as_written = HARNESS._instants_of(dict(family["params"]), family, CORPUS)
        spelled_out = HARNESS._instants_of(
            {"repeat": "weekly", "weekdays": [5, 4, 3, 2, 1], "times": ["09:00"]},
            family,
            CORPUS,
        )
        assert spelled_out == as_written

    def test_a_wrong_schedule_scores_wrong(self) -> None:
        """A comparator that never fails measures nothing."""
        family = FAMILIES["weekdays-named-set"]
        weekend_instead = HARNESS._instants_of(
            {"repeat": "weekly", "weekdays": [6, 7], "times": ["09:00"]}, family, CORPUS
        )
        assert weekend_instead != family["expect"]

    def test_the_classic_trap_is_actually_distinguished(self) -> None:
        """'Every 15 days' against 'the 15th': the corpus is only useful if the
        comparator can tell them apart."""
        family = FAMILIES["fortnight-days-trap"]
        as_day_of_month = HARNESS._instants_of(
            {"repeat": "monthly", "month_days": [15], "times": ["09:00"]}, family, CORPUS
        )
        assert as_day_of_month != family["expect"]


class TestAnUnusableAnswerIsAMissNotACrash:
    """The corpus has a hundred lines; one bad answer must not end the run."""

    def test_an_impossible_combination_reads_as_empty(self) -> None:
        family = FAMILIES["daily-single"]
        assert HARNESS._instants_of({"repeat": "weekly", "times": ["08:00"]}, family, CORPUS) == []

    def test_an_unknown_parameter_reads_as_empty(self) -> None:
        family = FAMILIES["daily-single"]
        assert (
            HARNESS._instants_of(
                {"repeat": "daily", "times": ["08:00"], "invented": True}, family, CORPUS
            )
            == []
        )

    def test_a_malformed_time_reads_as_empty(self) -> None:
        family = FAMILIES["daily-single"]
        assert HARNESS._instants_of({"repeat": "daily", "times": ["8h"]}, family, CORPUS) == []


class TestWhatTheModelIsTold:
    def test_the_vocabulary_is_the_one_the_tools_publish(self) -> None:
        """Measuring a prompt nobody ships answers a question nobody asked."""
        from src.domains.agents.registry.recurrence_parameters import RECURRENCE_DOCS

        vocabulary = HARNESS._vocabulary()
        for name, doc in RECURRENCE_DOCS.items():
            assert name in vocabulary
            assert doc in vocabulary
