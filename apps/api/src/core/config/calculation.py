"""Calculation tools configuration (ADR-318).

Contains settings for:
- The longest expression the calculator reads (published as a ``max_length``)
- The significant digits every calculator operation keeps

Reference: docs/architecture/ADR-318-Assistant-Tools-Exact-Answers-And-Own-Records.md
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    CALCULATOR_EXPRESSION_MAX_CHARS_CEILING,
    CALCULATOR_EXPRESSION_MAX_CHARS_DEFAULT,
    CALCULATOR_PRECISION_DIGITS_CEILING,
    CALCULATOR_PRECISION_DIGITS_DEFAULT,
)


class CalculationSettings(BaseSettings):
    """Settings for the exact-arithmetic tools the assistant computes with."""

    calculator_expression_max_chars: int = Field(
        default=CALCULATOR_EXPRESSION_MAX_CHARS_DEFAULT,
        ge=20,
        le=CALCULATOR_EXPRESSION_MAX_CHARS_CEILING,
        description=(
            "Longest arithmetic expression the calculator reads. Published to the "
            "planner and the ReAct loop as the parameter's max_length."
        ),
    )
    calculator_precision_digits: int = Field(
        default=CALCULATOR_PRECISION_DIGITS_DEFAULT,
        ge=10,
        le=CALCULATOR_PRECISION_DIGITS_CEILING,
        description=(
            "Significant digits every calculator operation keeps. A result that "
            "needed more is flagged approximate, never passed off as exact."
        ),
    )
