"""Image-size arithmetic shared by every image family (ADR-305).

Both vendors speak ``WIDTHxHEIGHT``; what differs between families is which sizes
they accept and how they bill them (``families.py``). This module only knows
geometry: parsing, orientation, and "which offered size is nearest to this one".

Proportions and areas are compared on LOG ratios, so a 2:1 source is exactly as far
from a square as from a 4:1 frame and a portrait is always handled as the mirror of
the matching landscape. Every tie resolves to the smaller area — the cheaper image.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from src.core.constants import IMAGE_GENERATION_SIZE_PATTERN

Orientation = Literal["square", "landscape", "portrait"]

_SIZE_PATTERN = re.compile(IMAGE_GENERATION_SIZE_PATTERN)


@dataclass(frozen=True)
class ImageSize:
    """A pixel size, as both vendors write it (``1536x1024``).

    Attributes:
        width: Width in pixels.
        height: Height in pixels.
    """

    width: int
    height: int

    @classmethod
    def parse(cls, value: str) -> ImageSize:
        """Parse the ``WIDTHxHEIGHT`` notation.

        Args:
            value: A size string such as ``"1024x1536"``.

        Returns:
            The parsed size.

        Raises:
            ValueError: When ``value`` is not two positive integers joined by ``x``.
        """
        # ``fullmatch``: ``$`` alone also matches before a trailing newline.
        match = _SIZE_PATTERN.fullmatch(value or "")
        if match is None:
            raise ValueError(f"Invalid image size {value!r}: expected WIDTHxHEIGHT")
        return cls(int(match.group(1)), int(match.group(2)))

    def __str__(self) -> str:
        return f"{self.width}x{self.height}"

    @property
    def area(self) -> int:
        """Number of pixels."""
        return self.width * self.height

    @property
    def aspect(self) -> float:
        """Width divided by height."""
        return self.width / self.height

    @property
    def orientation(self) -> Orientation:
        """Square, landscape or portrait."""
        if self.width == self.height:
            return "square"
        return "landscape" if self.width > self.height else "portrait"


def is_well_formed_size(value: str) -> bool:
    """Whether ``value`` is a ``WIDTHxHEIGHT`` size, whatever a model offers.

    Args:
        value: The candidate string.

    Returns:
        True when :meth:`ImageSize.parse` accepts it.
    """
    return _SIZE_PATTERN.fullmatch(value or "") is not None


def _log_distance(left: float, right: float) -> float:
    return abs(math.log(left / right))


def closest_by_aspect(candidates: Iterable[ImageSize], target: ImageSize) -> ImageSize:
    """The candidate whose proportions are nearest to ``target``'s.

    Args:
        candidates: The sizes to choose from (at least one).
        target: The size whose proportions must be kept (an edit's source).

    Returns:
        The nearest candidate; a tie resolves to the smaller area.

    Raises:
        ValueError: When ``candidates`` is empty.
    """
    return min(
        _non_empty(candidates),
        key=lambda size: (_log_distance(size.aspect, target.aspect), size.area),
    )


def closest_in_orientation(candidates: Iterable[ImageSize], target: ImageSize) -> ImageSize:
    """The candidate of ``target``'s orientation whose area is nearest.

    A size the configured model does not offer keeps what the person chose it for —
    its orientation — and lands on the nearest offered area. When no offered size
    has that orientation, the nearest proportion decides.

    Args:
        candidates: The offered sizes (at least one).
        target: The size the person stored.

    Returns:
        The chosen candidate; a tie resolves to the smaller area.

    Raises:
        ValueError: When ``candidates`` is empty.
    """
    offered = _non_empty(candidates)
    same = [size for size in offered if size.orientation == target.orientation]
    if not same:
        return closest_by_aspect(offered, target)
    return min(same, key=lambda size: (_log_distance(size.area, target.area), size.area))


def _non_empty(candidates: Iterable[ImageSize]) -> list[ImageSize]:
    listed = list(candidates)
    if not listed:
        raise ValueError("No image size to choose from")
    return listed
