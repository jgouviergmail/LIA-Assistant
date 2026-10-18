"""Systemic guard: no code default may point at a retiring model.

Measured 2026-08-24: 23 of the 114 active catalogue rows were retiring, and two
constants were two months from their date — ``SUMMARIZATION_MODEL_DEFAULT =
gpt-4.1-nano`` and ``LLM_DEFAULTS["image_generation"] = gpt-image-1``, both
2026-10-23. A third, ``FALLBACK_MODELS_DEFAULT``, named one model absent from
the catalogue entirely and one that was deactivated, so the failover chain had
no reachable target at all.

This guard turns that class of outage into a build failure with a month of
notice. It reads both retirement signals through the single ``is_retiring``
policy, so it cannot disagree with the sync report or the correction migration
about what "retiring" means. One addition, for a model no registry copies:
``registry_facts`` answers nothing for it even when the vendor's own page dates
its shutdown (eleven ``VENDOR_SHUTDOWNS`` entries on 2026-10-18, the 3.8 speech
and live models among them), so the vendor's date is handed to the same policy —
read alone, the guard would pass on every such model by construction.

It also covers the model defaults a provider path calls DIRECTLY, with no
``LLM_DEFAULTS`` slot (measured 2026-10-18: the live voice sample's default was
``gemini-2.5-flash-preview-tts``, which Google retires on 2026-11-17, and no
test read it).

**What it deliberately cannot see: the deployed environment.**
``tests/conftest.py`` scrubs every key declared in the repository-root ``.env``
before any import, so that the test environment is identical whatever the
launcher (an incident is recorded there: a developer's
``SEMANTIC_EXPANSION_EVIDENCE_DRIVEN_ENABLED`` and ``DEFAULT_CURRENCY`` once
flipped twelve tests). ``settings.summarization_model`` therefore always
resolves to the code default here. A deployment whose ``SUMMARIZATION_MODEL``
still names a retiring model is real drift — measured on the dev instance on
2026-08-24, where the constant had moved and the environment had not — but it
belongs to a boot-time assertion on the running configuration, not to a unit
suite that is designed to be blind to it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from src.core.constants import (
    FALLBACK_MODELS_DEFAULT,
    GEMINI_LIVE_DEFAULT_MODEL,
    GEMINI_TTS_SAMPLE_MODEL_DEFAULT,
    INTEREST_EMBEDDING_MODEL_DEFAULT,
    JOURNAL_EMBEDDING_MODEL_DEFAULT,
    MEMORY_EMBEDDING_MODEL_DEFAULT,
    OPENAI_STT_DIARIZE_MODEL_DEFAULT,
    PERPLEXITY_SEARCH_MODEL_DEFAULT,
    RAG_SPACES_EMBEDDING_MODEL_DEFAULT,
    SUMMARIZATION_MODEL_DEFAULT,
)
from src.domains.llm.models import LLMProviderEnum
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.infrastructure.llm.catalogue import vendor_announcements
from src.infrastructure.llm.catalogue.field_mapping import (
    RegistryFacts,
    is_retiring,
    registry_facts,
)
from src.infrastructure.llm.catalogue.vendor_announcements import announced_shutdown

pytestmark = pytest.mark.unit

#: The model defaults a provider path calls directly — no ``LLM_DEFAULTS`` slot —
#: with the provider that serves each. Not listed: a default no registry and no
#: vendor page LIA reads names (``OPENAI_LIVE_DEFAULT_MODEL``,
#: ``DEVOPS_CLAUDE_MODEL_DEFAULT``, the Fish Audio and ElevenLabs models): nothing
#: could judge it.
DIRECT_MODEL_DEFAULTS: dict[str, tuple[str, str]] = {
    "GEMINI_TTS_SAMPLE_MODEL_DEFAULT": ("gemini", GEMINI_TTS_SAMPLE_MODEL_DEFAULT),
    "GEMINI_LIVE_DEFAULT_MODEL": ("gemini", GEMINI_LIVE_DEFAULT_MODEL),
    "MEMORY_EMBEDDING_MODEL_DEFAULT": ("gemini", MEMORY_EMBEDDING_MODEL_DEFAULT),
    "INTEREST_EMBEDDING_MODEL_DEFAULT": ("gemini", INTEREST_EMBEDDING_MODEL_DEFAULT),
    "JOURNAL_EMBEDDING_MODEL_DEFAULT": ("gemini", JOURNAL_EMBEDDING_MODEL_DEFAULT),
    "RAG_SPACES_EMBEDDING_MODEL_DEFAULT": ("gemini", RAG_SPACES_EMBEDDING_MODEL_DEFAULT),
    "PERPLEXITY_SEARCH_MODEL_DEFAULT": ("perplexity", PERPLEXITY_SEARCH_MODEL_DEFAULT),
    "OPENAI_STT_DIARIZE_MODEL_DEFAULT": ("openai", OPENAI_STT_DIARIZE_MODEL_DEFAULT),
}


def _today() -> date:
    return datetime.now(UTC).date()


def _facts(provider: str, model: str) -> RegistryFacts | None:
    """The registries' facts — or, for a model none of them copies, the vendor's page."""
    facts = registry_facts(provider, model)
    if facts is not None:
        return facts
    announced, shutdown = announced_shutdown(provider, model)
    if not announced:
        return None
    return RegistryFacts(deprecation_date=shutdown, matched_registries=frozenset({"vendor"}))


def _retiring(provider: str, model: str) -> bool:
    facts = _facts(provider, model)
    return facts is not None and is_retiring(facts, today=_today())


def _providers_knowing(model: str) -> list[str]:
    """Every LIA provider whose canonical registry entry covers this model.

    All of them, not the first: a name can exist under two providers with
    different retirement dates, and taking the first hit would let the healthy
    one mask the retiring one.
    """
    return [
        provider.value
        for provider in LLMProviderEnum
        if registry_facts(provider.value, model) is not None
    ]


def test_no_llm_default_is_retiring() -> None:
    offenders = sorted(
        f"{slot}:{config.model}"
        for slot, config in LLM_DEFAULTS.items()
        if config.model and _retiring(config.provider, config.model)
    )
    assert offenders == [], f"LLM_DEFAULTS point at retiring models: {offenders}"


def test_summarization_default_is_not_retiring() -> None:
    """OpenAI by construction: the middleware calls ``_require_api_key("openai")``."""
    assert not _retiring(
        "openai", SUMMARIZATION_MODEL_DEFAULT
    ), f"SUMMARIZATION_MODEL_DEFAULT={SUMMARIZATION_MODEL_DEFAULT} is retiring"


def test_fallback_models_are_known_and_not_retiring() -> None:
    """A failover chain naming an unknown model has no reachable target."""
    for name in (part.strip() for part in FALLBACK_MODELS_DEFAULT.split(",") if part.strip()):
        providers = _providers_knowing(name)
        assert providers, f"FALLBACK_MODELS_DEFAULT entry {name!r} is unknown to every registry"
        retiring = sorted(p for p in providers if _retiring(p, name))
        assert not retiring, f"FALLBACK_MODELS_DEFAULT entry {name!r} is retiring under {retiring}"


@pytest.mark.parametrize(
    ("constant", "provider", "model"),
    [(name, provider, model) for name, (provider, model) in DIRECT_MODEL_DEFAULTS.items()],
    ids=list(DIRECT_MODEL_DEFAULTS),
)
def test_direct_model_defaults_are_known_and_not_retiring(
    constant: str, provider: str, model: str
) -> None:
    """A default a provider path calls directly is judged like a slot's default."""
    bare = model.removeprefix("models/")  # the Gemini SDK's resource spelling
    assert (
        _facts(provider, bare) is not None
    ), f"{constant}={model!r} is known to no registry and to no vendor page LIA reads"
    assert not _retiring(provider, bare), f"{constant}={model!r} is retiring"


def test_a_vendor_dated_shutdown_is_seen_without_any_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model no registry copies is judged on the vendor's own date, by the same policy."""
    model = "gemini-vendor-only-guard-probe"
    assert registry_facts("gemini", model) is None
    assert _facts("gemini", model) is None  # unlisted anywhere: unknown, never « healthy »

    monkeypatch.setitem(
        vendor_announcements.VENDOR_SHUTDOWNS, ("gemini", model), _today() + timedelta(days=10)
    )
    assert _retiring("gemini", model)

    monkeypatch.setitem(vendor_announcements.VENDOR_SHUTDOWNS, ("gemini", model), None)
    assert _facts("gemini", model) is not None and not _retiring("gemini", model)
