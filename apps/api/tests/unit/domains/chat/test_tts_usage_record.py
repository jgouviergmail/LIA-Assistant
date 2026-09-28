"""A synthesis is priced on the units its vendor bills — characters, or tokens."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domains.chat import tracking_records
from src.domains.chat.tracking_records import tts_usage_record
from src.domains.voice.billing import SynthesisResult, synthesize_billed

pytestmark = pytest.mark.unit


@pytest.fixture
def priced(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Record what the pricing cache is asked, at the module that asks it."""
    asked: list[dict[str, object]] = []

    def fake_cost(**kwargs: object) -> tuple[float, float]:
        asked.append(kwargs)
        return 0.02, 0.018

    monkeypatch.setattr(tracking_records, "get_cached_cost_usd_eur", fake_cost)
    monkeypatch.setattr(tracking_records, "get_cached_usd_eur_rate", lambda: 0.9)
    return asked


def test_a_character_billed_engine_is_priced_per_character(
    priced: list[dict[str, object]],
) -> None:
    record = tts_usage_record("openai", "tts-model", 510, 12.5)
    assert priced == [
        {
            "model": "tts-model",
            "prompt_tokens": 510,
            "completion_tokens": 0,
            "cached_tokens": 0,
            "cache_write_tokens": 0,
        }
    ]
    assert (record.characters, record.cost_eur, record.usd_to_eur_rate) == (
        510,
        Decimal("0.018"),
        Decimal("0.9"),
    )


def test_a_token_billed_engine_is_priced_on_its_usage_report(
    priced: list[dict[str, object]],
) -> None:
    record = tts_usage_record("gemini", "gemini-tts", 510, input_tokens=125, output_tokens=949)
    assert priced[0]["prompt_tokens"] == 125
    assert priced[0]["completion_tokens"] == 949
    assert record.characters == 510  # still shown, never billed


def test_half_a_usage_report_falls_back_to_characters(
    priced: list[dict[str, object]],
) -> None:
    tts_usage_record("gemini", "gemini-tts", 510, input_tokens=125, output_tokens=None)
    assert priced[0]["prompt_tokens"] == 510


class _PlainClient:
    """A character-billed client: bytes, no usage report."""

    provider_name = "openai"
    audio_format = "mp3"

    async def synthesize(self, text: str, voice_name: str | None = None, **_: object) -> bytes:
        return b"mp3:" + text.encode()

    async def synthesize_base64(self, text: str, voice_name: str | None = None, **_: object) -> str:
        return ""

    async def close(self) -> None:
        return None


async def test_a_plain_client_is_billed_on_what_was_sent() -> None:
    result = await synthesize_billed(_PlainClient(), "Bonjour.", "nova")
    assert result == SynthesisResult(audio=b"mp3:Bonjour.", characters=8)
