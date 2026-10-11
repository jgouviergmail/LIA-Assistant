"""Bounded rejection metadata; passages never enter ordinary application logs."""

from typing import Any
from uuid import UUID


class PortraitValidationError(ValueError):
    """Keep a familiar refusal and a separate, content-free diagnostic."""

    def __init__(self, message: str, details: dict[str, Any]) -> None:
        super().__init__(message)
        self.details = details


def log_consolidation_rejection(logger: Any, user_id: UUID, error: ValueError) -> None:
    """Publish bounded metadata without copying personal source passages."""
    details = {"details": error.details} if isinstance(error, PortraitValidationError) else {}
    logger.warning(
        "journal_consolidation_invalid_output", user_id=str(user_id), reason=str(error), **details
    )


def log_consolidation_failure(logger: Any, user_id: UUID, error: Exception) -> None:
    """Retain operational exception diagnostics separately from validation refusals."""
    logger.error(
        "journal_consolidation_failed",
        user_id=str(user_id),
        error=str(error),
        error_type=type(error).__name__,
        exc_info=True,
    )
