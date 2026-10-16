"""Guard: the admin form offers exactly the Fish Audio options the client accepts.

The voice-slot dialog lists containers, latencies, a speaking-rate range and a
voice-id shape for Fish Audio, mirrored in TypeScript beside the other
providers' lists — the pin ceiling is not mirrored: the pins route publishes it.
A value the form offers that the client does not know is repaired at run time
with a warning — the form would be lying about what it configures. This test holds the two sides equal (ADR-345, the ADR-184 rule that
the UI is offered exactly what the API accepts). It also holds the providers the
pickers know to the ones the voice catalogue serves.

The frontend file is parsed rather than imported: the backend suite runs from a
full checkout, the same reading ``test_llm_provider_vocabulary_parity_guard.py``
does.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest

from src.domains.voice.admin_router import VoiceProviderName
from src.domains.voice.families import TTS_FAMILIES
from src.domains.voice.fishaudio.formats import (
    DEFAULT_FISH_OUTPUT_FORMAT,
    DEFAULT_FISH_TRANSPORT,
    FISH_LATENCIES,
    FISH_OUTPUT_FORMATS,
    FISH_SPEED_MAX,
    FISH_SPEED_MIN,
    FISH_TRANSPORTS,
)
from src.domains.voice.fishaudio.voices import VOICE_ID_PATTERN

pytestmark = pytest.mark.unit

_HELPERS = (
    Path(__file__).resolve().parents[3]
    / "web"
    / "src"
    / "components"
    / "settings"
    / "llm-config"
    / "configDialogHelpers.ts"
)


@pytest.fixture(scope="module")
def helpers() -> str:
    return _HELPERS.read_text(encoding="utf-8")


def _array(text: str, name: str) -> list[str]:
    match = re.search(rf"export const {name} = \[([^\]]+)\]", text)
    assert match is not None, f"{name} not found"
    return re.findall(r"'([a-z0-9_]+)'", match.group(1))


def _scalar(text: str, name: str) -> str:
    match = re.search(rf"export const {name} = ([^;]+);", text)
    assert match is not None, f"{name} not found"
    return match.group(1).strip()


def test_the_containers_are_the_clients(helpers: str) -> None:
    assert set(_array(helpers, "FISHAUDIO_OUTPUT_FORMATS")) == set(FISH_OUTPUT_FORMATS)
    assert _scalar(helpers, "DEFAULT_FISHAUDIO_OUTPUT_FORMAT") == f"'{DEFAULT_FISH_OUTPUT_FORMAT}'"


def test_the_latencies_are_the_clients(helpers: str) -> None:
    assert set(_array(helpers, "FISHAUDIO_LATENCIES")) == set(FISH_LATENCIES)


def test_the_transports_are_the_clients(helpers: str) -> None:
    assert set(_array(helpers, "FISHAUDIO_TRANSPORTS")) == set(FISH_TRANSPORTS)
    assert _scalar(helpers, "DEFAULT_FISHAUDIO_TRANSPORT") == f"'{DEFAULT_FISH_TRANSPORT}'"


def test_the_speaking_rate_range_is_the_vendors(helpers: str) -> None:
    assert float(_scalar(helpers, "FISHAUDIO_SPEED_MIN")) == FISH_SPEED_MIN
    assert float(_scalar(helpers, "FISHAUDIO_SPEED_MAX")) == FISH_SPEED_MAX


def test_the_voice_id_is_the_apis(helpers: str) -> None:
    assert _scalar(helpers, "FISHAUDIO_VOICE_ID_PATTERN") == f"/^{VOICE_ID_PATTERN.pattern}$/"


def test_the_pin_ceiling_is_read_from_the_api_never_mirrored(helpers: str) -> None:
    # A second copy of the ceiling could disagree with the one the store enforces.
    assert "FISHAUDIO_PINNED_VOICES_MAX" not in helpers


def test_the_pickers_know_every_provider_the_catalogue_serves(helpers: str) -> None:
    providers = set(_array(helpers, "TTS_PROVIDERS"))
    assert providers == set(get_args(VoiceProviderName)) == set(TTS_FAMILIES)
