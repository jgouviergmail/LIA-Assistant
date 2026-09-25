"""The person's image preferences, resolved against the configured model (ADR-305).

A stored quality or size is an INTENT: it survives the administrator changing the
image model, so it is never rejected for not being offered — it is mapped, here,
by the one resolver the tools and ``GET /image-generation/options`` share. The
settings therefore show exactly what the next image will use.

- A quality the model does not offer becomes the CHEAPEST it offers: a preference
  is also a budget, and the fallback never spends more than intended.
- A size it does not offer becomes the offered size of the same orientation with
  the nearest area (``sizing.closest_in_orientation``).
- An edit keeps the SOURCE's proportions, within the billing tier of the size the
  person prefers.

The prompt enhancement (ADR-315) is an opt-in of the person that the operator can
withdraw: :func:`prompt_enhancement_offered` is the one reading of that switch.
"""

from __future__ import annotations

from src.core.config import settings
from src.core.constants import IMAGE_GENERATION_LLM_TYPE, IMAGE_GENERATION_SIZE_DEFAULT
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.image_generation.options_cache import ImageOptionsCache, ModelOptions
from src.domains.image_generation.sizing import (
    ImageSize,
    closest_by_aspect,
    closest_in_orientation,
    is_well_formed_size,
)


class ImageModelNotServedError(Exception):
    """The configured image model has no offer a client can serve."""


def configured_image_model() -> str:
    """The image slot's model, resolved like every slot's (defaults, then override)."""
    return get_llm_config_for_agent(settings, IMAGE_GENERATION_LLM_TYPE).model


def active_image_options() -> ModelOptions:
    """What the configured image model offers right now.

    Returns:
        The model's options (provider, family, qualities, sizes).

    Raises:
        ImageModelNotServedError: When no family, client or active pricing row
            serves the configured model — the message names it.
    """
    model = configured_image_model()
    options = ImageOptionsCache.get_options_for_model(model)
    if options is None:
        raise ImageModelNotServedError(
            f"The configured image model {model!r} is not served: it needs a provider "
            "client and at least one active pricing row its family accepts "
            "(Settings > Administration > Image pricing)."
        )
    return options


def prompt_enhancement_offered() -> bool:
    """Whether the operator offers the prompt enhancement (read at call time).

    The one reading of the switch: the image tool and the settings page both ask
    it, so the page never offers what the tool would ignore (ADR-315).
    """
    return settings.image_prompt_enhancement_enabled


def effective_quality(stored: str | None, options: ModelOptions) -> str:
    """The quality the next image uses.

    Args:
        stored: The person's stored preference.
        options: The configured model's offer.

    Returns:
        ``stored`` when offered, else the cheapest offered quality.
    """
    if any(quality.value == stored for quality in options.qualities):
        return str(stored)
    return min(options.qualities, key=lambda quality: quality.min_cost_usd).value


def effective_size(stored: str | None, options: ModelOptions) -> str:
    """The size the next generated image uses.

    Args:
        stored: The person's stored preference.
        options: The configured model's offer.

    Returns:
        ``stored`` when offered, else the offered size of the same orientation
        with the nearest area (the default size's intent when nothing usable is
        stored).
    """
    offered = [ImageSize.parse(size.value) for size in options.sizes]
    if stored is not None and any(size.value == stored for size in options.sizes):
        return stored
    intent = stored if stored is not None and is_well_formed_size(stored) else None
    target = ImageSize.parse(intent or IMAGE_GENERATION_SIZE_DEFAULT)
    return str(closest_in_orientation(offered, target))


def edit_size(source: ImageSize, preferred_size: str, options: ModelOptions) -> str:
    """The output size of an edit.

    Args:
        source: The source image's displayed size.
        preferred_size: The person's effective size (an offered one).
        options: The configured model's offer.

    Returns:
        The offered size nearest to the source's proportions, within the
        billing tier of ``preferred_size``.
    """
    tier = next((size.tier for size in options.sizes if size.value == preferred_size), None)
    candidates = [ImageSize.parse(size.value) for size in options.sizes if size.tier == tier]
    if not candidates:
        candidates = [ImageSize.parse(size.value) for size in options.sizes]
    return str(closest_by_aspect(candidates, source))
