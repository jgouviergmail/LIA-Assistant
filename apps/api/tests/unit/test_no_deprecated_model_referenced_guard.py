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
about what "retiring" means.

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

from datetime import UTC, datetime

import pytest

from src.core.constants import FALLBACK_MODELS_DEFAULT, SUMMARIZATION_MODEL_DEFAULT
from src.domains.llm.models import LLMProviderEnum
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.infrastructure.llm.catalogue.field_mapping import is_retiring, registry_facts

pytestmark = pytest.mark.unit


def _retiring(provider: str, model: str) -> bool:
    facts = registry_facts(provider, model)
    return facts is not None and is_retiring(facts, today=datetime.now(UTC).date())


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
