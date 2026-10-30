"""Fail over to another model only when the primary's outcome is known (owner decision Q3 (a)).

``ModelFallbackMiddleware`` called the next model of its chain on ANY failure of the
primary. After a timeout, or a connection lost once the request was sent, the primary's
generation may still be running and billed: calling another model then buys the same
generation a second time, on another provider — the relaunch the owner ruled out on
2026-10-28 (ADR-221 amendment). A failure whose outcome is known still fails over,
which is what the operator's chain (``FALLBACK_MODELS``, ADR-244) is for: the provider
answered with an error status, or the request never reached it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import ModelFallbackMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse

from src.infrastructure.utils.request_outcome import outcome_unknown


class _OutcomeUnknown(BaseException):
    """Carries an unknown-outcome failure past the fallback loop, which catches ``Exception``."""

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error


class KnownOutcomeFallbackMiddleware(ModelFallbackMiddleware):
    """The fallback chain, entered only for a failure whose outcome is known."""

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        def guarded(attempt: ModelRequest[Any]) -> ModelResponse[Any]:
            try:
                return handler(attempt)
            except Exception as error:
                if outcome_unknown(error):
                    raise _OutcomeUnknown(error) from error
                raise

        try:
            return super().wrap_model_call(request, guarded)
        except _OutcomeUnknown as stop:
            raise stop.error from stop.error.__cause__

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        async def guarded(attempt: ModelRequest[Any]) -> ModelResponse[Any]:
            try:
                return await handler(attempt)
            except Exception as error:
                if outcome_unknown(error):
                    raise _OutcomeUnknown(error) from error
                raise

        try:
            return await super().awrap_model_call(request, guarded)
        except _OutcomeUnknown as stop:
            raise stop.error from stop.error.__cause__


__all__ = ["KnownOutcomeFallbackMiddleware"]
