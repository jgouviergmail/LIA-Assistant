"""The voice preference says who receives the audio in « remote » mode (ADR-345).

The privacy notice used to name ElevenLabs whatever the administrator chose;
the endpoint now publishes the ``voice_transcription`` slot's provider, and
« available » follows that provider's switch and key.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from src.domains.auth.router import get_voice_mode_preference
from src.domains.llm_config.cache import LLMConfigOverrideCache

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_cache() -> Iterator[None]:
    LLMConfigOverrideCache.reset()
    yield
    LLMConfigOverrideCache.reset()


@pytest.mark.parametrize(
    ("keys", "available"),
    [({"fishaudio": "sk-fish"}, True), ({"elevenlabs": "sk-eleven"}, False)],
)
async def test_it_names_the_slots_engine_and_its_own_readiness(
    keys: dict[str, str], available: bool
) -> None:
    LLMConfigOverrideCache._overrides = {
        "voice_transcription": {"provider": "fishaudio", "model": "transcribe-1"}
    }
    LLMConfigOverrideCache._provider_keys = keys
    LLMConfigOverrideCache._loaded = True
    user = SimpleNamespace(voice_mode_enabled=True, voice_stt_mode="remote")

    answer = await get_voice_mode_preference(user=user)  # type: ignore[arg-type]

    assert answer.stt_remote_provider == "fishaudio"
    assert answer.stt_remote_available is available
