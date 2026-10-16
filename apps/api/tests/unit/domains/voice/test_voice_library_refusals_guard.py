"""Guard: every refusal the voice library can send has its sentence, in the six languages (ADR-345).

The library's routes name a refusal by a stable code; the page holds the
sentence (``settings.admin.voiceLibrary.errors.<code>``). A code with no
sentence reaches the administrator as the generic one — the reason lost — so
the two sides are held equal here, and so is the name of every TTS slot a
voice can speak for (``…voiceLibrary.slots.<slot>``), which the 409 and the
list quote.

The locale files are parsed rather than imported, the reading
``test_llm_provider_vocabulary_parity_guard.py`` does.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.core.constants import INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE
from src.domains.llm.models import LLMModelKindEnum
from src.domains.llm_config.constants import LLM_TYPES_REGISTRY
from src.domains.voice.fishaudio.library_errors import REFUSAL_CODES

pytestmark = pytest.mark.unit

_LOCALES = Path(__file__).resolve().parents[5] / "web" / "locales"
_LANGUAGES = ("en", "fr", "de", "es", "it", "zh")


def _section(language: str) -> dict[str, Any]:
    raw = json.loads((_LOCALES / language / "translation.json").read_text(encoding="utf-8"))
    section: dict[str, Any] = raw["settings"]["admin"]["voiceLibrary"]
    return section


@pytest.mark.parametrize("language", _LANGUAGES)
def test_every_refusal_has_its_sentence(language: str) -> None:
    errors = _section(language)["errors"]
    expected = REFUSAL_CODES | {INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE, "generic"}

    assert set(errors) == expected
    assert all(isinstance(text, str) and text.strip() for text in errors.values())


@pytest.mark.parametrize("language", _LANGUAGES)
def test_every_speaking_slot_has_its_name(language: str) -> None:
    speaking = {
        slot
        for slot, metadata in LLM_TYPES_REGISTRY.items()
        if metadata.required_kind is LLMModelKindEnum.tts
    }

    assert set(_section(language)["slots"]) == speaking
