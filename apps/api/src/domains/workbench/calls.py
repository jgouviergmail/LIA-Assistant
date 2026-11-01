"""The one seam every provider call of the workbench goes through (ADR-369).

``provider_call`` times the call, turns a client failure into the refusal it
amounts to — by type and status, knowing whether the call was an ACT
(``errors.refusal_for``) — and counts the outcome under closed labels. A
refusal the service raised itself passes through, counted under its code. A
cancellation is neither: it propagates untouched (the person left).
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from src.core.exceptions import BaseAPIException
from src.domains.workbench.errors import refusal_code_of, refuse_provider_failure
from src.domains.workbench.features import WorkbenchTool
from src.infrastructure.observability.metrics_workbench import (
    workbench_provider_latency_seconds,
    workbench_requests_total,
)

#: The outcome label of a call that succeeded.
OK = "ok"


@asynccontextmanager
async def provider_call(tool: WorkbenchTool, operation: str, *, act: bool) -> AsyncIterator[None]:
    """Run one provider call of ``tool`` under the workbench's failure contract.

    Args:
        tool: The tool calling.
        operation: The act, a closed word per route (``list``, ``send``…).
        act: Whether the call can change something at the provider.

    Yields:
        Nothing; the caller makes its provider call inside the block.

    Raises:
        BaseAPIException: The workbench refusal a failure amounts to.
    """
    started = time.perf_counter()
    try:
        yield
    except BaseAPIException as refusal:
        code = refusal_code_of(refusal)
        if code is not None:
            _count(tool, operation, code)
            raise
        _count_failure(tool, operation, refusal, act=act)
    except Exception as failure:
        _count_failure(tool, operation, failure, act=act)
    else:
        _count(tool, operation, OK)
    finally:
        workbench_provider_latency_seconds.labels(tool=tool.value).observe(
            time.perf_counter() - started
        )


def _count_failure(tool: WorkbenchTool, operation: str, failure: Exception, *, act: bool) -> None:
    try:
        refuse_provider_failure(failure, act=act)
    except BaseAPIException as refusal:
        _count(tool, operation, refusal_code_of(refusal) or "error")
        raise


def _count(tool: WorkbenchTool, operation: str, outcome: str) -> None:
    workbench_requests_total.labels(tool=tool.value, operation=operation, outcome=outcome).inc()
