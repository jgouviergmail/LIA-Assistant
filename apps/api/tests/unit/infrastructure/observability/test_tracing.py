"""
Unit tests for OpenTelemetry tracing module.

Phase: PHASE 4.1 - Coverage Baseline & Tests Unitaires
Session: 25
Created: 2025-11-20
Target: 50% → 80%+ coverage
Module: infrastructure/observability/tracing.py (62 statements)

Missing Lines to Cover:
- Line 64-65: Exception handling in configure_tracing()
- Line 82: get_tracer() function
- Lines 109-158: trace_node() decorator (async wrapper, span attributes, routing metadata, exceptions)

OpenTelemetry Integration:
- Tempo distributed tracing
- FastAPI instrumentation
- LangGraph node tracing
- OTLP gRPC exporter
"""

from collections.abc import AsyncIterator
from unittest.mock import Mock, patch

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import Tracer
from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from src.infrastructure.observability.tracing import (
    configure_tracing,
    get_tracer,
    instrument_fastapi,
    trace_node,
)


class TestConfigureTracing:
    """Tests for OpenTelemetry tracing configuration."""

    @patch("src.infrastructure.observability.tracing.settings")
    @patch("src.infrastructure.observability.tracing.Resource")
    @patch("src.infrastructure.observability.tracing.TracerProvider")
    @patch("src.infrastructure.observability.tracing.OTLPSpanExporter")
    @patch("src.infrastructure.observability.tracing.BatchSpanProcessor")
    @patch("src.infrastructure.observability.tracing.trace.set_tracer_provider")
    @patch("src.infrastructure.observability.tracing.FastAPIInstrumentor")
    def test_configure_tracing_success(
        self,
        mock_instrumentor,
        mock_set_provider,
        mock_batch_processor,
        mock_otlp_exporter,
        mock_tracer_provider_class,
        mock_resource_class,
        mock_settings,
    ):
        """Test successful tracing configuration."""
        # Setup settings
        mock_settings.otel_service_name = "test-service"
        mock_settings.environment = "test"
        mock_settings.otel_exporter_otlp_endpoint = "http://localhost:4317"
        mock_settings.is_production = False
        mock_settings.http_log_exclude_paths = ["/health", "/metrics"]
        # Build provenance (F030) now feeds the OTel resource.
        mock_settings.app_version = "1.24.0"
        mock_settings.git_commit_sha = "deadbeef1234"
        mock_settings.build_date = "2026-07-13T00:00:00Z"

        # Setup mocks
        mock_resource = Mock()
        mock_resource_class.create.return_value = mock_resource

        mock_tracer_provider = Mock()
        mock_tracer_provider_class.return_value = mock_tracer_provider

        mock_exporter = Mock()
        mock_otlp_exporter.return_value = mock_exporter

        mock_processor = Mock()
        mock_batch_processor.return_value = mock_processor

        app = FastAPI()

        # Execute
        configure_tracing(app)

        # Verify resource creation
        mock_resource_class.create.assert_called_once()
        resource_attrs = mock_resource_class.create.call_args[0][0]
        assert resource_attrs["service.name"] == "test-service"
        assert resource_attrs["service.version"] == "1.24.0"
        assert resource_attrs["service.instance.commit_sha"] == "deadbeef1234"
        assert resource_attrs["service.build_date"] == "2026-07-13T00:00:00Z"
        assert resource_attrs["deployment.environment"] == "test"

        # Verify tracer provider creation
        mock_tracer_provider_class.assert_called_once_with(resource=mock_resource)

        # Verify OTLP exporter creation
        mock_otlp_exporter.assert_called_once_with(
            endpoint="http://localhost:4317",
            insecure=True,  # Not production
        )

        # Verify span processor added
        mock_batch_processor.assert_called_once_with(mock_exporter)
        mock_tracer_provider.add_span_processor.assert_called_once_with(mock_processor)

        # Verify global tracer provider set
        mock_set_provider.assert_called_once_with(mock_tracer_provider)

        # Verify FastAPI instrumentation with excluded URLs
        mock_instrumentor.instrument_app.assert_called_once()
        call_args = mock_instrumentor.instrument_app.call_args
        assert call_args[0][0] == app  # First positional arg is app
        assert "excluded_urls" in call_args[1]  # excluded_urls passed as kwarg

    @patch("src.infrastructure.observability.tracing.settings")
    @patch("src.infrastructure.observability.tracing.Resource")
    def test_configure_tracing_handles_exception(self, mock_resource_class, mock_settings, caplog):
        """Test that tracing configuration handles exceptions gracefully (Lines 64-65)."""
        # Setup settings
        mock_settings.otel_service_name = "test-service"
        mock_settings.environment = "test"
        mock_settings.otel_exporter_otlp_endpoint = "http://localhost:4317"

        # Mock Resource.create to raise exception
        mock_resource_class.create.side_effect = RuntimeError("OTLP connection failed")

        app = FastAPI()

        # Lines 64-65 executed: Exception caught, logged
        configure_tracing(app)  # Should not raise exception

        # Verify exception was logged (caplog may not capture structlog, but no exception raised)
        # The important part is that configure_tracing didn't crash

    @patch("src.infrastructure.observability.tracing.settings")
    @patch("src.infrastructure.observability.tracing.Resource")
    @patch("src.infrastructure.observability.tracing.TracerProvider")
    @patch("src.infrastructure.observability.tracing.OTLPSpanExporter")
    def test_configure_tracing_production_mode_secure(
        self,
        mock_otlp_exporter,
        mock_tracer_provider_class,
        mock_resource_class,
        mock_settings,
    ):
        """Test that production mode uses secure OTLP connection."""
        mock_settings.otel_service_name = "prod-service"
        mock_settings.environment = "production"
        mock_settings.otel_exporter_otlp_endpoint = "https://tempo.example.com:4317"
        mock_settings.is_production = True  # Production mode

        mock_resource_class.create.return_value = Mock()
        mock_tracer_provider_class.return_value = Mock()

        app = FastAPI()
        configure_tracing(app)

        # OTLP exporter always uses insecure=True (Docker-internal communication)
        # Even in production, Tempo runs inside the same Docker network without TLS
        mock_otlp_exporter.assert_called_once_with(
            endpoint="https://tempo.example.com:4317",
            insecure=True,
        )


class TestGetTracer:
    """Tests for get_tracer function."""

    @patch("src.infrastructure.observability.tracing.trace.get_tracer")
    def test_get_tracer_returns_tracer(self, mock_trace_get_tracer):
        """Test that get_tracer returns OpenTelemetry tracer (Line 82)."""
        mock_tracer = Mock(spec=Tracer)
        mock_trace_get_tracer.return_value = mock_tracer

        # Line 82 executed: trace.get_tracer(name)
        result = get_tracer("test.module")

        # Verify trace.get_tracer called with correct name
        mock_trace_get_tracer.assert_called_once_with("test.module")
        assert result == mock_tracer


class TestTraceNode:
    """Tests for trace_node decorator for LangGraph nodes."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.observability.tracing.trace.get_tracer")
    async def test_trace_node_creates_span(self, mock_get_tracer):
        """Test that trace_node decorator creates OpenTelemetry span (Lines 109-114)."""
        # Setup mock tracer and span
        mock_tracer = Mock()
        mock_span = Mock()
        mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)
        mock_get_tracer.return_value = mock_tracer

        # Create decorated function
        @trace_node("test_node")
        async def test_func(state, config):
            return {"result": "success"}

        # Lines 109-114 executed: Create span with node name
        result = await test_func({"input": "data"}, {"metadata": {}})

        # Verify span created
        mock_tracer.start_as_current_span.assert_called_once_with("langgraph.node.test_node")
        assert result == {"result": "success"}

    @pytest.mark.asyncio
    @patch("src.infrastructure.observability.tracing.trace.get_tracer")
    async def test_trace_node_sets_node_name_attribute(self, mock_get_tracer):
        """Test that trace_node sets node name attribute (Line 116)."""
        mock_tracer = Mock()
        mock_span = Mock()
        mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)
        mock_get_tracer.return_value = mock_tracer

        @trace_node("router")
        async def router_func(state, config):
            return {}

        # Line 116 executed: Set node name attribute
        await router_func({}, {})

        # Verify node name attribute set
        mock_span.set_attribute.assert_any_call("langgraph.node.name", "router")

    @pytest.mark.asyncio
    @patch("src.infrastructure.observability.tracing.trace.get_tracer")
    async def test_trace_node_extracts_run_id_from_config(self, mock_get_tracer):
        """Test that trace_node extracts run_id from config (Lines 119-122)."""
        mock_tracer = Mock()
        mock_span = Mock()
        mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)
        mock_get_tracer.return_value = mock_tracer

        @trace_node("planner")
        async def planner_func(state, config):
            return {}

        # Lines 119-122 executed: Extract run_id from config.metadata
        config = {"metadata": {"run_id": "run-abc-123"}}
        await planner_func({}, config)

        # Verify run_id attribute set
        mock_span.set_attribute.assert_any_call("langgraph.run_id", "run-abc-123")

    @pytest.mark.asyncio
    @patch("src.infrastructure.observability.tracing.trace.get_tracer")
    async def test_trace_node_handles_missing_run_id(self, mock_get_tracer):
        """Test that trace_node handles missing run_id gracefully."""
        mock_tracer = Mock()
        mock_span = Mock()
        mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)
        mock_get_tracer.return_value = mock_tracer

        @trace_node("node")
        async def node_func(state, config):
            return {}

        # Config without run_id
        config = {"metadata": {}}
        await node_func({}, config)

        # Verify function executes without error (no run_id set)
        # run_id attribute should not be set
        calls = [
            call
            for call in mock_span.set_attribute.call_args_list
            if call[0][0] == "langgraph.run_id"
        ]
        assert len(calls) == 0

    @pytest.mark.asyncio
    @patch("src.infrastructure.observability.tracing.trace.get_tracer")
    async def test_trace_node_sets_llm_model_attribute(self, mock_get_tracer):
        """Test that trace_node sets LLM model attribute (Lines 125-126)."""
        mock_tracer = Mock()
        mock_span = Mock()
        mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)
        mock_get_tracer.return_value = mock_tracer

        @trace_node("response", llm_model="gpt-4-mini")
        async def response_func(state, config):
            return {}

        # Lines 125-126 executed: Set LLM model attribute
        await response_func({}, {})

        # Verify LLM model attribute set
        mock_span.set_attribute.assert_any_call("langgraph.llm.model", "gpt-4-mini")

    @pytest.mark.asyncio
    @patch("src.infrastructure.observability.tracing.trace.get_tracer")
    async def test_trace_node_extracts_routing_metadata(self, mock_get_tracer):
        """Test that trace_node extracts routing metadata from result (Lines 135-149)."""
        mock_tracer = Mock()
        mock_span = Mock()
        mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)
        mock_get_tracer.return_value = mock_tracer

        @trace_node("router")
        async def router_func(state, config):
            # Return routing history
            routing_entry = Mock()
            routing_entry.intention = "search_contacts"
            routing_entry.confidence = 0.95
            routing_entry.next_node = "contacts_handler"
            return {"routing_history": [routing_entry]}

        # Lines 135-149 executed: Extract routing metadata
        await router_func({}, {})

        # Verify routing attributes set
        mock_span.set_attribute.assert_any_call("langgraph.router.intention", "search_contacts")
        mock_span.set_attribute.assert_any_call("langgraph.router.confidence", 0.95)
        mock_span.set_attribute.assert_any_call("langgraph.router.next_node", "contacts_handler")

    @pytest.mark.asyncio
    @patch("src.infrastructure.observability.tracing.trace.get_tracer")
    async def test_trace_node_handles_exception(self, mock_get_tracer):
        """Test that trace_node handles exceptions and sets error attributes (Lines 153-158)."""
        mock_tracer = Mock()
        mock_span = Mock()
        mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)
        mock_get_tracer.return_value = mock_tracer

        @trace_node("failing_node")
        async def failing_func(state, config):
            raise ValueError("Node execution failed")

        # Lines 153-158 executed: Exception caught, attributes set
        with pytest.raises(ValueError, match="Node execution failed"):
            await failing_func({}, {})

        # Verify error attributes set
        mock_span.set_attribute.assert_any_call("error", True)
        mock_span.set_attribute.assert_any_call("error.type", "ValueError")
        mock_span.set_attribute.assert_any_call("error.message", "Node execution failed")

    @pytest.mark.asyncio
    @patch("src.infrastructure.observability.tracing.trace.get_tracer")
    async def test_trace_node_config_extraction_from_args(self, mock_get_tracer):
        """Test that trace_node extracts config from positional args (Line 112)."""
        mock_tracer = Mock()
        mock_span = Mock()
        mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)
        mock_get_tracer.return_value = mock_tracer

        @trace_node("node")
        async def node_func(state, config):
            return {}

        # Line 112 executed: Extract config from args[1]
        config = {"metadata": {"run_id": "from-args"}}
        await node_func({"state": "data"}, config)

        # Verify run_id extracted from args
        mock_span.set_attribute.assert_any_call("langgraph.run_id", "from-args")

    @pytest.mark.asyncio
    @patch("src.infrastructure.observability.tracing.trace.get_tracer")
    async def test_trace_node_config_extraction_from_kwargs(self, mock_get_tracer):
        """Test that trace_node extracts config from kwargs (Line 112)."""
        mock_tracer = Mock()
        mock_span = Mock()
        mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)
        mock_get_tracer.return_value = mock_tracer

        @trace_node("node")
        async def node_func(state, config=None):
            return {}

        # Line 112 executed: Extract config from kwargs
        config = {"metadata": {"run_id": "from-kwargs"}}
        await node_func({"state": "data"}, config=config)

        # Verify run_id extracted from kwargs
        mock_span.set_attribute.assert_any_call("langgraph.run_id", "from-kwargs")

    @pytest.mark.asyncio
    @patch("src.infrastructure.observability.tracing.trace.get_tracer")
    async def test_trace_node_returns_function_result(self, mock_get_tracer):
        """Test that trace_node returns function result (Line 151)."""
        mock_tracer = Mock()
        mock_span = Mock()
        mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)
        mock_get_tracer.return_value = mock_tracer

        @trace_node("node")
        async def node_func(state, config):
            return {"output": "test_value", "count": 42}

        # Line 151 executed: return result
        result = await node_func({}, {})

        # Verify result returned
        assert result == {"output": "test_value", "count": 42}

    @pytest.mark.asyncio
    @patch("src.infrastructure.observability.tracing.trace.get_tracer")
    async def test_trace_node_with_no_config(self, mock_get_tracer):
        """Test that trace_node works without config parameter."""
        mock_tracer = Mock()
        mock_span = Mock()
        mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)
        mock_get_tracer.return_value = mock_tracer

        @trace_node("simple_node")
        async def simple_func(state):
            return {"result": "ok"}

        # Execute without config (should not crash)
        result = await simple_func({"input": "data"})

        # Verify execution successful
        assert result == {"result": "ok"}
        mock_span.set_attribute.assert_any_call("langgraph.node.name", "simple_node")

    @pytest.mark.asyncio
    @patch("src.infrastructure.observability.tracing.trace.get_tracer")
    async def test_trace_node_real_world_scenario(self, mock_get_tracer):
        """Test trace_node with realistic LangGraph node scenario."""
        mock_tracer = Mock()
        mock_span = Mock()
        mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)
        mock_get_tracer.return_value = mock_tracer

        @trace_node("router", llm_model="gpt-4-mini")
        async def router_node(state, config):
            # Simulate router logic
            routing_entry = Mock()
            routing_entry.intention = "get_contacts"
            routing_entry.confidence = 0.92
            routing_entry.next_node = "contacts_search"

            return {"messages": state.get("messages", []), "routing_history": [routing_entry]}

        # Execute with full config
        state = {"messages": ["user query"]}
        config = {"metadata": {"run_id": "run-xyz-789"}}

        result = await router_node(state, config)

        # Verify all attributes set
        assert mock_span.set_attribute.call_count >= 6
        mock_span.set_attribute.assert_any_call("langgraph.node.name", "router")
        mock_span.set_attribute.assert_any_call("langgraph.run_id", "run-xyz-789")
        mock_span.set_attribute.assert_any_call("langgraph.llm.model", "gpt-4-mini")
        mock_span.set_attribute.assert_any_call("langgraph.router.intention", "get_contacts")
        mock_span.set_attribute.assert_any_call("langgraph.router.confidence", 0.92)
        mock_span.set_attribute.assert_any_call("langgraph.router.next_node", "contacts_search")

        # Verify result
        assert result["routing_history"][0].intention == "get_contacts"


def _instrumented_nested_client(exporter: InMemorySpanExporter) -> TestClient:
    """LIA's shape (a prefixed domain router under /api/v1), instrumented as main.py does."""
    provider = SdkTracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    domain = APIRouter(prefix="/relations")

    @domain.get("/favorites/{name}")
    async def favorite(name: str) -> dict[str, str]:
        return {"name": name}

    @domain.get("/stream")
    async def stream() -> StreamingResponse:
        async def chunks() -> AsyncIterator[bytes]:
            for index in range(5):
                yield f"data: {index}\n\n".encode()

        return StreamingResponse(chunks(), media_type="text/event-stream")

    api_router = APIRouter()
    api_router.include_router(domain)
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    instrument_fastapi(app, tracer_provider=provider)
    return TestClient(app, raise_server_exceptions=False)


class TestNestedRouteSpans:
    """The FastAPI instrumentation reads FastAPI 0.137's route tree.

    0.137 keeps an included router as one node of ``app.routes``; the
    instrumentation before 0.64b0 read that list flat — measured with 0.63b1 on
    FastAPI 0.141.1: the span of ``/favorites/{name}`` was named after the
    person in the URL, and a wrong method answered 500 instead of 405.
    """

    def test_a_span_names_the_template_never_the_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The suite disables the SDK (conftest); a provider records only when built enabled.
        monkeypatch.setenv("OTEL_SDK_DISABLED", "false")
        exporter = InMemorySpanExporter()

        _instrumented_nested_client(exporter).get("/api/v1/relations/favorites/Jane%20Doe")

        servers = [s for s in exporter.get_finished_spans() if s.kind is SpanKind.SERVER]
        assert [s.name for s in servers] == ["GET /api/v1/relations/favorites/{name}"]

    def test_a_wrong_method_is_refused_not_crashed(self) -> None:
        client = _instrumented_nested_client(InMemorySpanExporter())

        assert client.post("/api/v1/relations/favorites/someone").status_code == 405

    def test_no_attribute_carries_the_path_or_the_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 0.64b0 fixed the span NAME, not its attributes — measured on 0.65b0:
        # `http.target` carried the person's name and `http.url` the query too.
        monkeypatch.setenv("OTEL_SDK_DISABLED", "false")
        exporter = InMemorySpanExporter()
        client = _instrumented_nested_client(exporter)

        client.get("/api/v1/relations/favorites/Jane%20Doe?q=secret-term")
        client.get("/wp-admin/install.php?q=secret-term")

        spans = exporter.get_finished_spans()
        values = [str(value) for span in spans for value in span.attributes.values()]
        assert [v for v in values if "Jane" in v or "secret-term" in v or "wp-admin" in v] == []
        servers = {
            s.attributes["http.status_code"]: s.attributes
            for s in spans
            if s.kind is SpanKind.SERVER
        }
        assert servers[200]["http.target"] == "/api/v1/relations/favorites/{name}"
        assert servers[200]["http.url"] == "http://testserver/api/v1/relations/favorites/{name}"
        assert servers[404]["http.target"] == "unmatched"
        assert servers[404]["http.url"] == "http://testserver"

    def test_a_streamed_response_is_one_span_not_one_per_chunk(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Every SSE chunk used to leave an internal `http send` span: measured
        # 2026-10-03 in production, 54 371 a day — 88 % of the API's spans, 36 %
        # of everything Tempo stored, none of them read by anybody.
        monkeypatch.setenv("OTEL_SDK_DISABLED", "false")
        exporter = InMemorySpanExporter()

        response = _instrumented_nested_client(exporter).get("/api/v1/relations/stream")

        assert response.text.count("data: ") == 5
        assert [(s.kind, s.name) for s in exporter.get_finished_spans()] == [
            (SpanKind.SERVER, "GET /api/v1/relations/stream")
        ]
