"""The live tests run against a PRIMED pricing cache (ADR-300 wave 3).

A live model is offered and started only when the tariff table declares it,
and the cache is the runtime's reading of that table. The fixture primes it
with the names the tests open sessions on, so a test about a credential or a
cap never fails on « model_unpriced » — and the tests about that refusal
clear the cache themselves.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from src.infrastructure.cache import pricing_cache
from src.infrastructure.cache.pricing_cache import CachedModelPrice, PricingCacheData

#: The Gemini live tier as the seed declares it: text and audio, per 1M tokens.
GEMINI_LIVE_PRICE = CachedModelPrice(
    input_unit_price=0.75,
    output_unit_price=4.5,
    cached_input_unit_price=0.0,
    pricing_unit="per_1m_tokens",
    audio_input_unit_price=3.0,
    audio_output_unit_price=12.0,
)
#: GPT-Live: a minute of session.
GPT_LIVE_PRICE = CachedModelPrice(
    input_unit_price=0.05,
    output_unit_price=0.0,
    cached_input_unit_price=0.0,
    pricing_unit="per_audio_minute",
)
PRICED_LIVE_MODELS: dict[str, CachedModelPrice] = {
    "gemini-3.8-live": GEMINI_LIVE_PRICE,
    "gemini-3.8-live-extended-thinking": GEMINI_LIVE_PRICE,
    "gpt-live-1": GPT_LIVE_PRICE,
}
USD_EUR_RATE = 0.9


@pytest.fixture(autouse=True)
def primed_pricing_cache() -> Iterator[PricingCacheData]:
    """Every live test sees the live models priced; the cache is restored after."""
    before = pricing_cache._local_cache
    primed = PricingCacheData(
        models=dict(PRICED_LIVE_MODELS), usd_eur_rate=USD_EUR_RATE, last_refresh_ts=0.0
    )
    pricing_cache._local_cache = primed
    try:
        yield primed
    finally:
        pricing_cache._local_cache = before


# ---------------------------------------------------------------------------
# The closing's archive door (ADR-301)
# ---------------------------------------------------------------------------

#: The archive mock the CLOSING writes through (the card, a phone's voice
#: rows), installed on the closing module by the autouse fixture below and
#: handed out by ``test_service._service`` — so a test reads ONE mock for
#: every row a session archives, wherever the row is written: the end of a
#: session is the shared closing's, not the service's.
CLOSING_ARCHIVE: dict[str, Any] = {}


@pytest.fixture(autouse=True)
def _closing_archive_door(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infrastructure.scheduler import voice_session_closing as closing

    async def _door(db: object, **kwargs: object) -> object:
        mock = CLOSING_ARCHIVE.get("mock")
        if mock is None:
            raise AssertionError("no archive mock installed: build the service with _service()")
        return await mock(db, **kwargs)

    monkeypatch.setattr(closing, "archive_row", _door)
