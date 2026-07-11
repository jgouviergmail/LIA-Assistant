"""Public (non-admin) image-generation options endpoint.

Exposes the qualities and sizes available for the currently configured
image-generation model, derived from the active rows in
``image_generation_pricing``. Consumed by the user-facing
``ImageGenerationSettings`` component to populate its dropdowns dynamically
(replacing the previously hardcoded values).

Phase: v1.x DB-source-of-truth release (Task 17).
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from src.core.exceptions import raise_invalid_input
from src.core.session_dependencies import get_current_active_session
from src.domains.image_generation.options_cache import ImageOptionsCache
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/image-generation",
    tags=["image-generation"],
    dependencies=[Depends(get_current_active_session)],
)


# Mapping from raw size strings (as stored in image_generation_pricing) to
# i18n keys for the user-facing label. Sizes not in this map fall back to
# a generic "custom" label, with the raw value still shown in the UI.
_SIZE_LABEL_KEYS: dict[str, str] = {
    "1024x1024": "settings.image_generation.size_square",
    "1024x1536": "settings.image_generation.size_portrait",
    "1536x1024": "settings.image_generation.size_landscape",
}


class QualityOptionResponse(BaseModel):
    """One quality level supported for the configured image model.

    The price range (min/max across the model's sizes) lets the UI render
    a "(~$0.04-0.06)" hint without a second roundtrip.
    """

    value: str = Field(..., description="Quality identifier (e.g. 'low', 'medium', 'high')")
    min_cost_usd: float = Field(..., ge=0)
    max_cost_usd: float = Field(..., ge=0)


class SizeOptionResponse(BaseModel):
    """One image size supported for the configured image model."""

    value: str = Field(..., description="Image dimensions (e.g. '1024x1024')")
    label_key: str = Field(
        ...,
        description="i18n key for the user-facing label (resolved client-side)",
    )


class ImageGenerationOptionsResponse(BaseModel):
    """Response: which qualities and sizes the user can pick for image generation."""

    model_config = ConfigDict(protected_namespaces=())

    active_model: str = Field(
        ...,
        description="The image_generation LLM type's currently configured model_name",
    )
    provider: str = Field(..., description="Provider that hosts the active model")
    qualities: list[QualityOptionResponse]
    sizes: list[SizeOptionResponse]


@router.get("/options", response_model=ImageGenerationOptionsResponse)
async def get_image_generation_options(
    _user: User = Depends(get_current_active_session),
) -> ImageGenerationOptionsResponse:
    """Return the qualities and sizes available for the currently configured image model.

    The active model is read from the LLM config cache for the
    ``image_generation`` LLM type. If no model is configured, or if no
    pricing rows exist for the configured model (e.g. the admin has
    deactivated all of them), the endpoint returns 422 with an explicit
    message — the user-facing component should display a graceful empty
    state in that case.
    """
    from src.core.llm_agent_config import LLMAgentConfig
    from src.domains.llm_config.cache import LLMConfigOverrideCache
    from src.domains.llm_config.constants import LLM_DEFAULTS

    # 1. Resolve the active image_generation model. The cache lookup follows
    # the same merge logic as Configuration LLM: defaults + admin override.
    overrides = LLMConfigOverrideCache.get_override("image_generation")
    defaults: LLMAgentConfig | None = LLM_DEFAULTS.get("image_generation")
    if defaults is None:
        raise_invalid_input("Image generation LLM type is not registered in LLM_DEFAULTS")

    active_model = (overrides or {}).get("model") or defaults.model
    if not active_model:
        raise_invalid_input("Image generation LLM type has no model configured")

    # 2. Look up the model's options in the cache (DISTINCT-aggregated from
    # image_generation_pricing).
    options = ImageOptionsCache.get_options_for_model(active_model)
    if options is None:
        raise_invalid_input(
            f"No active pricing rows for image model {active_model!r}. "
            "The admin must declare at least one (model, quality, size) row "
            "in Tarification LLM Image."
        )

    return ImageGenerationOptionsResponse(
        active_model=options.model,
        provider=options.provider,
        qualities=[
            QualityOptionResponse(
                value=q.value,
                min_cost_usd=float(q.min_cost_usd),
                max_cost_usd=float(q.max_cost_usd),
            )
            for q in options.qualities
        ],
        sizes=[
            SizeOptionResponse(
                value=s.value,
                label_key=_SIZE_LABEL_KEYS.get(s.value, "settings.image_generation.size_custom"),
            )
            for s in options.sizes
        ],
    )
