"""The one door every synthesis goes through: billed in the vendor's unit, recorded once.

Three defects this closes, each measured in the code before ADR-345:

- a byte-billed engine priced per character under-bills a Chinese line three
  times (a CJK character is three UTF-8 bytes);
- the chat recorded the CONFIGURED engine's tariff even when the factory had
  substituted the free engine — a phantom cost for audio Edge produced;
- only a SERVED synthesis may reach the ledger: a refused or cancelled call
  never ran to completion, and a guess would bill it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from src.domains.voice.billing import SynthesisResult
from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.families import billed_text_units
from src.domains.voice.protocol import DialogueAudio, DialogueTurn
from src.domains.voice.spoken import speak, speak_dialogue

pytestmark = pytest.mark.unit


@dataclass
class _Ledger:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def record_tts_call(
        self,
        provider: str,
        model: str,
        characters: int,
        duration_ms: float = 0.0,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        billed_units: int | None = None,
    ) -> None:
        self.calls.append(
            {
                "provider": provider,
                "model": model,
                "characters": characters,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "billed_units": billed_units,
            }
        )


class _Client:
    """A plain client: bytes back, no usage report."""

    audio_format = "mp3"

    def __init__(self, provider: str, *, fail: Exception | None = None) -> None:
        self.provider_name = provider
        self._fail = fail
        self.calls: list[tuple[str, str | None, dict[str, object]]] = []

    async def synthesize(self, text: str, voice_name: str | None = None, **kwargs: object) -> bytes:
        self.calls.append((text, voice_name, kwargs))
        if self._fail is not None:
            raise self._fail
        return b"audio"

    async def close(self) -> None:
        return None


class _ReportingClient(_Client):
    """A token-billed client: the vendor's usage report states the units."""

    async def synthesize_with_usage(
        self, text: str, voice_name: str | None = None, **kwargs: object
    ) -> SynthesisResult:
        self.calls.append((text, voice_name, kwargs))
        return SynthesisResult(audio=b"wav", characters=len(text), input_tokens=7, output_tokens=90)


class TestBilledTextUnits:
    @pytest.mark.parametrize(
        ("text", "characters"), [("abc", 3), ("été", 3), ("你好", 2), ("ok 👍", 4)]
    )
    def test_a_character_billed_engine_counts_code_points(self, text: str, characters: int) -> None:
        assert billed_text_units("openai", text) == characters

    @pytest.mark.parametrize(("text", "size"), [("abc", 3), ("été", 5), ("你好", 6), ("ok 👍", 7)])
    def test_a_byte_billed_engine_counts_utf8_bytes(self, text: str, size: int) -> None:
        assert billed_text_units("fishaudio", text) == size

    def test_a_free_engine_bills_nothing(self) -> None:
        assert billed_text_units("edge", "Bonjour.") == 0

    def test_a_token_billed_engine_leaves_the_units_to_its_report(self) -> None:
        assert billed_text_units("gemini", "Bonjour.") is None

    def test_an_unknown_engine_is_priced_like_characters(self) -> None:
        assert billed_text_units("azure", "Bonjour.") == 8


class TestTheDoor:
    async def test_a_served_synthesis_is_recorded_once_in_the_vendors_unit(self) -> None:
        ledger = _Ledger()
        client = _Client("fishaudio")

        result = await speak(client, "你好", "v1", model="m1", ledger=ledger, speed=1.1)

        assert result.audio == b"audio"
        assert client.calls == [("你好", "v1", {"speed": 1.1})]
        assert ledger.calls == [
            {
                "provider": "fishaudio",
                "model": "m1",
                "characters": 2,
                "input_tokens": None,
                "output_tokens": None,
                "billed_units": 6,
            }
        ]

    async def test_a_token_billed_synthesis_is_recorded_on_its_reported_tokens(self) -> None:
        ledger = _Ledger()

        await speak(_ReportingClient("gemini"), "Bonjour.", "Kore", model="g1", ledger=ledger)

        assert ledger.calls[0]["input_tokens"] == 7
        assert ledger.calls[0]["output_tokens"] == 90
        assert ledger.calls[0]["billed_units"] is None

    async def test_the_free_engine_records_nothing(self) -> None:
        ledger = _Ledger()

        await speak(_Client("edge"), "Bonjour.", "Remy", model="edge-tts", ledger=ledger)

        assert ledger.calls == []

    async def test_a_substituted_engine_never_bills_the_configured_one(self) -> None:
        """The factory hands Edge to a lenient caller whose engine cannot be served:
        the line Edge spoke must not cost the configured paid model."""
        ledger = _Ledger()

        await speak(_Client("edge"), "Bonjour.", "Remy", model="eleven_v4", ledger=ledger)

        assert ledger.calls == []

    async def test_a_refused_synthesis_spends_nothing(self) -> None:
        ledger = _Ledger()
        refusal = TTSProviderError("provider_http_error", details={"status_code": 400})

        with pytest.raises(TTSProviderError):
            await speak(
                _Client("openai", fail=refusal), "Bonjour.", "nova", model="tts-1", ledger=ledger
            )

        assert ledger.calls == []

    async def test_without_a_ledger_the_audio_still_comes_back(self) -> None:
        result = await speak(_Client("openai"), "Bonjour.", "nova", model="tts-1", ledger=None)

        assert result.characters == 8
        assert result.billed_units == 8


class _DialogueClient:
    """A byte-billed client voicing a whole exchange in one request."""

    provider_name = "fishaudio"
    audio_format = "mp3"

    def __init__(self, *, placed: bool = True, fail: Exception | None = None) -> None:
        self._placed = placed
        self._fail = fail

    async def synthesize(self, text: str, voice_name: str | None = None, **_: object) -> bytes:
        raise AssertionError("a dialogue is one request")

    async def synthesize_dialogue(self, turns: Any, **_: object) -> DialogueAudio:
        if self._fail is not None:
            raise self._fail
        sent = "".join(f"<|speaker:{n}|>{turn.words}" for n, turn in enumerate(turns))
        starts = tuple(float(n) for n in range(len(turns))) if self._placed else None
        return DialogueAudio(audio=b"audio", sent_text=sent, turn_starts_s=starts)

    async def close(self) -> None:
        return None


class TestDialogue:
    TURNS = [DialogueTurn("a", "今天的新闻。"), DialogueTurn("b", "Merci.")]

    @pytest.mark.parametrize("placed", [True, False])
    async def test_one_request_is_recorded_once_on_what_it_carried(self, placed: bool) -> None:
        """Markers included, and whether or not its timing placed every turn: the
        vendor billed the request whole once its audio came back."""
        ledger = _Ledger()

        dialogue = await speak_dialogue(
            _DialogueClient(placed=placed), self.TURNS, model="s2.1-pro", ledger=ledger
        )

        assert len(ledger.calls) == 1
        assert ledger.calls[0]["provider"] == "fishaudio"
        assert ledger.calls[0]["billed_units"] == len(dialogue.sent_text.encode("utf-8"))
        assert ledger.calls[0]["characters"] == len(dialogue.sent_text)

    async def test_a_refused_dialogue_records_nothing(self) -> None:
        ledger = _Ledger()

        with pytest.raises(TTSProviderError):
            await speak_dialogue(
                _DialogueClient(fail=TTSProviderError("provider_http_error")),
                self.TURNS,
                model="s2.1-pro",
                ledger=ledger,
            )

        assert ledger.calls == []
