"""The one admission of a voice lookup (ADR-301): offered, then the budget, then the run."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

import src.domains.agents.telephony.voice_lookup as vl
from src.domains.agents.telephony.live_tools import LiveToolSpec, VoiceToolHost

pytestmark = pytest.mark.unit

EVENTS = LiveToolSpec("get_events_tool", "event", "event", ("query",))
MEMORIES = LiveToolSpec("recall_memories", "context", "memories", (), True)
HOST = VoiceToolHost.live_session("s" * 32, "live_session_" + "s" * 32)


def _wire(
    monkeypatch: pytest.MonkeyPatch, *, budget: bool = True, text: str = "Two events."
) -> dict[str, Any]:
    seen: dict[str, Any] = {"budget_asked": 0, "ran": []}

    async def _consume() -> bool:
        seen["budget_asked"] += 1
        return budget

    async def _run(spec, args, **kwargs):  # noqa: ANN001, ANN003
        seen["ran"].append((spec, args, kwargs))
        return text

    monkeypatch.setattr(vl, "spec_for", lambda name: {"get_events_tool": EVENTS}.get(name))
    monkeypatch.setattr(vl, "run_live_tool", _run)
    seen["consume"] = _consume
    return seen


async def _serve(seen: dict[str, Any], name: str, offered: tuple[LiveToolSpec, ...], **args: Any):
    return await vl.serve_voice_lookup(
        name,
        args,
        offered=offered,
        consume_budget=seen["consume"],
        user_id=uuid4(),
        language="fr",
        timezone="Europe/Paris",
        display_name="Alex",
        host=HOST,
    )


async def test_a_tool_the_voice_was_not_offered_is_refused_before_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _wire(monkeypatch)
    # Derived, but the person switched its domain off for their voice.
    switched_off = await _serve(seen, "get_events_tool", (MEMORIES,), query="tomorrow")
    # Not derived at all: a mutation the model invented.
    invented = await _serve(seen, "send_email_tool", (EVENTS, MEMORIES))
    for verdict in (switched_off, invented):
        assert verdict.refusal is vl.LookupRefusal.NOT_OFFERED
        assert verdict.admitted is False and verdict.spec is None and verdict.text == ""
    # A refused tool spends nothing: the budget is asked AFTER the offer.
    assert seen["budget_asked"] == 0
    assert seen["ran"] == []


async def test_a_spent_budget_refuses_and_names_the_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _wire(monkeypatch, budget=False)
    verdict = await _serve(seen, "get_events_tool", (EVENTS,), query="tomorrow")
    assert verdict.refusal is vl.LookupRefusal.BUDGET
    assert verdict.spec == EVENTS and verdict.text == ""
    assert seen["budget_asked"] == 1
    assert seen["ran"] == []


async def test_an_admitted_lookup_runs_under_the_host_and_hands_its_text_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _wire(monkeypatch, text="Two events tomorrow: the dentist at nine, lunch at noon.")
    verdict = await _serve(seen, "get_events_tool", (EVENTS, MEMORIES), query="tomorrow")
    assert verdict.admitted is True and verdict.refusal is None
    assert verdict.spec == EVENTS
    assert verdict.text.startswith("Two events tomorrow")
    assert seen["budget_asked"] == 1
    spec, args, kwargs = seen["ran"][0]
    assert spec == EVENTS and args == {"query": "tomorrow"}
    assert kwargs["host"] == HOST
    assert kwargs["language"] == "fr" and kwargs["display_name"] == "Alex"


def test_the_refusal_vocabulary_is_the_doors_metric_outcome() -> None:
    """The two doors count a refusal under the enum's value: keep them stable."""
    assert {r.value for r in vl.LookupRefusal} == {"refused_tool", "budget_exceeded"}
