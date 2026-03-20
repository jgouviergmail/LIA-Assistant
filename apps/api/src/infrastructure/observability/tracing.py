"""
OpenTelemetry tracing configuration.
Integrates with Tempo for distributed tracing.
"""

from typing import Any

import structlog
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from src.core.config import settings
from src.core.field_names import FIELD_METADATA, FIELD_RUN_ID

logger = structlog.get_logger(__name__)


def configure_tracing(app: FastAPI) -> None:
    """
    Configure OpenTelemetry tracing for FastAPI application.

    Args:
        app: FastAPI application instance
    """
    try:
        # Create resource with service information
        resource = Resource.create(
            {
                "service.name": settings.otel_service_name,
                "service.version": "0.1.0",
                "deployment.environment": settings.environment,
            }
        )

        # Create tracer provider
        tracer_provider = TracerProvider(resource=resource)

        # Create OTLP exporter
        # Always insecure for Docker-internal communication (tempo:4317 has no TLS).
        # For external OTLP endpoints with TLS, set OTEL_EXPORTER_OTLP_ENDPOINT to https://...
        otlp_exporter = OTLPSpanExporter(
            endpoint=settings.otel_exporter_otlp_endpoint,
            insecure=True,
        )

        # Add span processor
        tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

        # Set global tracer provider
        trace.set_tracer_provider(tracer_provider)

        # Instrument FastAPI
        excluded = "|".join(f"{p.rstrip('/')}/?" for p in settings.http_log_exclude_paths)
        FastAPIInstrumentor.instrument_app(app, excluded_urls=excluded)

        logger.info(
            "tracing_configured",
            service_name=settings.otel_service_name,
            otlp_endpoint=settings.otel_exporter_otlp_endpoint,
        )

    except Exception as exc:
        logger.error(
            "tracing_configuration_failed",
            error=str(exc),
            exc_info=True,
        )


def get_tracer(name: str) -> trace.Tracer:
    """
    Get a tracer instance.

    Args:
        name: Tracer name (typically __name__)

    Returns:
        OpenTelemetry tracer
    """
    return trace.get_tracer(name)


def trace_node(node_name: str, llm_model: str | None = None) -> Any:
    """
    Decorator for tracing LangGraph nodes with OpenTelemetry.
    Automatically adds standard span attributes for LangGraph operations.

    Args:
        node_name: Name of the LangGraph node (e.g., "router", "response").
        llm_model: Optional LLM model name to add to span attributes.

    Returns:
        Decorator function.

    Example:
        >>> @trace_node("router", llm_model="gpt-4.1-mini")
        >>> async def router_node(state: MessagesState, config: RunnableConfig):
        >>>     ...
    """
    from collections.abc import Callable
    from functools import wraps
    from typing import Any

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = trace.get_tracer(__name__)

            # Extract config from args/kwargs
            config = kwargs.get("config") or (args[1] if len(args) > 1 else None)

            with tracer.start_as_current_span(f"langgraph.node.{node_name}") as span:
                # Add standard LangGraph attributes
                span.set_attribute("langgraph.node.name", node_name)

                # Add run_id from config if available
                if config and isinstance(config, dict):
                    run_id = config.get(FIELD_METADATA, {}).get(FIELD_RUN_ID)
                    if run_id:
                        span.set_attribute("langgraph.run_id", str(run_id))

                # Add LLM model if specified
                if llm_model:
                    span.set_attribute("langgraph.llm.model", llm_model)

                # Execute node function
                try:
                    result = await func(*args, **kwargs)

                    # Add result metadata if available
                    if hasattr(result, "get"):
                        # If result is dict-like, check for routing info
                        routing_history = result.get("routing_history", [])
                        if routing_history:
                            last_routing = routing_history[-1]
                            if hasattr(last_routing, "intention"):
                                span.set_attribute(
                                    "langgraph.router.intention", last_routing.intention
                                )
                            if hasattr(last_routing, "confidence"):
                                span.set_attribute(
                                    "langgraph.router.confidence", last_routing.confidence
                                )
                            if hasattr(last_routing, "next_node"):
                                span.set_attribute(
                                    "langgraph.router.next_node", last_routing.next_node
                                )

                    return result

                except Exception as e:
                    # Add exception info to span
                    span.set_attribute("error", True)
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e))
                    raise

        return wrapper

    return decorator
