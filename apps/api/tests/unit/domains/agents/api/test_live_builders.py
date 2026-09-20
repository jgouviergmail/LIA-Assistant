"""Two more rows built by the one door (ADR-276 doctrine, ADR-299)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.core.constants import LIVE_SESSION_SUMMARY_MESSAGE_TYPE, LIVE_TURN_MESSAGE_TYPE
from src.core.field_names import FIELD_LIVE_SESSION_ID, FIELD_LIVE_SUMMARY, FIELD_RUN_ID
from src.domains.agents.api.archive_metadata import (
    build_live_session_summary_metadata,
    build_live_turn_metadata,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 18, 9, 0, tzinfo=UTC)


def test_turn_metadata() -> None:
    meta = build_live_turn_metadata(
        run_id="live_session_x", live_session_id="x" * 32, started_at=NOW, ended_at=NOW
    )
    assert meta["type"] == LIVE_TURN_MESSAGE_TYPE
    assert meta[FIELD_RUN_ID] == "live_session_x"
    assert meta[FIELD_LIVE_SESSION_ID] == "x" * 32
    assert meta["started_at"] == NOW.isoformat()
    assert meta["ended_at"] == NOW.isoformat()


def test_summary_metadata_carries_the_figures_in_the_meters_vocabulary() -> None:
    meta = build_live_session_summary_metadata(
        run_id="live_session_x",
        live_session_id="x" * 32,
        outcome="ended",
        duration_seconds=720,
        delegations=3,
        voice_turns=7,
        usage={
            "tokens_in": 10,
            "tokens_out": 5,
            "tokens_cache": 0,
            "cost_eur": 0.01,
            "google_api_requests": 0,
        },
    )
    assert meta["type"] == LIVE_SESSION_SUMMARY_MESSAGE_TYPE
    assert meta[FIELD_LIVE_SUMMARY] == {
        "outcome": "ended",
        "duration_seconds": 720,
        "delegations": 3,
        "voice_turns": 7,
        "extensions": 0,
        "mode": "delegated",
    }
    assert meta["tokens_in"] == 10 and meta["cost_eur"] == 0.01
    assert "provider" not in str(meta)
    # A DIRECT session's card names its mode: it archived no exchange to count (ADR-300 wave 4).
    direct = build_live_session_summary_metadata(
        run_id="live_session_x",
        live_session_id="x" * 32,
        outcome="ended",
        duration_seconds=60,
        delegations=0,
        voice_turns=0,
        usage=None,
        mode="direct",
    )
    assert direct[FIELD_LIVE_SUMMARY]["mode"] == "direct"


def test_summary_metadata_without_usage_carries_no_meter_keys() -> None:
    meta = build_live_session_summary_metadata(
        run_id="r",
        live_session_id="x" * 32,
        outcome="error",
        duration_seconds=1,
        delegations=0,
        voice_turns=0,
        usage=None,
    )
    assert "tokens_in" not in meta and "cost_eur" not in meta


def test_the_figures_key_is_no_origin_kind_and_survives_a_stamp() -> None:
    """The stamp writes under the origin KIND (`with_origin_stamp`): a card whose
    figures sat under `live_session` — a relayed browser turn's kind — would have
    them REPLACED if archived under that origin (review 2026-09-20). The key is
    the card's own, and the stamp lands beside it."""
    from uuid import uuid4

    from src.domains.agents.api.run_origin import RunOrigin, out_of_turn_origin_ctx
    from src.domains.voice_sessions.session import VoiceSession
    from src.domains.workboard.constants import RUN_ORIGIN_KIND

    kinds = {
        RUN_ORIGIN_KIND,
        *(
            VoiceSession.browser(
                session_id="s" * 32,
                run_id="live_session_s",
                mode="direct",
                user_id=uuid4(),
                conversation_id=uuid4(),
                language="fr",
                timezone="UTC",
            ).origin_kind,
            VoiceSession.phone(
                call_id=uuid4(),
                mode="direct",
                user_id=uuid4(),
                conversation_id=uuid4(),
                language="fr",
                timezone="UTC",
            ).origin_kind,
        ),
    }
    assert FIELD_LIVE_SUMMARY not in kinds
    origin = RunOrigin(
        kind="live_session", ticket_id="s" * 32, run_id="live_session_s", hidden=False
    )
    token = out_of_turn_origin_ctx.set(origin)
    try:
        meta = build_live_session_summary_metadata(
            run_id="live_session_s",
            live_session_id="s" * 32,
            outcome="ended",
            duration_seconds=5,
            delegations=0,
            voice_turns=0,
            usage=None,
            mode="direct",
            relay="scheduled",
        )
    finally:
        out_of_turn_origin_ctx.reset(token)
    assert meta[FIELD_LIVE_SUMMARY]["relay"] == "scheduled"
    assert meta["live_session"] == {"ticket_id": "s" * 32, "run_id": "live_session_s"}
