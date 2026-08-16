"""``init_semantic_services`` is a resilience boundary: it must never kill the boot.

The step's own docstring and handler say so — semantic tool selection is an
optimization, and its initialization failure degrades to full-catalogue
selection. But the except tuple listed only (RuntimeError, ValueError,
AttributeError): the selector's FIRST real failure mode — the embeddings
provider refusing the call (GoogleGenerativeAIError on a depleted quota,
HTTP 429) — extends plain Exception and sailed straight through, turning a
provider-side quota state into "Application startup failed. Exiting." on
every worker. Measured 2026-08-15 on the demonstrator: fresh tmpfs boot,
Gemini prepaid credits depleted, the API died in an import/respawn loop and
never served a single request.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.startup.agents import init_semantic_services

pytestmark = pytest.mark.unit


class _ProviderError(Exception):
    """Stands in for GoogleGenerativeAIError: Exception, not RuntimeError."""


async def test_provider_exception_does_not_kill_the_boot() -> None:
    registry = MagicMock()
    registry.initialize_semantic_tool_selector = AsyncMock(
        side_effect=_ProviderError("429 RESOURCE_EXHAUSTED: prepayment credits depleted")
    )

    # Must not raise: the boot continues with the selector degraded.
    await init_semantic_services(registry)

    registry.initialize_semantic_tool_selector.assert_awaited_once()


async def test_cancellation_still_propagates() -> None:
    """except Exception must not swallow a shutdown: CancelledError is a
    BaseException and has to keep unwinding the lifespan."""
    import asyncio

    registry = MagicMock()
    registry.initialize_semantic_tool_selector = AsyncMock(side_effect=asyncio.CancelledError())

    with pytest.raises(asyncio.CancelledError):
        await init_semantic_services(registry)
