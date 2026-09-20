"""The relay synthesis reads the SAME context after its move (ADR-301, the ADR-269 net).

``telephony/self_call_relay.py`` became ``infrastructure/scheduler/voice_relay.py``
so that a browser direct session can be relayed like a phone call. The golden
file was captured from the phone module BEFORE the move, on one fixture
payload, and proved the move byte for byte; it now pins the contract as it
stands — the context gained a SESSION line naming the carrier (review
2026-09-20: the prompt served two lines while written for one, and its rule on
who was speaking contradicted the collected flag of an authenticated
session). The shared module must render the prompt context byte for byte,
name the same chokepoint node and the same schema. Regenerate ONLY when the
prompt contract changes on purpose:

    VOICE_RELAY_GOLDEN_WRITE=1 pytest tests/unit/infrastructure/scheduler/test_voice_relay_golden.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from src.core.config import settings
from src.domains.telephony.schemas import SelfCallRelay
from src.domains.voice_sessions.session import VoiceCarrier

pytestmark = pytest.mark.unit

GOLDEN = Path(__file__).with_name("voice_relay_golden.json")
USER_ID = UUID("00000000-0000-0000-0000-00000000abcd")

PAYLOAD = {
    "data": {
        "metadata": {"call_duration_secs": 300},
        "status": "done",
        "analysis": {
            "transcript_summary": "The person asked for a reminder and a message.",
            "data_collection_results": {
                "owner_confirmed": {"value": True},
                "requests": {"value": "a reminder to call the bank; a message to Anna"},
            },
        },
        "transcript": [
            {"role": "agent", "message": "Hello, am I speaking with Alex?", "time_in_call_secs": 0},
            {
                "role": "user",
                "message": "Yes. Remind me to call the bank tomorrow.",
                "time_in_call_secs": 3,
            },
            {"role": "agent", "message": "Noted. Anything else?", "time_in_call_secs": 6},
            {
                "role": "user",
                "message": "Send Anna a message that I am running late.",
                "time_in_call_secs": 9,
            },
        ],
    }
}


def _frozen_clock(user_timezone: str) -> str:
    return f"CURRENT DATETIME: 2026-09-20 10:00 ({user_timezone})"


async def _capture_new(monkeypatch: pytest.MonkeyPatch) -> dict:
    from src.infrastructure.scheduler import voice_relay as relay

    captured: dict = {}

    async def _fake_chokepoint(**kwargs: Any) -> SelfCallRelay:
        captured.update(kwargs)
        return SelfCallRelay(owner_confirmed=True, relay_message="m", summary="s")

    monkeypatch.setattr(relay, "current_datetime_line", _frozen_clock)
    monkeypatch.setattr(relay, "get_llm", lambda _t: object())
    monkeypatch.setattr(relay, "load_telephony_prompt", lambda name, _v: f"SYSTEM<{name}>")
    monkeypatch.setattr(
        relay,
        "get_llm_config_for_agent",
        lambda _s, _t: SimpleNamespace(provider="openai", model="gpt-4.1-mini"),
    )
    monkeypatch.setattr(relay, "get_structured_output_with_retry", _fake_chokepoint)
    monkeypatch.setattr(settings, "telephony_relay_transcript_max_tokens", 5000, raising=False)
    await relay.synthesize_relay(
        carrier=VoiceCarrier.PHONE,
        transcript=relay.transcript_of_payload(PAYLOAD),
        collected=relay.collected_of_payload(PAYLOAD),
        vendor_summary=relay.vendor_summary_of_payload(PAYLOAD),
        objective="a catch-up on the week",
        user_language="fr",
        user_timezone="Europe/Paris",
        user_id=USER_ID,
    )
    return {
        "system": captured["messages"][0].content,
        "human": captured["messages"][1].content,
        "node_name": captured["node_name"],
        "schema": captured["schema"].__name__,
        "provider": captured["provider"],
        "user_id": str(captured["user_id"]),
    }


async def test_the_shared_relay_renders_the_phone_s_golden_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered = await _capture_new(monkeypatch)
    if os.environ.get("VOICE_RELAY_GOLDEN_WRITE"):
        GOLDEN.write_text(
            json.dumps(rendered, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert rendered == golden
