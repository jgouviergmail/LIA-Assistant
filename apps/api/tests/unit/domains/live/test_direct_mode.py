"""The DIRECT live session (ADR-300 wave 4): the phone's line in the browser.

The voice holds LIA's read-only tools itself and never delegates: the start
renders the direct mandate and declares the derived tool set, refuses a model
whose wire carries no tool schema, and the tool door runs one lookup per call
under the session's own budget — every refusal a sentence the voice says.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import settings
from src.core.constants import LIVE_DIRECT_TRANSCRIPT_MAX_ROWS, LIVE_SESSION_RECORD_GRACE_SECONDS
from src.core.i18n_live import get_live_phrases
from src.domains.agents.telephony.live_tools import LiveToolSpec, VoiceToolHost
from src.domains.live import direct_mandate as dm
from src.domains.live.errors import LiveRefusedError
from src.domains.live.preferences import LivePreferences
from src.domains.live.providers import setup_inputs_from_dict, setup_inputs_to_dict
from src.domains.live.providers.protocol import LiveModelCapabilities
from src.domains.live.schemas import (
    LiveEndRequest,
    LiveToolCallRequest,
    LiveTurnRequest,
    LiveUsage,
)
from tests.unit.domains.live.test_service import (
    CLOSING,
    MODULE,
    USER,
    _connector,
    _fake_provider,
    _now,
    _record,
    _service,
)

pytestmark = pytest.mark.unit

DM = "src.domains.live.direct_mandate"
DOOR = "src.domains.live.tool_door"
#: The shared admission the door runs (ADR-301): the runner and the derivation are bound THERE.
ADMISSION = "src.domains.agents.telephony.voice_lookup"

EVENTS = LiveToolSpec("get_events_tool", "event", "agenda", ("query",))
EMAILS = LiveToolSpec("get_emails_tool", "email", "emails", ("query",))
MEMORIES = LiveToolSpec("recall_memories", "context", "memories", (), True)


def _direct_user(**overrides: object) -> SimpleNamespace:
    fields = {**vars(USER), "phone_disabled_domains": ["email"]}
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _direct_provider() -> object:
    provider = _fake_provider()
    provider.capabilities_of.side_effect = lambda model: LiveModelCapabilities(
        async_delegation=True,
        delivery_scheduling=True,
        reports_idle=False,
        cancels_on_interruption=True,
        configurable_vad=True,
        resumes=True,
        thinking=False,
        direct_tools=True,
    )
    return provider


# -- start ---------------------------------------------------------------------


async def test_a_direct_start_declares_the_tools_and_no_delegation() -> None:
    service, _, _ = _service(_connector())
    provider = _direct_provider()
    specs = AsyncMock(return_value=(EVENTS, MEMORIES))
    context = AsyncMock(return_value="AGENDA\n- Dentist tomorrow at 9.")
    declaration = {
        "name": "get_events_tool",
        "description": "Reads the agenda.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }
    with (
        patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}),
        patch(f"{DM}.direct_tool_specs", specs),
        patch(f"{DM}.direct_context", context),
        patch(f"{DM}.function_declaration", lambda spec: {**declaration, "name": spec.name}),
    ):
        response = await service.start(
            _direct_user(),
            language="fr",
            timezone="Europe/Paris",
            display_name="Alex",
            mode="direct",
        )
    assert response.mode == "direct"
    # The person's own switches narrow the declared set (the phone's rule).
    specs.assert_awaited_once_with(frozenset({"email"}))
    inputs = provider.mint.call_args.args[1]
    assert inputs.tool_declaration is None
    assert [tool["name"] for tool in inputs.direct_tools] == ["get_events_tool", "recall_memories"]
    # The mandate is the direct one, with the context block and the domains in words.
    assert "DIRECT real-time spoken session" in inputs.system_instruction
    assert "Dentist tomorrow at 9." in inputs.system_instruction
    assert "never act" in inputs.system_instruction
    # The record kept what a reconnection re-mints from, both shapes intact.
    assert setup_inputs_from_dict(setup_inputs_to_dict(inputs)) == inputs


async def test_a_direct_start_is_refused_where_the_wire_carries_no_tool_schema() -> None:
    # GPT-Live delegates natively and declares nothing: `direct_tools` False.
    service, store, _ = _service(_connector())
    provider = _fake_provider()
    with patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}):
        with pytest.raises(LiveRefusedError) as raised:
            await service.start(
                _direct_user(),
                language="fr",
                timezone="Europe/Paris",
                display_name="Alex",
                mode="direct",
            )
    assert raised.value.status_code == 409 and raised.value.code == "mode_unsupported"
    assert raised.value.detail["message"] == get_live_phrases("fr")["mode_unsupported"]
    # Refused before any claim: nothing to release, nothing minted.
    store.claim.assert_not_awaited()
    provider.mint.assert_not_awaited()


async def test_a_delegated_start_is_unchanged_by_the_mode_field() -> None:
    service, _, _ = _service(_connector())
    provider = _fake_provider()
    with patch(f"{MODULE}.PROVIDERS", {"gemini_live": provider}):
        response = await service.start(
            USER, language="fr", timezone="Europe/Paris", display_name="Alex", mode="delegated"
        )
    assert response.mode == "delegated"
    inputs = provider.mint.call_args.args[1]
    assert inputs.tool_declaration is not None and inputs.direct_tools == ()


# -- nothing recorded turn by turn; relayed at the end ---------------------------
#
# Owner decisions 2026-09-19 and 2026-09-20 (ADR-301): a direct session keeps
# no `live_turn` row (the row the next written turn would carry into the graph
# and its extractors) and runs no learning pass of its own — its exchanges are
# KEPT in the record and become, at the end, the message the person would
# have typed, relayed as their own turn; that turn learns. The card claims no
# figure it does not hold and says the relay's fate.


async def test_a_direct_session_keeps_its_turns_in_the_record_and_archives_none() -> None:
    service, store, archive = _service(_connector(), record=_direct_record())
    response = await service.archive_turn(
        USER,
        "s" * 32,
        LiveTurnRequest(user_text="hello", assistant_text="hi", started_at=_now(), ended_at=_now()),
        language="fr",
    )
    assert response.user_message_id is None and response.assistant_message_id is None
    archive.assert_not_awaited()
    assert store.kept_turns == [("user", "hello"), ("assistant", "hi")]
    kwargs = store.append_turns.call_args.kwargs
    assert kwargs["max_rows"] == LIVE_DIRECT_TRANSCRIPT_MAX_ROWS
    assert kwargs["ttl_seconds"] >= 1


async def test_a_direct_session_ends_by_relaying_its_words_as_the_person_s_turn() -> None:
    record = _direct_record()
    service, store, archive = _service(_connector(), record=record)
    store.kept_turns.extend([("user", "remind me to call the bank"), ("assistant", "noted")])
    usage = LiveUsage(
        tokens_in=3, tokens_out=1, tokens_cache=0, cost_eur=0.02, google_api_requests=1
    )
    with (
        patch(f"{CLOSING}.session_run_ids", AsyncMock(return_value=[])),
        # Even a row that somehow exists is handed to no extractor.
        patch(f"{CLOSING}.session_voice_rows", AsyncMock(return_value=[("user", "a")])),
        patch(f"{CLOSING}.count_voice_turns", AsyncMock(return_value=0)),
        patch(f"{CLOSING}.aggregate_usage", AsyncMock(return_value=usage)) as aggregate,
        patch(f"{CLOSING}.record_decision", AsyncMock()),
        patch(f"{CLOSING}.schedule_voice_learning", AsyncMock()) as learning,
        patch(f"{CLOSING}.synthesize_relay", AsyncMock()) as synth,
        patch(f"{CLOSING}.safe_fire_and_forget") as scheduled,
    ):
        response = await service.end(USER, "s" * 32, LiveEndRequest(outcome="ended"), language="fr")
    learning.assert_not_awaited()
    # No model inside the request: the synthesis AND the relayed turn run in a
    # task the closing owns, handed the KEPT turns; the end answers now.
    synth.assert_not_awaited()
    scheduled.assert_called_once()
    settle = scheduled.call_args.args[0]
    assert settle.cr_code.co_name == "_settle_direct_relay"
    assert settle.cr_frame.f_locals["transcript"].lines() == [
        "user: remind me to call the bank",
        "agent: noted",
    ]
    settle.close()
    assert response.relay == "scheduled"
    # The lookups' spend is filed under the session's OWN run id (the tool
    # host's `spend_run_id`): the card adds it up, in both modes.
    assert aggregate.call_args.args[1] == [record.run_id]
    assert response.usage and response.usage.cost_eur == 0.02
    metadata = archive.call_args.kwargs["metadata"]["live_summary"]
    assert metadata["mode"] == "direct" and metadata["relay"] == "scheduled"
    # The Markdown fallback claims no exchange count and says the fate.
    content = archive.call_args.kwargs["content"]
    assert content.startswith("**Session live** — terminée par toi · ")
    assert "échange" not in content and "0.0200" in content
    assert get_live_phrases("fr")["relay_scheduled"] in content
    store.release.assert_awaited_once_with(USER.id, "tok")


async def test_a_direct_session_with_nothing_to_say_relays_nothing() -> None:
    service, _, archive = _service(_connector(), record=_direct_record())
    with (
        patch(f"{CLOSING}.session_run_ids", AsyncMock(return_value=[])),
        patch(f"{CLOSING}.session_voice_rows", AsyncMock(return_value=[])),
        patch(f"{CLOSING}.count_voice_turns", AsyncMock(return_value=0)),
        patch(f"{CLOSING}.aggregate_usage", AsyncMock(return_value=None)),
        patch(f"{CLOSING}.record_decision", AsyncMock()),
        patch(f"{CLOSING}.synthesize_relay", AsyncMock()) as synth,
        patch(f"{CLOSING}.safe_fire_and_forget") as scheduled,
    ):
        response = await service.end(USER, "s" * 32, LiveEndRequest(outcome="ended"), language="fr")
    synth.assert_not_awaited()
    scheduled.assert_not_called()
    assert response.relay == "empty"
    assert archive.call_args.kwargs["metadata"]["live_summary"]["relay"] == "empty"


async def test_a_direct_session_s_slot_is_released_before_any_model_runs() -> None:
    """The claim goes with the end (the person may start again at once): the
    synthesis a slow provider could hold for a minute never stands in the way."""
    service, store, _ = _service(_connector(), record=_direct_record())
    store.kept_turns.append(("user", "hello"))
    order: list[str] = []
    store.release = AsyncMock(side_effect=lambda *_a: order.append("released") or True)
    with (
        patch(f"{CLOSING}.session_run_ids", AsyncMock(return_value=[])),
        patch(f"{CLOSING}.session_voice_rows", AsyncMock(return_value=[])),
        patch(f"{CLOSING}.count_voice_turns", AsyncMock(return_value=0)),
        patch(f"{CLOSING}.aggregate_usage", AsyncMock(return_value=None)),
        patch(f"{CLOSING}.record_decision", AsyncMock()),
        patch(
            f"{CLOSING}.synthesize_relay",
            AsyncMock(side_effect=lambda **_k: order.append("synthesised")),
        ) as synth,
        patch(f"{CLOSING}.safe_fire_and_forget", lambda coro, **_k: coro.close()),
    ):
        await service.end(USER, "s" * 32, LiveEndRequest(outcome="ended"), language="fr")
    synth.assert_not_awaited()
    assert order == ["released"]


async def test_a_delegated_session_s_card_adds_the_session_s_own_run_to_the_delegated_ones() -> (
    None
):
    record = _record(USER.id)
    service, _, archive = _service(_connector(), record=record)
    with (
        patch(f"{CLOSING}.session_run_ids", AsyncMock(return_value=["r1"])),
        patch(f"{CLOSING}.session_voice_rows", AsyncMock(return_value=[])),
        patch(f"{CLOSING}.count_voice_turns", AsyncMock(return_value=0)),
        patch(f"{CLOSING}.aggregate_usage", AsyncMock(return_value=None)) as aggregate,
        patch(f"{CLOSING}.record_decision", AsyncMock()),
        patch(f"{CLOSING}.schedule_voice_learning", AsyncMock()) as learning,
    ):
        await service.end(USER, "s" * 32, LiveEndRequest(outcome="ended"), language="fr")
    assert aggregate.call_args.args[1] == ["r1", record.run_id]
    learning.assert_awaited_once()
    assert archive.call_args.kwargs["metadata"]["live_summary"]["mode"] == "delegated"


# -- the tool door ---------------------------------------------------------------


def _direct_record() -> object:
    record = _record(USER.id)
    return replace(record, mode="direct")


async def _run(service: object, name: str = "get_events_tool", **arguments: object) -> object:
    return await service.run_tool(  # type: ignore[attr-defined]
        _direct_user(),
        "s" * 32,
        LiveToolCallRequest(name=name, arguments=arguments),
        language="fr",
        timezone="Europe/Paris",
        display_name="Alex",
    )


async def test_the_door_refuses_a_delegated_session_with_a_sentence() -> None:
    service, store, _ = _service(_connector(), record=_record(USER.id))
    store.consume_tool_budget = AsyncMock(return_value=True)
    with patch(f"{ADMISSION}.run_live_tool", AsyncMock()) as runner:
        response = await _run(service)
    assert response.ok is False and response.text == dm.refusal_line("refused_mode")
    runner.assert_not_awaited()
    store.consume_tool_budget.assert_not_awaited()


async def test_the_door_refuses_a_tool_the_session_did_not_declare() -> None:
    service, store, _ = _service(_connector(), record=_direct_record())
    store.consume_tool_budget = AsyncMock(return_value=True)
    with (
        patch(f"{ADMISSION}.spec_for", lambda name: {"get_events_tool": EVENTS}.get(name)),
        patch(f"{DOOR}.direct_tool_specs", AsyncMock(return_value=(MEMORIES,))),
        patch(f"{ADMISSION}.run_live_tool", AsyncMock()) as runner,
    ):
        # Declared in the catalogue, but the person switched its domain off.
        offered_elsewhere = await _run(service, "get_events_tool")
        # Not a derived tool at all (a mutation the model invented).
        unknown = await _run(service, "send_email_tool")
    for response in (offered_elsewhere, unknown):
        assert response.ok is False and response.text == dm.refusal_line("refused_tool")
    runner.assert_not_awaited()
    # A refused tool spends none of the budget.
    store.consume_tool_budget.assert_not_awaited()


async def test_the_door_refuses_past_the_session_s_budget() -> None:
    service, store, _ = _service(_connector(), record=_direct_record())
    store.consume_tool_budget = AsyncMock(return_value=False)
    with (
        patch(f"{ADMISSION}.spec_for", lambda name: EVENTS),
        patch(f"{DOOR}.direct_tool_specs", AsyncMock(return_value=(EVENTS,))),
        patch(f"{ADMISSION}.run_live_tool", AsyncMock()) as runner,
    ):
        response = await _run(service, query="tomorrow")
    assert response.ok is False and response.text == dm.refusal_line("budget_exhausted")
    runner.assert_not_awaited()
    kwargs = store.consume_tool_budget.call_args.kwargs
    assert kwargs["limit"] == settings.live_direct_tool_calls_max
    # The counter lives as long as the record: to its cap plus the grace.
    assert 0 < kwargs["ttl_seconds"] <= 5 * 60 + LIVE_SESSION_RECORD_GRACE_SECONDS


async def test_the_door_runs_a_declared_tool_under_the_session_s_host() -> None:
    service, store, _ = _service(_connector(), record=_direct_record())
    store.consume_tool_budget = AsyncMock(return_value=True)
    runner = AsyncMock(return_value="Two events tomorrow: the dentist at nine, lunch at noon.")
    with (
        patch(f"{ADMISSION}.spec_for", lambda name: EVENTS),
        patch(f"{DOOR}.direct_tool_specs", AsyncMock(return_value=(EVENTS,))),
        patch(f"{ADMISSION}.run_live_tool", runner),
    ):
        response = await _run(service, query="tomorrow")
    assert response.ok is True and response.text.startswith("Two events tomorrow")
    args, kwargs = runner.call_args
    assert args == (EVENTS, {"query": "tomorrow"})
    assert kwargs["user_id"] == USER.id and kwargs["language"] == "fr"
    host = kwargs["host"]
    assert host == VoiceToolHost.live_session("s" * 32, "live_session_" + "s" * 32)
    assert host.surface == "live_session" and host.spend_node == "live_session_tool"


async def test_the_door_answers_not_found_for_another_session() -> None:
    service, _, _ = _service(_connector(), record=_direct_record())
    with pytest.raises(LiveRefusedError) as raised:
        await service.run_tool(
            _direct_user(),
            "z" * 32,
            LiveToolCallRequest(name="get_events_tool"),
            language="fr",
            timezone="Europe/Paris",
            display_name="Alex",
        )
    assert raised.value.status_code == 404


# -- the direct mandate ----------------------------------------------------------


def _inputs(**overrides: object) -> dm.DirectMandateInputs:
    base: dict[str, object] = {
        "language": "fr",
        "user_name": "Alex",
        "personality": "",
        "now": datetime(2026, 9, 19, 8, 30, tzinfo=UTC),
        "timezone": "Europe/Paris",
        "psyche_block": "",
        "user_context": "",
        "tool_domains": (),
    }
    base.update(overrides)
    return dm.DirectMandateInputs(**base)  # type: ignore[arg-type]


def test_the_mandate_names_the_domains_in_words_or_says_it_has_no_lookup() -> None:
    with_tools = dm.render_direct_mandate(_inputs(tool_domains=("event", "context")))
    assert "LOOK THINGS UP" in with_tools
    # The vocabulary's words, in the prompt's language, never the domain keys.
    assert "event," not in with_tools and "Calendar" in with_tools or "Agenda" in with_tools
    assert "no lookup on this session" not in with_tools
    without = dm.render_direct_mandate(_inputs())
    assert "no lookup on this session" in without and "LOOK THINGS UP" not in without
    # French is asked for unmistakably, and the clock is the person's own.
    assert "RESPOND IN French" in without and "Europe/Paris" in without


def test_the_mandate_carries_the_context_or_says_none_was_shared() -> None:
    bare = dm.render_direct_mandate(_inputs())
    assert "No context was shared" in bare
    rich = dm.render_direct_mandate(_inputs(user_context="AGENDA\n- Dentist at 9."))
    assert "Dentist at 9." in rich and "No context was shared" not in rich
    # Empty blocks collapse: no run of blank lines survives.
    assert "\n\n\n" not in bare and "\n\n\n" not in rich


def test_the_mandate_renders_the_personality_and_the_inner_state_when_present() -> None:
    rendered = dm.render_direct_mandate(
        _inputs(personality="Speak briskly.", psyche_block="INNER STATE: calm")
    )
    assert "Speak briskly." in rendered and "INNER STATE: calm" in rendered


def test_every_placeholder_of_the_direct_prompt_is_produced() -> None:
    # A placeholder nobody fills reaches the model as `{name}` (ADR-284).
    rendered = dm.render_direct_mandate(_inputs(tool_domains=("event",), user_context="x"))
    assert "{" not in rendered and "}" not in rendered


def test_the_refusal_lines_are_the_ones_the_door_hands_back() -> None:
    lines = dm.direct_lines()
    assert set(dm.REFUSAL_LINE_KEYS) <= set(lines)
    for key in dm.REFUSAL_LINE_KEYS:
        assert dm.refusal_line(key) == lines[key] and lines[key].strip()


def test_tool_domains_are_distinct_and_first_seen_first() -> None:
    assert dm.tool_domains((EVENTS, EMAILS, MEMORIES, EVENTS)) == ("event", "email", "context")
    assert dm.tool_domains(()) == ()


async def test_direct_tool_specs_pass_the_live_gate_not_the_telephony_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    available = AsyncMock(return_value=(EVENTS,))
    monkeypatch.setattr(dm, "available_live_tools", available)
    assert await dm.direct_tool_specs(frozenset({"email"})) == (EVENTS,)
    available.assert_awaited_once_with(disabled_domains=frozenset({"email"}), feature_enabled=True)


async def test_build_direct_setup_inputs_assembles_the_mandate_the_tools_and_the_budgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dm, "direct_tool_specs", AsyncMock(return_value=(EVENTS, MEMORIES)))
    monkeypatch.setattr(dm, "direct_context", AsyncMock(return_value="AGENDA\n- x"))
    monkeypatch.setattr(
        dm,
        "function_declaration",
        lambda spec: {"name": spec.name, "description": "d", "parameters": {}},
    )
    inputs = await dm.build_direct_setup_inputs(
        user_id=uuid.uuid4(),
        model="gemini-3.8-live",
        voice="Kore",
        thinking_level="low",
        preferences=LivePreferences(),
        disabled_domains=frozenset(),
        language="fr",
        timezone="Europe/Paris",
        display_name="Alex",
        now=datetime(2026, 9, 19, 8, 30, tzinfo=UTC),
        personality="",
        psyche_block="",
    )
    assert inputs.model == "gemini-3.8-live" and inputs.voice == "Kore"
    assert inputs.thinking_level == "low"
    assert inputs.tool_declaration is None
    assert [tool["name"] for tool in inputs.direct_tools] == ["get_events_tool", "recall_memories"]
    assert inputs.trigger_tokens == settings.live_context_trigger_tokens
    assert inputs.target_tokens == settings.live_context_target_tokens
    assert "AGENDA\n- x" in inputs.system_instruction
