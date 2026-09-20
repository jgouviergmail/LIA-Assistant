"""The closing card sums every euro the platform paid under the session's runs.

``aggregate_usage`` read the model column alone, so the Maps Platform lookups
a direct session makes (ADR-300 wave 4 — Places, Routes, on the deployment's
key) were counted as requests and priced at nothing on the card. The figure is
the summary row's billed total, the same the chat meter shows.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.chat.models import MessageTokenSummary
from src.domains.voice_sessions.summary import aggregate_usage

pytestmark = pytest.mark.unit


def _row(
    run_id: str, *, llm: str, google: str, images: str = "0", requests: int = 0
) -> MessageTokenSummary:
    return MessageTokenSummary(
        user_id=uuid.uuid4(),
        session_id="live",
        run_id=run_id,
        total_prompt_tokens=100,
        total_completion_tokens=20,
        total_cached_tokens=5,
        total_cost_eur=Decimal(llm),
        google_api_requests=requests,
        google_api_cost_eur=Decimal(google),
        image_generation_cost_eur=Decimal(images),
    )


async def test_the_card_carries_the_maps_lookups_euros() -> None:
    rows = {
        "turn-1": _row("turn-1", llm="0.010", google="0"),
        "session": _row("session", llm="0.002", google="0.064", requests=2),
    }
    repo = MagicMock()
    repo.get_token_summaries_by_run_ids = AsyncMock(return_value=rows)
    with patch("src.domains.voice_sessions.summary.ChatRepository", return_value=repo):
        usage = await aggregate_usage(MagicMock(), ["turn-1", "session"])
    assert usage is not None
    assert usage.tokens_in == 200 and usage.tokens_out == 40 and usage.tokens_cache == 10
    assert usage.google_api_requests == 2
    assert usage.cost_eur == pytest.approx(0.076)


def test_the_direct_card_names_the_recap_when_the_words_could_not_become_a_turn() -> None:
    # The phone's fallback push carries the neutral recap when the relay did
    # not run; the browser's card carries the same, so the person's words are
    # never lost in silence (ADR-301 review). A relay that ran carries none.
    from src.core.i18n_live import get_live_phrases
    from src.domains.voice_sessions.summary import render_summary_markdown

    kept = render_summary_markdown(
        language="fr",
        outcome="ended",
        mode="direct",
        duration_seconds=90,
        delegations=0,
        voice_turns=0,
        usage=None,
        extensions=0,
        relay="busy",
        relay_summary="La personne a demandé un rappel jeudi.",
    )
    assert get_live_phrases("fr")["relay_busy"] in kept
    assert "La personne a demandé un rappel jeudi." in kept
    ran = render_summary_markdown(
        language="fr",
        outcome="ended",
        mode="direct",
        duration_seconds=90,
        delegations=0,
        voice_turns=0,
        usage=None,
        extensions=0,
        relay="answered",
    )
    assert get_live_phrases("fr")["summary_recap"].split("{recap}")[0].strip() not in ran


async def test_no_run_means_no_figure() -> None:
    assert await aggregate_usage(MagicMock(), []) is None
    repo = MagicMock()
    repo.get_token_summaries_by_run_ids = AsyncMock(return_value={})
    with patch("src.domains.voice_sessions.summary.ChatRepository", return_value=repo):
        assert await aggregate_usage(MagicMock(), ["turn-1"]) is None
