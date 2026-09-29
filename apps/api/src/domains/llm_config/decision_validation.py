"""Keep native decision configurations out of generative slots and vice versa."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import raise_structured_validation_error
from src.domains.llm.models import LLMModel, LLMModelKindEnum, LLMProviderEnum
from src.domains.llm_config.constants import LLM_DEFAULTS, LLM_TYPES_REGISTRY
from src.domains.llm_config.schemas import LLMTypeConfigUpdate
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache


def validate_decision_config(llm_type: str, update: LLMTypeConfigUpdate) -> None:
    """Reject incompatible native decision settings before writing an override."""
    default = LLM_DEFAULTS[llm_type]
    provider = update.provider or default.provider
    model = update.model or default.model
    expected = LLM_TYPES_REGISTRY[llm_type].required_kind.value
    profile = ModelCapabilitiesCache.get(model)
    native = expected == "decision"
    if not native and provider != "typesafe" and (profile is None or profile.kind != "decision"):
        return
    if not native or provider != "typesafe" or (profile is not None and profile.kind != "decision"):
        raise_structured_validation_error(
            error_type="decision_model_incompatible",
            loc=["body", "model"],
            msg="Native decisions require a decision slot and a TypeSafe decision model.",
            input_value=model,
            ctx={"expected_kind": expected},
        )
    _validate_native_parameters(update)


def _validate_native_parameters(update: LLMTypeConfigUpdate) -> None:
    """Native Choice accepts a deadline, never generative sampling controls."""
    for field in (
        "temperature",
        "top_p",
        "frequency_penalty",
        "presence_penalty",
        "max_tokens",
        "reasoning_effort",
        "context_window",
    ):
        if getattr(update, field) is not None:
            raise_structured_validation_error(
                error_type="decision_parameter_unsupported",
                loc=["body", field],
                msg="Native decisions do not accept this parameter.",
                input_value=None,
                ctx={"field": field},
            )
    if update.provider_config not in (None, "", "{}"):
        raise_structured_validation_error(
            error_type="decision_parameter_unsupported",
            loc=["body", "provider_config"],
            msg="Native decisions do not accept custom provider parameters.",
            input_value=None,
            ctx={"field": "provider_config"},
        )
    if update.timeout_seconds is not None and update.timeout_seconds > 5:
        raise_structured_validation_error(
            error_type="decision_timeout_too_long",
            loc=["body", "timeout_seconds"],
            msg="Native decisions must fall back within five seconds.",
            input_value=update.timeout_seconds,
            ctx={"maximum": 5},
        )


async def validate_decision_model(
    db: AsyncSession, llm_type: str, update: LLMTypeConfigUpdate
) -> None:
    """Validate native availability against the authority, including on a cold cache."""
    if LLM_TYPES_REGISTRY[llm_type].required_kind != LLMModelKindEnum.decision:
        return
    name = update.model or LLM_DEFAULTS[llm_type].model
    model = await db.scalar(
        select(LLMModel.id).where(
            LLMModel.model_name == name,
            LLMModel.provider == LLMProviderEnum.typesafe,
            LLMModel.kind == LLMModelKindEnum.decision,
            LLMModel.is_active,
        )
    )
    if model is None:
        raise_structured_validation_error(
            error_type="decision_model_unavailable",
            loc=["body", "model"],
            msg="Select an active TypeSafe decision model from the catalogue.",
            input_value=name,
            ctx={"model": name},
        )
