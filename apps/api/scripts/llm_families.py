"""The model families a measurement asks, named one way for every bench.

A measurement concludes over several families, never over one model: a bench is
told which with ``--models provider:model[@level],...`` and asks each through the
slot's own configuration, with only the provider, the model and the reasoning
level replaced. Without a family named, the instance's own slot is asked, as the
database configures it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from src.core.config import settings
from src.core.llm_agent_config import LLMAgentConfig
from src.core.llm_config_helper import get_llm_config_for_agent
from src.core.reasoning_intent import LEVELS, Level, ReasoningIntent
from src.infrastructure.cache.pricing_cache import (
    get_cached_cost_usd_eur,
    refresh_pricing_cache,
)
from src.infrastructure.llm.factory import LLMType, get_llm
from src.infrastructure.llm.usage_metadata import (
    model_name_of,
    model_name_of_response,
    tokens_from_usage_metadata,
)


async def prepare_bench() -> None:
    """Load what a paid bench reads before its first call, as the API does at boot.

    The provider keys live in the database (the in-memory override cache): a bench
    that skips this asks every family with the environment's placeholder key. The
    capabilities cache decides each model's options, the tariffs price each answer.
    """
    from src.domains.llm_config.cache import LLMConfigOverrideCache
    from src.infrastructure.database.session import get_db_context
    from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache

    async with get_db_context() as db:
        await LLMConfigOverrideCache.load_from_db(db)
        await ModelCapabilitiesCache.load_from_db(db)
    await refresh_pricing_cache()


#: One family: a provider, its model, and the reasoning level asked of it.
Family = tuple[str, str, Level]


def parse_families(spec: str | None) -> list[Family | None]:
    """The families named; ``None`` stands for the instance's own slot.

    Args:
        spec: ``provider:model[@level],...``, or nothing.

    Returns:
        One entry per family, in the order named.

    Raises:
        SystemExit: A reasoning level the ladder does not hold.
    """
    if not spec:
        return [None]
    parsed: list[Family | None] = []
    for item in spec.split(","):
        head, _, raw = item.partition("@")
        provider, _, model = head.partition(":")
        level = raw.strip() or "provider_default"
        if level not in LEVELS:
            raise SystemExit(f"unknown reasoning level '{level}' (one of {', '.join(LEVELS)})")
        parsed.append((provider.strip(), model.strip(), cast(Level, level)))
    return parsed


def named_families(spec: str) -> list[Family]:
    """The families of a bench that asks no slot as configured: each one is named.

    Args:
        spec: ``provider:model[@level],...``.

    Returns:
        One entry per family, in the order named.

    Raises:
        SystemExit: No family named, or a reasoning level the ladder does not hold.
    """
    families = [family for family in parse_families(spec) if family is not None]
    if not families:
        raise SystemExit("--models names no family (provider:model[@level],...)")
    return families


def family_llm(slot: LLMType, family: Family | None) -> tuple[str, BaseChatModel, LLMAgentConfig]:
    """The slot's model, or another family on the slot's own settings.

    Args:
        slot: The LLM slot whose settings are kept.
        family: The family to ask, or None for the slot as configured.

    Returns:
        The model's name, the model, and the configuration it was built from.
    """
    config = get_llm_config_for_agent(settings, slot)
    if family is None:
        llm = get_llm(slot)
        return model_name_of(llm) or slot, llm, config
    provider, model, level = family
    override = config.model_copy(
        update={
            "provider": provider,
            "model": model,
            "reasoning_effort": ReasoningIntent(level=level),
        }
    )
    return model, get_llm(slot, config_override=override), override


@dataclass(frozen=True)
class Priced:
    """What one model response cost, as the platform's tariffs price it."""

    tokens_in: int
    tokens_out: int
    cost_usd: float
    cost_eur: float


def price_response(response: BaseMessage, model: str) -> Priced:
    """Price one direct response from its own usage, at the model that ANSWERED.

    Args:
        response: The model's message, carrying its ``usage_metadata``.
        model: The model asked — priced only when the response names none.

    Returns:
        Its tokens and its cost in USD and EUR (the pricing cache must be loaded).
    """
    usage = tokens_from_usage_metadata(getattr(response, "usage_metadata", None))
    cost_usd, cost_eur = get_cached_cost_usd_eur(
        model_name_of_response(response) or model,
        usage.prompt,
        usage.completion,
        usage.cached,
        cache_write_tokens=usage.cache_write,
    )
    return Priced(usage.prompt, usage.completion, cost_usd, cost_eur)
