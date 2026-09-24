"""Public (non-admin) image-generation options endpoint (ADR-305).

Exposes what the configured image model offers — its qualities (with price
ranges) and sizes (with orientation and billing tier) — and the person's
EFFECTIVE quality and size: their stored preferences mapped onto that offer by
the resolver the image tools use (``preferences.py``). The settings therefore
show exactly what the next image will use, even after the administrator changed
the model.

Phase: v1.x DB-source-of-truth release (Task 17); multi-provider since ADR-305.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from src.core.exceptions import raise_invalid_input
from src.core.session_dependencies import get_current_active_session
from src.domains.feature_switches.guard import require_capability
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.image_generation.preferences import (
    ImageModelNotServedError,
    active_image_options,
    effective_quality,
    effective_size,
)
from src.domains.image_generation.sizing import Orientation
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/image-generation",
    tags=["image-generation"],
    dependencies=[
        Depends(get_current_active_session),
        # Administrable capability: no point offering size and quality
        # options for a generator the instance has switched off.
        Depends(require_capability(PlatformCapability.IMAGE_GENERATION)),
    ],
)

# The user-facing label of a size is its orientation; the dimensions and the
# billing tier are shown beside it.
_SIZE_LABEL_KEY = "settings.image_generation.size_{orientation}"


class QualityOptionResponse(BaseModel):
    """One quality level offered by the configured image model.

    The price range (min/max across the model's sizes) lets the UI render
    a "(~$0.04-0.06)" hint without a second roundtrip.
    """

    value: str = Field(..., description="Quality identifier, in the model family's vocabulary")
    min_cost_usd: float = Field(..., ge=0, description="Cheapest size at this quality (USD)")
    max_cost_usd: float = Field(..., ge=0, description="Dearest size at this quality (USD)")


class SizeOptionResponse(BaseModel):
    """One image size offered by the configured image model."""

    value: str = Field(..., description="Image dimensions (e.g. '1024x1024')")
    orientation: Orientation = Field(..., description="Square, landscape or portrait")
    tier: str | None = Field(
        default=None,
        description="The family's billing tier for this size (e.g. '1k', '2k'), if it has tiers",
    )
    label_key: str = Field(
        ...,
        description="i18n key for the user-facing label (resolved client-side)",
    )


class ImageGenerationOptionsResponse(BaseModel):
    """What the person can pick, and what their next image will use."""

    model_config = ConfigDict(protected_namespaces=())

    active_model: str = Field(
        ...,
        description="The image_generation LLM type's currently configured model_name",
    )
    provider: str = Field(..., description="Provider that hosts the active model")
    qualities: list[QualityOptionResponse] = Field(..., description="Offered qualities")
    sizes: list[SizeOptionResponse] = Field(..., description="Offered sizes")
    effective_quality: str = Field(
        ...,
        description="The quality the next image uses: the stored one mapped onto the offer",
    )
    effective_size: str = Field(
        ...,
        description="The size the next generated image uses: the stored one mapped onto the offer",
    )


@router.get("/options", response_model=ImageGenerationOptionsResponse)
async def get_image_generation_options(
    user: User = Depends(get_current_active_session),
) -> ImageGenerationOptionsResponse:
    """Return what the configured image model offers and what the person will get.

    When the configured model is not served (no family, no client, or no active
    pricing row), the endpoint returns 400 naming it — the user-facing component
    displays a graceful empty state in that case.
    """
    try:
        options = active_image_options()
    except ImageModelNotServedError as exc:
        raise_invalid_input(str(exc))

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
                orientation=s.orientation,
                tier=s.tier,
                label_key=_SIZE_LABEL_KEY.format(orientation=s.orientation),
            )
            for s in options.sizes
        ],
        effective_quality=effective_quality(user.image_generation_default_quality, options),
        effective_size=effective_size(user.image_generation_default_size, options),
    )
