"""Image families: what a model accepts and how it is billed (ADR-305).

An image model is servable only when a family declares it. Every surface reads
this one answer: the pricing write path, the options offered to the person, the
image slot's model list, the LLM configuration write path and the tools. A model
no family declares cannot be priced, offered, selected or run.

Families are resolved like reasoning profiles (ADR-245): ordered
``(family, model prefixes)`` rules, first match on the family's provider and a
prefix wins. A new vendor is a family here plus a client in ``providers/`` —
``client.py`` refuses to import when a family has no client, so a declared family
IS a servable one.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domains.image_generation.sizing import ImageSize, is_well_formed_size


@dataclass(frozen=True)
class FixedSizes:
    """A vendor that prices an explicit list of sizes.

    Attributes:
        sizes: The accepted sizes.
    """

    sizes: tuple[ImageSize, ...]

    def accepts(self, size: ImageSize) -> bool:
        """Whether ``size`` is one of the listed sizes."""
        return size in self.sizes

    def describe(self) -> str:
        """The accepted sizes, for a refusal message."""
        return ", ".join(str(size) for size in self.sizes)


@dataclass(frozen=True)
class AreaEnvelope:
    """A vendor that accepts any size within an area and aspect envelope.

    Attributes:
        min_area: Smallest accepted pixel area.
        max_area: Largest accepted pixel area.
        max_aspect: Largest accepted ratio between the long and the short edge.
    """

    min_area: int
    max_area: int
    max_aspect: float

    def accepts(self, size: ImageSize) -> bool:
        """Whether ``size`` lies within the envelope."""
        long_edge = max(size.width, size.height)
        short_edge = min(size.width, size.height)
        return (
            self.min_area <= size.area <= self.max_area
            and long_edge / short_edge <= self.max_aspect
        )

    def describe(self) -> str:
        """The envelope, for a refusal message."""
        return (
            f"an area between {self.min_area} and {self.max_area} pixels "
            f"and an aspect ratio within 1:{self.max_aspect:g} to {self.max_aspect:g}:1"
        )


@dataclass(frozen=True)
class BillingTier:
    """One billing tier, keyed by the output's pixel area.

    Attributes:
        name: The tier's identifier (published to the settings, e.g. ``"1k"``).
        max_area: Largest area of the tier, inclusive; ``None`` for the last tier.
    """

    name: str
    max_area: int | None


@dataclass(frozen=True)
class ImageFamily:
    """What a family of image models accepts and how its vendor bills it.

    Attributes:
        key: Stable identifier (logs, tests).
        provider: The provider whose client serves the family.
        qualities: The accepted quality identifiers.
        sizes: The sizes the vendor accepts.
        billing_tiers: Area tiers the vendor bills by, in increasing order; empty
            when the price does not depend on a tier.
        bills_reference_images_per_image: Whether the vendor bills each image sent
            to an edit at a per-image price. ``False`` for a vendor that bills
            input images as tokens, which a per-image table cannot express.
        source_max_edge: Longest edge an edit's source image is fitted within;
            ``None`` fits it within the OUTPUT size instead.
        source_max_bytes: Largest encoded source image the vendor accepts.
    """

    key: str
    provider: str
    qualities: tuple[str, ...]
    sizes: FixedSizes | AreaEnvelope
    billing_tiers: tuple[BillingTier, ...]
    bills_reference_images_per_image: bool
    source_max_edge: int | None
    source_max_bytes: int

    def tier_of(self, size: ImageSize) -> str | None:
        """The billing tier of an output ``size``, or ``None`` without tiers."""
        for tier in self.billing_tiers:
            if tier.max_area is None or size.area <= tier.max_area:
                return tier.name
        return None

    def source_box(self, output: ImageSize) -> ImageSize:
        """The box an edit's source image is fitted within before it is sent.

        Args:
            output: The size the edit will produce.

        Returns:
            ``output`` when the family fits the source within it, else a square of
            ``source_max_edge``.
        """
        if self.source_max_edge is None:
            return output
        return ImageSize(self.source_max_edge, self.source_max_edge)

    def refusal(self, quality: str, size: str) -> str | None:
        """Why this family cannot price or produce ``(quality, size)``.

        Args:
            quality: A quality identifier.
            size: A ``WIDTHxHEIGHT`` size.

        Returns:
            ``None`` when both are accepted, else a sentence naming what is.
        """
        if quality not in self.qualities:
            return (
                f"Quality {quality!r} is not offered by the {self.key} family; "
                f"accepted: {', '.join(self.qualities)}."
            )
        if not is_well_formed_size(size):
            return f"Size {size!r} is not a WIDTHxHEIGHT size."
        if not self.sizes.accepts(ImageSize.parse(size)):
            return (
                f"Size {size} is not accepted by the {self.key} family; "
                f"it accepts {self.sizes.describe()}."
            )
        return None

    def pricing_refusal(self, quality: str, size: str, *, has_input_price: bool) -> str | None:
        """Why a pricing row cannot be stored for this family.

        A family that bills reference images per image REQUIRES their price — an
        edit priced without it would under-bill every time — and one that does
        not REFUSES it, or an edit would be billed for something the vendor
        prices otherwise.

        Args:
            quality: The row's quality.
            size: The row's size.
            has_input_price: Whether the row carries a reference-image price.

        Returns:
            ``None`` when the row is valid, else a sentence naming the rule.
        """
        refusal = self.refusal(quality, size)
        if refusal is not None:
            return refusal
        if self.bills_reference_images_per_image and not has_input_price:
            return (
                f"The {self.key} family bills each reference image of an edit: "
                "cost_per_input_image_usd is required."
            )
        if not self.bills_reference_images_per_image and has_input_price:
            return (
                f"The {self.key} family does not bill reference images per image: "
                "cost_per_input_image_usd must be empty."
            )
        return None


# The three sizes OpenAI publishes a per-image price for. gpt-image-2 also accepts
# arbitrary sizes, but only these three have a per-image figure to bill.
OPENAI_GPT_IMAGE = ImageFamily(
    key="openai_gpt_image",
    provider="openai",
    qualities=("low", "medium", "high"),
    sizes=FixedSizes(
        sizes=(ImageSize(1024, 1024), ImageSize(1536, 1024), ImageSize(1024, 1536)),
    ),
    billing_tiers=(),
    bills_reference_images_per_image=False,
    source_max_edge=None,
    source_max_bytes=50 * 1024 * 1024,
)

# Qwen Image 3.0 (text to image and image to image). Documented envelope: area from
# 512x512 to 2048x2048, aspect from 1:8 to 8:1; billing tier by output area
# (<= 2,250,000 px is 1K); input images up to 2048 px per edge and 10 MB.
QWEN_IMAGE_3 = ImageFamily(
    key="qwen_image_3",
    provider="qwen",
    qualities=("standard",),
    sizes=AreaEnvelope(min_area=512 * 512, max_area=2048 * 2048, max_aspect=8.0),
    billing_tiers=(BillingTier("1k", 2_250_000), BillingTier("2k", None)),
    bills_reference_images_per_image=True,
    source_max_edge=2048,
    source_max_bytes=10 * 1024 * 1024,
)

#: The provider a rule applies to is its family's: a rule cannot pair one vendor's
#: model names with another vendor's family.
_RULES: tuple[tuple[ImageFamily, tuple[str, ...]], ...] = (
    (OPENAI_GPT_IMAGE, ("gpt-image-", "chatgpt-image-")),
    (QWEN_IMAGE_3, ("qwen-image-3.0",)),
)

ALL_FAMILIES: tuple[ImageFamily, ...] = tuple(family for family, _ in _RULES)


def resolve_image_family(provider: str, model: str) -> ImageFamily | None:
    """The family that serves ``model`` on ``provider``, if any.

    Args:
        provider: The provider identifier stored beside the model.
        model: The model name.

    Returns:
        The family, or ``None`` when no family declares the model — which makes it
        unservable everywhere.
    """
    for family, prefixes in _RULES:
        if provider == family.provider and model.startswith(prefixes):
            return family
    return None
