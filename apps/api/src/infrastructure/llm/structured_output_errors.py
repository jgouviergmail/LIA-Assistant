"""What a structured-output call raises (ADR-220, ADR-275).

Extracted from ``structured_output.py`` (file-size ratchet), the way
``strict_schema`` was: the error taxonomy is self-contained, and every caller
keeps importing it from ``structured_output``, which re-exports it.

The two classes are ONE hierarchy on purpose: a caller that only knows
``StructuredOutputError`` keeps handling a truncation by inheritance, while a
caller that cares can tell "the model was cut at its output budget" from "the
model answered something unusable".
"""

from __future__ import annotations


class StructuredOutputError(Exception):
    """Raised when structured output generation or parsing fails."""

    def __init__(
        self,
        message: str,
        provider: str,
        schema_name: str,
        raw_output: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.schema_name = schema_name
        self.raw_output = raw_output
        self.original_error = original_error


class StructuredOutputTruncatedError(StructuredOutputError):
    """The provider stopped at its output budget (ADR-275).

    The payload is incomplete by the provider's own account, and the same
    prompt cannot complete it — so nothing retries this one, and no rescue may
    close it into a shorter, valid-looking object.
    """
