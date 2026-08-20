"""GraphInterrupt handling in the metrics decorators.

A LangGraph HITL interrupt is control flow, not a failure. Regression
2026-08-20 (prod logs): every ``hitl_dispatch`` / ``for_each_confirm``
interrupt was logged at ERROR by ``track_metrics`` — traceback plus the
full interrupt payload (recipient names, draft content: PII at ERROR
level) — and counted as ``status="error"``, falsifying the node error
metrics.

Contract pinned here, for all four wrappers (node/tool × async/sync):

- the interrupt propagates unchanged (LangGraph must see it);
- nothing is logged at ERROR, and the payload never reaches a log;
- no success/error counter is incremented — the node or tool resumes
  later and is counted once, at completion (counting "interrupted" would
  double-count the invocation across the resume);
- the duration histogram still observes (finally block, pre-existing
  behavior for every outcome).
"""

from unittest.mock import MagicMock

import pytest
from langgraph.errors import GraphInterrupt

from src.infrastructure.observability import decorators
from src.infrastructure.observability.decorators import track_metrics, track_tool_metrics


@pytest.fixture
def metric_mocks() -> tuple[MagicMock, MagicMock]:
    """Counter + histogram doubles with .labels() chaining."""
    counter = MagicMock()
    histogram = MagicMock()
    counter.labels.return_value.inc = MagicMock()
    histogram.labels.return_value.observe = MagicMock()
    return counter, histogram


@pytest.fixture
def logger_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Capture the module logger so log levels can be asserted."""
    mock = MagicMock()
    monkeypatch.setattr(decorators, "logger", mock)
    return mock


class TestNodeWrapperInterrupts:
    """track_metrics — the node wrappers."""

    @pytest.mark.asyncio
    async def test_async_interrupt_propagates_without_error_log_or_counter(
        self, metric_mocks: tuple[MagicMock, MagicMock], logger_mock: MagicMock
    ) -> None:
        counter, histogram = metric_mocks

        @track_metrics(node_name="hitl_dispatch", duration_metric=histogram, counter_metric=counter)
        async def node() -> dict:
            raise GraphInterrupt()

        with pytest.raises(GraphInterrupt):
            await node()

        logger_mock.error.assert_not_called()
        counter.labels.assert_not_called()
        histogram.labels.return_value.observe.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_interrupt_log_carries_no_payload(
        self, metric_mocks: tuple[MagicMock, MagicMock], logger_mock: MagicMock
    ) -> None:
        """Whatever is logged about an interrupt must not embed its payload."""
        counter, histogram = metric_mocks
        secret = "draft_content_with_recipient_name"

        @track_metrics(node_name="hitl_dispatch", duration_metric=histogram, counter_metric=counter)
        async def node() -> dict:
            raise GraphInterrupt((secret,))

        with pytest.raises(GraphInterrupt):
            await node()

        for call in logger_mock.mock_calls:
            assert secret not in repr(call)

    def test_sync_interrupt_propagates_without_error_log_or_counter(
        self, metric_mocks: tuple[MagicMock, MagicMock], logger_mock: MagicMock
    ) -> None:
        counter, histogram = metric_mocks

        @track_metrics(
            node_name="for_each_confirm", duration_metric=histogram, counter_metric=counter
        )
        def node() -> dict:
            raise GraphInterrupt()

        with pytest.raises(GraphInterrupt):
            node()

        logger_mock.error.assert_not_called()
        counter.labels.assert_not_called()

    @pytest.mark.asyncio
    async def test_real_error_still_logged_and_counted(
        self, metric_mocks: tuple[MagicMock, MagicMock], logger_mock: MagicMock
    ) -> None:
        """The interrupt carve-out must not swallow genuine failures."""
        counter, histogram = metric_mocks

        @track_metrics(node_name="router", duration_metric=histogram, counter_metric=counter)
        async def node() -> dict:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await node()

        logger_mock.error.assert_called_once()
        counter.labels.assert_called_once_with(node_name="router", status="error")


class TestToolWrapperInterrupts:
    """track_tool_metrics — tool-level HITL raises interrupts too."""

    @pytest.mark.asyncio
    async def test_async_interrupt_propagates_without_error_log_or_counters(
        self, metric_mocks: tuple[MagicMock, MagicMock], logger_mock: MagicMock
    ) -> None:
        counter, histogram = metric_mocks

        @track_tool_metrics(
            tool_name="send_email",
            agent_name="email_agent",
            duration_metric=histogram,
            counter_metric=counter,
        )
        async def tool() -> str:
            raise GraphInterrupt()

        with pytest.raises(GraphInterrupt):
            await tool()

        logger_mock.error.assert_not_called()
        counter.labels.assert_not_called()

    def test_sync_interrupt_propagates_without_error_log_or_counters(
        self, metric_mocks: tuple[MagicMock, MagicMock], logger_mock: MagicMock
    ) -> None:
        counter, histogram = metric_mocks

        @track_tool_metrics(
            tool_name="send_email",
            agent_name="email_agent",
            duration_metric=histogram,
            counter_metric=counter,
        )
        def tool() -> str:
            raise GraphInterrupt()

        with pytest.raises(GraphInterrupt):
            tool()

        logger_mock.error.assert_not_called()
        counter.labels.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_interrupt_skips_business_metric(
        self,
        metric_mocks: tuple[MagicMock, MagicMock],
        logger_mock: MagicMock,
    ) -> None:
        """The business outcome counter must not record an interrupt either."""
        from src.infrastructure.observability.metrics_business import agent_tool_usage_total

        counter, histogram = metric_mocks
        labels = {"agent_type": "email", "tool_name": "send_email", "outcome": "failure"}
        before = agent_tool_usage_total.labels(**labels)._value.get()

        @track_tool_metrics(
            tool_name="send_email",
            agent_name="email_agent",
            duration_metric=histogram,
            counter_metric=counter,
        )
        async def tool() -> str:
            raise GraphInterrupt()

        with pytest.raises(GraphInterrupt):
            await tool()

        assert agent_tool_usage_total.labels(**labels)._value.get() == before
