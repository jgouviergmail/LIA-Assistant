"""The one door a heard synthesis goes through: billed in its vendor's unit, recorded once.

Every surface that speaks — the chat's voice comments and readouts, the radio —
used to bill on its own, and the copies disagreed (ADR-345): the chat recorded
the CONFIGURED engine's tariff for a line the factory had handed to the free
engine instead, counted characters for an engine billed per UTF-8 byte, and
could not serve a token-billed engine at all. :func:`speak` is the door: it
synthesizes through :func:`~src.domains.voice.billing.synthesize_billed` and
files the call on the ledger, keyed on the client that SPOKE.

What reaches the ledger is a SERVED synthesis only: a refused or cancelled call
raises before anything is recorded, and the free engine records nothing.
Wrapping raw samples for a reader (:func:`~src.domains.voice.audio_output.audio_for_mix`)
stays with the caller, outside any retry: the vendor billed the audio it sent,
and a malformed answer must not be bought twice.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Protocol

from src.domains.voice.billing import SynthesisResult, synthesize_billed
from src.domains.voice.families import billed_text_units
from src.domains.voice.protocol import DialogueAudio, DialogueTTSClient, DialogueTurn, TTSClient


class TtsLedger(Protocol):
    """Where a paid synthesis is billed (a run's tracking context)."""

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
        """Record one synthesis."""
        ...


async def speak(
    client: TTSClient,
    text: str,
    voice_name: str | None = None,
    *,
    model: str,
    ledger: TtsLedger | None,
    **kwargs: object,
) -> SynthesisResult:
    """Synthesize ``text`` and record what the call costs.

    Args:
        client: The client that speaks — its provider is the one billed.
        text: What to say.
        voice_name: Provider voice id.
        model: The client's model, as the tariff table names it.
        ledger: Where the call is recorded; ``None`` records nothing (an
            anonymous synthesis).
        **kwargs: Per-call delivery controls, passed through.

    Returns:
        The audio and the units it was billed on.

    Raises:
        TTSProviderError: When the provider refuses or fails; nothing is recorded.
    """
    started = time.perf_counter()
    result = await synthesize_billed(client, text, voice_name, **kwargs)
    # A free engine bills nothing (0): no zero-value row in the audit trail.
    if ledger is not None and result.billed_units != 0:
        ledger.record_tts_call(
            client.provider_name,
            model,
            result.characters,
            (time.perf_counter() - started) * 1000,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            billed_units=result.billed_units,
        )
    return result


async def speak_dialogue(
    client: DialogueTTSClient,
    turns: Sequence[DialogueTurn],
    *,
    model: str,
    ledger: TtsLedger | None,
    **kwargs: object,
) -> DialogueAudio:
    """Voice ``turns`` in one request and record what the request costs.

    The vendor bills the request whole — its markers and cues with the words —
    as soon as its audio came back, whether or not its timing placed every turn:
    an unplaced dialogue is recorded all the same, and a caller that voices its
    lines again records those calls too.

    Args:
        client: The client that speaks — its provider is the one billed.
        turns: The turns, in order.
        model: The client's model, as the tariff table names it.
        ledger: Where the call is recorded; ``None`` records nothing.
        **kwargs: Per-call delivery controls shared by every turn.

    Returns:
        The audio and each turn's start.

    Raises:
        TTSProviderError: When the provider refuses or fails; nothing is recorded.
    """
    started = time.perf_counter()
    dialogue = await client.synthesize_dialogue(turns, **kwargs)
    billed = billed_text_units(client.provider_name, dialogue.sent_text)
    if ledger is not None and billed != 0:
        ledger.record_tts_call(
            client.provider_name,
            model,
            len(dialogue.sent_text),
            (time.perf_counter() - started) * 1000,
            billed_units=billed,
        )
    return dialogue


__all__ = ["TtsLedger", "speak", "speak_dialogue"]
