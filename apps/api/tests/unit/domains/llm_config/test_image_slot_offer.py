"""The image slot offers and accepts exactly what the image domain serves (ADR-305)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.domains.llm_config.schemas import LLMTypeConfigUpdate
from src.domains.llm_config.service import LLMConfigService

_IMAGE_CACHE = "src.domains.image_generation.options_cache.ImageOptionsCache"
_CAPS = "src.infrastructure.llm.model_capabilities_cache.ModelCapabilitiesCache"


def _profile(kind: str) -> SimpleNamespace:
    return SimpleNamespace(
        kind=kind,
        max_output_tokens=4096,
        supports_tool_calling=kind == "chat",
        supports_structured_output=kind == "chat",
        supports_vision=False,
        is_reasoning_model=False,
        supports_temperature=True,
        supports_top_p=True,
        supports_frequency_penalty=False,
        supports_presence_penalty=False,
    )


@pytest.mark.unit
class TestImageSlotList:
    """A catalogue image row no client serves is not offered."""

    def test_image_models_come_from_the_image_domain_alone(self) -> None:
        profiles = {
            "gemini-2.5-flash-image": _profile("image"),
            "gemini-3.8-flash": _profile("chat"),
            "gpt-image-2": _profile("image"),
        }
        with (
            patch(
                f"{_CAPS}.get_models_grouped_by_provider",
                return_value={
                    "gemini": ["gemini-2.5-flash-image", "gemini-3.8-flash"],
                    "openai": ["gpt-image-2"],
                },
            ),
            patch(f"{_CAPS}.get", side_effect=profiles.get),
            patch(
                f"{_IMAGE_CACHE}.get_models_grouped_by_provider",
                return_value={"openai": ["gpt-image-2"], "qwen": ["qwen-image-3.0-pro"]},
            ),
            patch.object(LLMConfigService, "_reasoning_metadata", return_value={}),
        ):
            metadata = LLMConfigService.get_provider_models(kinds=["image"])

        offered = {
            (provider, model.model_id)
            for provider, models in metadata.providers.items()
            for model in models
        }
        assert offered == {("openai", "gpt-image-2"), ("qwen", "qwen-image-3.0-pro")}


def _service() -> tuple[LLMConfigService, MagicMock]:
    """A service on a session that holds no override yet, and its ``add``."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    add = MagicMock()
    db.add = add
    service = LLMConfigService(db)
    service._log_audit = MagicMock()  # type: ignore[method-assign]
    service.get_config = AsyncMock(return_value=MagicMock())  # type: ignore[method-assign]
    return service, add


@pytest.mark.unit
@pytest.mark.asyncio
class TestImageSlotWrite:
    """The write path refuses what the list would never offer."""

    async def test_an_unserved_image_model_is_refused(self) -> None:
        with (
            patch(f"{_IMAGE_CACHE}.is_loaded", return_value=True),
            patch(f"{_IMAGE_CACHE}.get_options_for_model", return_value=None),
        ):
            with pytest.raises(HTTPException) as raised:
                await _service()[0].update_config(
                    "image_generation",
                    LLMTypeConfigUpdate(provider="gemini", model="gemini-2.5-flash-image"),
                    admin_user_id=uuid4(),
                    request=MagicMock(),
                )
        assert raised.value.status_code == 422
        assert "image_model_not_served" in str(raised.value.detail)

    @pytest.mark.parametrize(
        ("update", "serving_provider"),
        [
            (LLMTypeConfigUpdate(provider="qwen", model="qwen-image-3.0-pro"), "qwen"),
            # The UI omits a provider equal to the slot's default (openai).
            (LLMTypeConfigUpdate(model="gpt-image-1.5"), "openai"),
        ],
    )
    async def test_a_served_image_model_is_saved(
        self, update: LLMTypeConfigUpdate, serving_provider: str
    ) -> None:
        service, add = _service()
        with (
            patch(f"{_IMAGE_CACHE}.is_loaded", return_value=True),
            patch(
                f"{_IMAGE_CACHE}.get_options_for_model",
                return_value=SimpleNamespace(provider=serving_provider),
            ),
            patch(
                "src.domains.llm_config.service.LLMConfigOverrideCache.invalidate_and_reload",
                AsyncMock(),
            ),
        ):
            await service.update_config(
                "image_generation", update, admin_user_id=uuid4(), request=MagicMock()
            )
        add.assert_called_once()

    async def test_a_provider_that_does_not_serve_the_model_is_refused(self) -> None:
        """The tools run the model on its own provider: the card must not name another."""
        service, add = _service()
        with (
            patch(f"{_IMAGE_CACHE}.is_loaded", return_value=True),
            patch(
                f"{_IMAGE_CACHE}.get_options_for_model",
                return_value=SimpleNamespace(provider="qwen"),
            ),
        ):
            with pytest.raises(HTTPException) as raised:
                await service.update_config(
                    "image_generation",
                    LLMTypeConfigUpdate(provider="openai", model="qwen-image-3.0-pro"),
                    admin_user_id=uuid4(),
                    request=MagicMock(),
                )
        assert raised.value.status_code == 422
        assert "image_model_provider_mismatch" in str(raised.value.detail)
        add.assert_not_called()

    async def test_a_chat_slot_is_not_asked_about_images(self) -> None:
        options = MagicMock()
        with (
            patch(f"{_IMAGE_CACHE}.is_loaded", return_value=True),
            patch(f"{_IMAGE_CACHE}.get_options_for_model", options),
            patch(
                "src.domains.llm_config.service.LLMConfigOverrideCache.invalidate_and_reload",
                AsyncMock(),
            ),
        ):
            await _service()[0].update_config(
                "response",
                LLMTypeConfigUpdate(provider="openai", model="gpt-6-sol"),
                admin_user_id=uuid4(),
                request=MagicMock(),
            )
        options.assert_not_called()
