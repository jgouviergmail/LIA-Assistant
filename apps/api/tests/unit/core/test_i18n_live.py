"""Live phrases (ADR-299): six languages, one key set, zh-CN normalised."""

from __future__ import annotations

from typing import get_args

import pytest

from src.core.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
from src.core.i18n_live import LIVE_PHRASES, get_live_phrases
from src.domains.live.schemas import LiveOutcome
from src.infrastructure.scheduler.voice_relay import RelayOutcome
from src.infrastructure.scheduler.voice_session_closing import RELAY_SCHEDULED

pytestmark = pytest.mark.unit

# The outcome phrases are READ from the wire vocabulary: a tenth outcome
# without its six sentences must fail here, not KeyError on a closing card.
KEYS = {
    "connector_missing",
    "session_in_progress",
    "instance_busy",
    "mint_rate_limited",
    "session_not_found",
    "session_expired",
    "credential_invalid",
    "provider_refused",
    "voice_unknown",
    "thinking_level_unknown",
    "model_unpriced",
    "mode_unsupported",
    "summary_title",
    "summary_body",
    "summary_body_direct",
    # ADR-301: the fate of a DIRECT session's words, said on the card — READ
    # from the relay's own vocabulary, every outcome included: the settle
    # formats `relay_{outcome}` for whatever the relay answered, and a value
    # with no sentence was a KeyError that left the card at « scheduled ».
    f"relay_{RELAY_SCHEDULED}",
    *(f"relay_{outcome.value}" for outcome in RelayOutcome),
    # The recap of the words when the relay could not run (the phone's own
    # fallback carries it in a push; the browser's card carries it here).
    "summary_recap",
    "summary_extended",
    "voice_sample",
    *(f"outcome_{outcome}" for outcome in get_args(LiveOutcome)),
}


@pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
def test_every_language_carries_every_key(language: str) -> None:
    assert set(LIVE_PHRASES[language]) == KEYS
    assert all(value.strip() for value in LIVE_PHRASES[language].values())


def test_the_table_speaks_the_backend_vocabulary() -> None:
    assert set(LIVE_PHRASES) == set(SUPPORTED_LANGUAGES)


@pytest.mark.parametrize("raw", ["zh", "zh_CN", "zh-TW", "ZH-cn"])
def test_every_chinese_spelling_reaches_the_canonical_row(raw: str) -> None:
    assert get_live_phrases(raw) is LIVE_PHRASES["zh-CN"]


def test_unknown_and_missing_fall_back_to_the_default_language() -> None:
    assert get_live_phrases(None) is LIVE_PHRASES[DEFAULT_LANGUAGE]
    assert get_live_phrases("xx") is LIVE_PHRASES[DEFAULT_LANGUAGE]


@pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
def test_summary_body_formats_in_every_language(language: str) -> None:
    body = get_live_phrases(language)["summary_body"].format(
        minutes=12, delegations=3, voice_turns=7, cost="0.0123"
    )
    assert "12" in body and "3" in body and "7" in body and "0.0123" in body


@pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
def test_provider_refused_carries_the_providers_words(language: str) -> None:
    assert "{detail}" in get_live_phrases(language)["provider_refused"]


@pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
def test_the_recap_line_carries_the_recap(language: str) -> None:
    assert "{recap}" in get_live_phrases(language)["summary_recap"]
