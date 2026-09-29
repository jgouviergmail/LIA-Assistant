"""Native decision models are configurable without entering a chat-model slot."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request

from src.core.llm_config_helper import merge_config
from src.domains.llm_config.constants import LLM_DEFAULTS, LLM_TYPES_REGISTRY
from src.domains.llm_config.schemas import LLMTypeConfigUpdate
from src.domains.llm_config.service import LLMConfigService
from src.infrastructure.llm.model_profiles import ModelProfile

pytestmark = pytest.mark.unit


def test_decision_defaults_resolve_without_touching_the_generative_fallback() -> None:
    assert "meeting_template_selection" in LLM_DEFAULTS
    default = LLM_DEFAULTS["meeting_template_selection"]
    config = merge_config(default, {"timeout_seconds": 2})
    assert config.provider == "typesafe"
    assert config.timeout_seconds == 2
    assert LLM_TYPES_REGISTRY["meeting_template_selection"].required_kind.value == "decision"
    assert LLM_TYPES_REGISTRY["meeting_synthesis"].required_kind.value == "chat"


@pytest.mark.parametrize(
    "slot,provider,model,kind",
    [
        ("meeting_synthesis", "typesafe", "jev-1.13.0", "decision"),
        ("meeting_template_selection", "openai", "chat-test", "chat"),
    ],
)
async def test_incompatible_model_is_refused_before_persistence(
    slot: str, provider: str, model: str, kind: str
) -> None:
    update = LLMTypeConfigUpdate.model_validate({"provider": provider, "model": model})
    db = AsyncMock()
    with patch(
        "src.infrastructure.llm.model_capabilities_cache.ModelCapabilitiesCache.get",
        return_value=ModelProfile(model_id=model, kind=kind),
    ):
        with pytest.raises(HTTPException) as error:
            await LLMConfigService(db).update_config(
                slot, update, uuid4(), Request({"type": "http", "headers": []})
            )
    assert error.value.status_code == 422
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("field,value", [("context_window", 10000), ("timeout_seconds", 30)])
async def test_native_settings_cannot_add_ignored_parameters_or_unbounded_latency(
    field: str, value: int
) -> None:
    from src.domains.llm_config.decision_validation import validate_decision_config

    update = LLMTypeConfigUpdate.model_validate({field: value})
    with pytest.raises(HTTPException) as error:
        validate_decision_config("meeting_template_selection", update)
    assert error.value.status_code == 422


async def test_unknown_native_model_cannot_be_saved_with_a_cold_cache() -> None:
    db = AsyncMock()
    db.scalar.return_value = None
    with patch(
        "src.infrastructure.llm.model_capabilities_cache.ModelCapabilitiesCache.get",
        return_value=None,
    ):
        with pytest.raises(HTTPException) as error:
            await LLMConfigService(db).update_config(
                "meeting_template_selection",
                LLMTypeConfigUpdate(model="invented"),
                uuid4(),
                Request({"type": "http", "headers": []}),
            )
    assert error.value.status_code == 422
    db.commit.assert_not_awaited()
