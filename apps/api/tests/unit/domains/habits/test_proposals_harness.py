"""The usage-proposals harness measures the real rules and cannot rot (ADR-375).

It is a measurement, never a gate. What is pinned here is that it still
measures: a seed relives the same month, it reports what the REAL rules
produce, it reads the shipped bars and never the live settings, and its
anchors mean what they say on a handful of seeds — a person who asks for
little gets nothing, a person who never reacts is asked whether to keep the
notifications, a planner who asks every Sunday is offered a weekly routine.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from src.core import constants as C

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "habits" / "measure_proposals.py"


def _harness() -> Any:
    spec = importlib.util.spec_from_file_location("measure_proposals", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered first: its dataclasses resolve their annotations through it.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


HARNESS = _harness()


def _persona(name: str) -> Any:
    return next(persona for persona in HARNESS.PERSONAS if persona.name == name)


def test_a_seed_relives_the_same_month() -> None:
    planner = _persona("weekly_planner")
    assert HARNESS.simulate(planner, 7, 35) == HARNESS.simulate(planner, 7, 35)


def test_the_bars_are_the_shipped_defaults_never_the_live_settings() -> None:
    assert HARNESS.NEED_BARS.automate_share == C.RECURRENCE_AUTOMATE_SHARE_DEFAULT
    assert HARNESS.NEED_BARS.automate_min_days == C.RECURRENCE_AUTOMATE_MIN_DAYS_DEFAULT
    assert HARNESS.PROPOSAL_BARS.silent_min_notifications == (
        C.HABITS_PROPOSAL_SILENT_MIN_NOTIFICATIONS_DEFAULT
    )
    assert HARNESS.NIGHTS == C.RECURRENCE_WINDOW_DAYS_DEFAULT


def test_every_expectation_names_a_kind_the_rules_know() -> None:
    kinds = {kind.value for kind in HARNESS.ProposalKind}
    for persona in HARNESS.PERSONAS:
        for name in persona.expected:
            assert name.split(":", 1)[0] in kinds, (persona.name, name)


def test_the_anchors_hold_on_a_few_seeds() -> None:
    reports = {
        report.name: report
        for report in HARNESS.measure(
            [_persona(name) for name in ("sparse", "silent", "weekly_planner")], seeds=5, nights=35
        )
    }

    assert reports["sparse"].unexpected == {}
    assert reports["silent"].expected["review_notifications:heartbeat"][0] == 1.0
    assert reports["weekly_planner"].expected["automate_need:event@weekly"][0] >= 0.8
    assert reports["weekly_planner"].expected["automate_need:task@weekly"][0] >= 0.8
