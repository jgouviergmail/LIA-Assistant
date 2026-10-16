"""A speech slot names a model its provider serves, of its kind, at a price its recorder reads.

A synthesis or transcription client sends its model by NAME to its own
provider, and the cost recorder prices the call by that name. Nothing held the
two together: ``provider=fishaudio, model=eleven_v4`` would have built the Fish
client, which sends the name in its ``model`` header — an unknown model, which
the vendor serves AND bills as ``s2.1-pro`` (measured 2026-10-13) — while LIA
priced the line at ElevenLabs' tariff. The admin form only offers a provider's
own models of the slot's kind; this is the write path's half of that promise
(ADR-345, the shape of ``_refuse_unserved_image_model``).

A tariff is refused only when it EXISTS in a unit the slot's recorder cannot
read (a synthesis priced per audio minute is billed at zero by a recorder that
reads per million units). A model with no tariff at all is not refused here:
telling a free engine from an unpriced one is the voice families' knowledge,
and ``voice`` already reads this domain. Absence of evidence is never a
rejection: with a cache not loaded yet, nothing is refused on what it would
have said.
"""

from __future__ import annotations

from typing import Final

from src.core.exceptions import raise_structured_validation_error
from src.domains.llm.models import LLMModelKindEnum, PricingUnitEnum
from src.domains.llm_config.constants import LLM_DEFAULTS, LLM_TYPES_REGISTRY
from src.infrastructure.cache.pricing_cache import get_cached_model_price, is_cache_initialized
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache

#: The units each speech kind's recorder prices: a synthesis per million billed
#: units (``tts_usage_record``), a transcription per audio duration.
_PRICED_UNITS: Final[dict[LLMModelKindEnum, frozenset[str]]] = {
    LLMModelKindEnum.tts: frozenset({PricingUnitEnum.per_1m_tokens.value}),
    LLMModelKindEnum.audio: frozenset(
        {PricingUnitEnum.per_audio_minute.value, PricingUnitEnum.per_audio_hour.value}
    ),
}


def refuse_unserved_speech_model(llm_type: str, provider: str | None, model: str | None) -> None:
    """Refuse a speech slot whose model its provider would not serve as stated.

    Args:
        llm_type: The slot being written.
        provider: The provider it would be configured with; ``None`` keeps the
            slot's default.
        model: The model it would be configured with; ``None`` keeps the
            slot's default. An omitted model requires the default provider too;
            a coherent reset to the defaults is never refused.

    Raises:
        HTTPException: 422 ``unknown_model``, ``model_kind_mismatch``,
            ``model_provider_mismatch`` or ``model_pricing_unit_mismatch``,
            naming the model.
    """
    metadata = LLM_TYPES_REGISTRY.get(llm_type)
    if metadata is None or metadata.required_kind not in _PRICED_UNITS:
        return
    model = _model_for_provider(llm_type, provider, model)
    if model is None:
        return
    if not ModelCapabilitiesCache.is_loaded():
        return
    required = metadata.required_kind
    profile = ModelCapabilitiesCache.get(model)
    if profile is None:
        raise_structured_validation_error(
            error_type="unknown_model",
            loc=["body", "model"],
            msg=f"Model {model!r} is not in the catalogue.",
            input_value=model,
            ctx={"model": model},
        )
    if profile.kind != required.value:
        raise_structured_validation_error(
            error_type="model_kind_mismatch",
            loc=["body", "model"],
            msg=f"Model {model!r} is a {profile.kind} model; this slot runs {required.value}.",
            input_value=model,
            ctx={"model": model, "kind": profile.kind, "required_kind": required.value},
        )
    configured = provider or LLM_DEFAULTS[llm_type].provider
    owner = ModelCapabilitiesCache.get_provider(model)
    if owner != configured:
        raise_structured_validation_error(
            error_type="model_provider_mismatch",
            loc=["body", "provider"],
            msg=f"Model {model!r} is served by {owner!r}, not {configured!r}.",
            input_value=configured,
            ctx={"model": model, "provider": owner},
        )
    price = get_cached_model_price(model) if is_cache_initialized() else None
    if price is not None and price.pricing_unit not in _PRICED_UNITS[required]:
        raise_structured_validation_error(
            error_type="model_pricing_unit_mismatch",
            loc=["body", "model"],
            msg=(
                f"Model {model!r} is priced {price.pricing_unit}, a unit the "
                f"{required.value} cost recorder does not read."
            ),
            input_value=model,
            ctx={"model": model, "pricing_unit": price.pricing_unit},
        )


def _model_for_provider(llm_type: str, provider: str | None, model: str | None) -> str | None:
    """A default model belongs to the default provider, including before cache load."""
    default = LLM_DEFAULTS[llm_type]
    if model is None and provider is not None and provider != default.provider:
        raise_structured_validation_error(
            error_type="model_provider_mismatch",
            loc=["body", "model"],
            msg=(
                f"Model {default.model!r} is the default of {default.provider!r}; "
                f"choose a model served by {provider!r}."
            ),
            input_value=model,
            ctx={"model": default.model, "provider": default.provider},
        )
    return model


__all__ = ["refuse_unserved_speech_model"]
