"""
OpenTelemetry tracing configuration.
Integrates with Tempo for distributed tracing.
"""

from collections.abc import Mapping
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
from src.core.run_config import run_id_of

logger = structlog.get_logger(__name__)


def _redacted_request_attributes(attributes: Mapping[str, Any]) -> dict[str, str]:
    """The request's target attributes rewritten to the route template.

    ``unmatched`` and the bare origin when no route matched, the query string
    dropped, whichever semantic convention emitted them — and only the
    attributes the span carries. Lookups alone: nothing here can raise.

    Args:
        attributes: The server span's attributes as the instrumentation set them.

    Returns:
        The rewritten value of every target attribute present.
    """
    template = attributes.get("http.route")
    target = template if isinstance(template, str) and template else "unmatched"
    scheme = attributes.get("http.scheme") or attributes.get("url.scheme")
    host = attributes.get("http.host") or attributes.get("server.address")
    origin = f"{scheme}://{host}" if scheme and host else ""
    url = origin + target if target.startswith("/") else origin
    rewritten = {
        "http.target": target,
        "url.path": target,
        "http.url": url,
        "url.full": url,
        "url.query": "",
    }
    return {key: value for key, value in rewritten.items() if key in attributes}


def _redact_request_target(span: trace.Span, scope: dict[str, Any]) -> None:
    """Keep the words a person typed out of exported traces (ADR-317).

    The instrumentation names the span after the route template, but records
    the CONCRETE target: measured on 0.65b0, ``http.target`` carried
    ``/api/v1/relations/favorites/Jane Doe`` and ``http.url`` the query string
    too. A hook that raised would fail the request, so it only looks up.

    Args:
        span: The server span, just started.
        scope: The request's ASGI scope (unused: the span already holds what
            the instrumentation read from it).
    """
    if not span.is_recording():
        return
    attributes: Mapping[str, Any] = getattr(span, "attributes", None) or {}
    for key, value in _redacted_request_attributes(attributes).items():
        span.set_attribute(key, value)


def instrument_fastapi(app: FastAPI, tracer_provider: TracerProvider | None = None) -> None:
    """Instrument the application the one way LIA does — main.py and its tests.

    Args:
        app: FastAPI application instance.
        tracer_provider: The provider spans go to; the global one when omitted.
    """
    excluded = "|".join(f"{p.rstrip('/')}/?" for p in settings.http_log_exclude_paths)
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls=excluded,
        server_request_hook=_redact_request_target,
        tracer_provider=tracer_provider,
    )


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
                "service.version": settings.app_version,
                "service.instance.commit_sha": settings.git_commit_sha,
                "service.build_date": settings.build_date,
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

        instrument_fastapi(app)

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
                run_id = run_id_of(config)
                if run_id:
                    span.set_attribute("langgraph.run_id", run_id)

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
