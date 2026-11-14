"""Translate a retired file source at the HTTP-facing upload/copy boundary."""

from typing import NoReturn

from src.core.conversation_execution import ExecutionRevoked
from src.core.exceptions import ResourceConflictError
from src.core.i18n_api_messages import APIMessages


def raise_retired_file_source(exc: ExecutionRevoked) -> NoReturn:
    """A late upload names the same conflict as a stale chat revision."""
    raise ResourceConflictError(
        "conversation_revision",
        detail={"error": "conversation_changed", "message": APIMessages.conversation_changed()},
    ) from exc
