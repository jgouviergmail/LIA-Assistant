"""Guard: the web app names every voice engine by the API's own display name (ADR-345).

The chat's synthesis and transcription tooltips and the voice settings name the
engine that spoke or listened, from ONE web table (``lib/voice-provider-brand.ts``).
This test holds it to the engines the catalogue serves — every TTS family and
every remote transcription engine — each under its ``LLM_PROVIDERS`` display
name: a new engine is named rather than shown by its identifier, and a renamed
brand reaches both sides.

The frontend file is parsed rather than imported, the reading
``test_llm_provider_vocabulary_parity_guard.py`` does.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.core.remote_stt import REMOTE_STT_PROVIDERS
from src.domains.llm_config.constants import LLM_PROVIDERS
from src.domains.voice.families import TTS_FAMILIES

pytestmark = pytest.mark.unit

_BRANDS = Path(__file__).resolve().parents[5] / "web" / "src" / "lib" / "voice-provider-brand.ts"


def _web_brands() -> dict[str, str]:
    text = _BRANDS.read_text(encoding="utf-8")
    match = re.search(r"VOICE_PROVIDER_BRANDS[^=]*=\s*new Map\(\[(.*?)\]\);", text, re.DOTALL)
    assert match is not None, "VOICE_PROVIDER_BRANDS not found"
    return dict(re.findall(r"\['([a-z0-9_]+)',\s*'([^']+)'\]", match.group(1)))


def test_every_voice_engine_is_named_by_its_display_name() -> None:
    engines = set(TTS_FAMILIES) | set(REMOTE_STT_PROVIDERS)

    assert _web_brands() == {engine: LLM_PROVIDERS[engine] for engine in engines}
