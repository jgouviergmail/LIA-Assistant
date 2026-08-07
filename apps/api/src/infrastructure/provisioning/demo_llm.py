"""Point every LLM type at the provider the demonstrator actually pays for.

The registry ships one provider per type, chosen for the full product: Qwen
for one, OpenAI for another. A demonstrator carries ONE key — the cheap one
an owner is willing to spend on strangers — so every type pointing elsewhere
fails, and the visitor reads "the model provider is having technical
difficulties" on their first message.

Measured 2026-08-06 on the first real conversation: the router reached OpenAI
with `NOT_CONFIGURED` (401) and the query analyzer reached Qwen, whose host is
not even on the egress allowlist. Nothing was broken — the instance was simply
calling providers it had no key for.

Every type is rewritten, never a subset: one type left behind is a path that
fails at random, depending on which node the graph happens to reach.

Created: 2026-08-07 (live-demonstrator programme, first bring-up)
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select

from src.core.config import settings
from src.domains.llm.models import LLMModel, LLMModelPricing, PricingUnitEnum
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.llm_config.constants import LLM_DEFAULTS, LLM_PROVIDERS
from src.domains.llm_config.models import LLMConfigOverride

logger = structlog.get_logger(__name__)

#: Providers that do NOT serve text completions. A chat model cannot
#: transcribe speech or speak, so the two voice types keep their own provider:
#: repointing them would not save a cent, it would leave the voice broken
#: while the capability switches still report it as on.
_SPEECH_PROVIDERS = frozenset({"elevenlabs", "edge"})

#: Providers whose calls cost the operator no provider euro, so the absence of
#: a price is the truth rather than a hole. Local inference only: anything
#: reached over the network bills somebody, and a demonstrator that cannot say
#: how much has no ceiling at all.
_UNBILLED_PROVIDERS = frozenset({"ollama"})


def build_demo_overrides(*, provider: str, model: str) -> dict[str, tuple[str, str]]:
    """Map every LLM type to the demonstrator's single provider.

    Args:
        provider: Canonical provider key; empty means "leave the registry
            alone", which is what an instance with no configured provider
            wants.
        model: Model name to use for every type.

    Returns:
        One ``(provider, model)`` per LLM type, or an empty mapping.

    Raises:
        ValueError: The provider is not one this codebase knows. Writing 57
            rows pointing nowhere would surface one failure at a time.
    """
    if not provider:
        return {}
    if provider not in LLM_PROVIDERS:
        raise ValueError(f"unknown provider {provider!r} — expected one of {sorted(LLM_PROVIDERS)}")
    return {
        llm_type: (provider, model)
        for llm_type, default in LLM_DEFAULTS.items()
        if default.provider not in _SPEECH_PROVIDERS
    }


async def unbillable_model(session: Any, *, provider: str, model: str) -> str | None:
    """Name the configured model when THIS database cannot price its calls.

    A demonstrator's only financial protection is the daily spend ceiling
    (ADR-216), and that ceiling reads a ledger fed by the pricing catalogue.
    A model absent from the catalogue is billed by the provider and recorded
    at zero: the ceiling stays flat while the invoice grows.

    Measured 2026-08-07 on the running demonstrator: 59 344 real tokens
    recorded as 0,000025 EUR, ``pricing_cache_fallback_total`` at 88. This
    database's catalogue is built by the MIGRATIONS alone — the reference seed
    bundle is refused here, because the migrations already inserted the
    personalities and that bundle deletes before it inserts (ADR-215) — and
    the configured model was one only the bundle carries.

    Args:
        session: Database session; the caller owns the transaction.
        provider: Canonical provider key; empty means the registry is left
            alone, so there is no single model to price.
        model: Model name every LLM type would be pointed at.

    Returns:
        The model name when it has no active per-1M-token price, ``None``
        when it has one, when the provider bills nothing, or when the provider
        is not one this codebase knows — that last case is a different fault
        with its own error, and answering it here would report a misleading
        "unpriced model" for what is really a misspelled provider.
    """
    if not provider or provider in _UNBILLED_PROVIDERS or provider not in LLM_PROVIDERS:
        return None

    priced = (
        await session.execute(
            select(LLMModelPricing.id)
            .join(LLMModel, LLMModel.id == LLMModelPricing.model_id)
            .where(
                LLMModel.model_name == model,
                LLMModelPricing.is_active.is_(True),
                LLMModelPricing.pricing_unit == PricingUnitEnum.per_1m_tokens,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return None if priced is not None else model


async def apply_demo_llm_configuration(session: Any) -> int:
    """Write the overrides, replacing whatever a previous run left.

    Args:
        session: Database session; the caller owns the transaction.

    Returns:
        How many types were pointed at the demonstrator's provider.
    """
    provider = (getattr(settings, "demo_instance_llm_provider", "") or "").strip()
    model = (getattr(settings, "demo_instance_llm_model", "") or "").strip()
    overrides = build_demo_overrides(provider=provider, model=model)
    if not overrides:
        logger.info("demo_llm_configuration_skipped", reason="no_provider_configured")
        return 0

    existing = {
        row.llm_type: row
        for row in (await session.execute(select(LLMConfigOverride))).scalars().all()
    }
    for llm_type, (llm_provider, llm_model) in overrides.items():
        row = existing.get(llm_type)
        if row is None:
            session.add(
                LLMConfigOverride(llm_type=llm_type, provider=llm_provider, model=llm_model)
            )
        else:
            row.provider = llm_provider
            row.model = llm_model

    # The factory reads the in-memory cache, never the table. Without this
    # reload the rows are written, `task demo:provision` reports success, and
    # every answer still goes to the registry's provider until someone
    # restarts the API — a setting that is stored and inert (measured
    # 2026-08-06: 57 rows pointing at DeepSeek while the response node kept
    # calling Qwen).
    await session.flush()
    await LLMConfigOverrideCache.invalidate_and_reload(session)

    logger.info(
        "demo_llm_configuration_applied",
        provider=provider,
        model=model,
        llm_types=len(overrides),
    )
    return len(overrides)
