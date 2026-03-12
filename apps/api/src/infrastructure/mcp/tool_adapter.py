"""
MCP Tool Adapter — Wraps MCP tools as LangChain BaseTool instances.

Converts dynamically-discovered MCP tools into LangChain BaseTool subclasses
that integrate seamlessly with the existing parallel_executor pipeline.

Why BaseTool (not @connector_tool):
    The @connector_tool decorator (and @rate_limit, @track_tool_metrics) only works
    on static functions decorated with @tool at import time. MCP tools are dynamic
    (discovered at runtime from external servers). BaseTool subclass enables
    programmatic creation via from_mcp_tool(). Metrics and error handling are
    implemented manually in _arun().

Phase: evolution F2 — MCP Support
Created: 2026-02-28
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, create_model

from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.mcp.utils import build_mcp_app_output
from src.infrastructure.observability.metrics_agents import (
    mcp_connection_errors_total,
    mcp_tool_duration_seconds,
    mcp_tool_invocations_total,
)

logger = structlog.get_logger(__name__)

# JSON Schema type → Python type mapping for create_model()
_JSON_SCHEMA_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def build_args_schema(
    input_schema: dict[str, Any],
) -> type[BaseModel] | None:
    """Build a Pydantic model from MCP tool JSON Schema.

    Converts JSON Schema properties to Pydantic fields for LangChain
    argument validation. Falls back to None for complex schemas ($ref,
    allOf, anyOf, const) where conversion is unreliable.

    Args:
        input_schema: JSON Schema dict from MCP list_tools()

    Returns:
        Pydantic model class or None if schema is too complex
    """
    properties = input_schema.get("properties", {})
    if not properties:
        return None

    required_fields = set(input_schema.get("required", []))
    field_definitions: dict[str, Any] = {}

    for field_name, field_spec in properties.items():
        # Skip complex schemas that can't be reliably converted
        if any(key in field_spec for key in ("$ref", "allOf", "anyOf", "oneOf", "const")):
            logger.debug(
                "mcp_schema_complex_field_skipped",
                field_name=field_name,
                complex_keys=[k for k in field_spec if k in ("$ref", "allOf", "anyOf", "oneOf")],
            )
            return None  # Fall back to no schema for entire tool

        field_type_str = field_spec.get("type", "string")
        python_type = _JSON_SCHEMA_TYPE_MAP.get(field_type_str, str)
        description = field_spec.get("description", "")

        if field_name in required_fields:
            field_definitions[field_name] = (
                python_type,
                Field(description=description),
            )
        else:
            default = field_spec.get("default")
            field_definitions[field_name] = (
                python_type | None,
                Field(default=default, description=description),
            )

    try:
        return create_model("MCPToolInput", **field_definitions)
    except Exception as e:
        logger.warning(
            "mcp_schema_conversion_failed",
            error=str(e),
            field_count=len(field_definitions),
        )
        return None


class MCPToolAdapter(BaseTool):
    """
    LangChain BaseTool adapter for MCP tools.

    Wraps an MCP tool discovered from an external server, making it
    invokable through the standard parallel_executor pipeline.

    Naming convention: "mcp_{server_name}_{tool_name}"
    """

    name: str = ""
    description: str = ""
    server_name: str = ""
    mcp_tool_name: str = ""
    args_schema: type[BaseModel] | None = None
    app_resource_uri: str | None = None

    @classmethod
    def from_mcp_tool(
        cls,
        server_name: str,
        tool_name: str,
        description: str,
        input_schema: dict[str, Any],
        app_resource_uri: str | None = None,
    ) -> MCPToolAdapter:
        """
        Create an MCPToolAdapter from MCP tool discovery data.

        Args:
            server_name: Name of the MCP server
            tool_name: Tool name as reported by the server
            description: Tool description for LLM context
            input_schema: JSON Schema for tool parameters
            app_resource_uri: MCP Apps UI resource URI (``ui://...``) if present

        Returns:
            Configured MCPToolAdapter instance
        """
        prefixed_name = f"mcp_{server_name}_{tool_name}"
        args_model = build_args_schema(input_schema)

        return cls(
            name=prefixed_name,
            description=description,
            server_name=server_name,
            mcp_tool_name=tool_name,
            args_schema=args_model,
            app_resource_uri=app_resource_uri,
        )

    @property
    def coroutine(self) -> Callable[..., Awaitable[Any]]:
        """Expose _arun for parallel_executor's direct call path.

        Without this, BaseTool subclasses fall to ainvoke() which stringifies
        the result via ToolMessage(content=str(result)), losing UnifiedToolOutput.
        """
        return self._arun

    async def _arun(self, **kwargs: Any) -> UnifiedToolOutput:
        """
        Execute the MCP tool via the client manager.

        When the tool has an associated MCP Apps UI (``app_resource_uri``),
        also fetches the HTML resource and returns a ``UnifiedToolOutput``
        with an ``MCP_APP`` RegistryItem. Falls back to raw string result
        if resource fetch fails (graceful degradation).

        Metrics are tracked manually (Prometheus Counter/Histogram) since
        @track_tool_metrics decorator is incompatible with BaseTool._arun().

        Error handling: exceptions are raised (not silently caught).
        parallel_executor._execute_tool() catches them and returns
        ToolExecutionResult(success=False, error=...).
        """
        # Lazy import to avoid circular dependencies
        from src.infrastructure.mcp.client_manager import get_mcp_client_manager

        start = time.perf_counter()
        try:
            manager = get_mcp_client_manager()
            if manager is None:
                raise RuntimeError("MCP client manager not initialized")

            # Excalidraw: iterative LLM-driven building or position correction
            kwargs = await self._prepare_excalidraw(kwargs)

            result = await manager.call_tool(
                self.server_name,
                self.mcp_tool_name,
                kwargs,
            )

            mcp_tool_invocations_total.labels(
                server_name=self.server_name,
                tool_name=self.mcp_tool_name,
                status="success",
            ).inc()

            # MCP Apps: fetch HTML resource if tool has an associated UI
            if self.app_resource_uri:
                html_content = await manager.read_resource(self.server_name, self.app_resource_uri)
                if html_content:
                    input_schema = (
                        self.args_schema.model_json_schema() if self.args_schema else None
                    )
                    return build_mcp_app_output(
                        raw_result=result,
                        html_content=html_content,
                        tool_name=self.mcp_tool_name,
                        adapter_name=self.name,
                        server_display_name=self.server_name,
                        server_id="",
                        server_key=self.server_name,
                        server_source="admin",
                        resource_uri=self.app_resource_uri,
                        source_label=self.server_name,
                        tool_arguments=kwargs,
                        tool_input_schema=input_schema,
                    )

            # Return UnifiedToolOutput with a short summary for the response
            # LLM and full data in structured_data for dependent steps.
            # Returning raw result would pollute agent_results_summary with
            # potentially large content (e.g., 27KB README from read_me).
            summary = f"[MCP] Tool '{self.mcp_tool_name}' on '{self.server_name}': result received"
            return UnifiedToolOutput.data_success(
                message=summary,
                structured_data={
                    "mcp_tool": self.mcp_tool_name,
                    "server_name": self.server_name,
                    "result": result,
                },
            )

        except Exception as exc:
            mcp_tool_invocations_total.labels(
                server_name=self.server_name,
                tool_name=self.mcp_tool_name,
                status="error",
            ).inc()
            mcp_connection_errors_total.labels(
                server_name=self.server_name,
                error_type=type(exc).__name__,
            ).inc()

            raise

        finally:
            elapsed = time.perf_counter() - start
            mcp_tool_duration_seconds.labels(
                server_name=self.server_name,
                tool_name=self.mcp_tool_name,
            ).observe(elapsed)

    async def _prepare_excalidraw(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Handle Excalidraw-specific element generation.

        Three modes:
        1. Intent mode (preferred): LLM generates a structured intent JSON
           (``{"intent": true, "components": [...], ...}``). The builder makes
           a single LLM call to produce all elements (shapes + arrows).
        2. Fallback: LLM generates raw Excalidraw elements (JSON array).
           The position corrector fixes overlaps and text centering.
        3. Passthrough: non-Excalidraw tools or non-string elements.
        """
        from src.infrastructure.mcp.excalidraw.overrides import (
            EXCALIDRAW_CREATE_VIEW_TOOL,
            EXCALIDRAW_SERVER_NAME,
        )

        if (
            self.server_name != EXCALIDRAW_SERVER_NAME
            or self.mcp_tool_name != EXCALIDRAW_CREATE_VIEW_TOOL
        ):
            return kwargs

        if "elements" not in kwargs:
            return kwargs

        elements_str = kwargs["elements"]
        if not isinstance(elements_str, str):
            return kwargs

        # ── Intent mode: single LLM call for complete diagram ────────────
        from src.infrastructure.mcp.excalidraw.iterative_builder import (
            build_from_intent,
            is_intent,
        )

        intent = is_intent(elements_str)
        if intent is not None:
            # Use cached read_me cheat sheet (auto-fetched at startup)
            cheat_sheet = self._fetch_excalidraw_cheat_sheet()

            built = await build_from_intent(intent, cheat_sheet)
            logger.info(
                "excalidraw_build_from_intent",
                input_length=len(elements_str),
                output_length=len(built),
                component_count=len(intent.get("components", [])),
            )
            return {**kwargs, "elements": built}

        # ── Fallback: raw elements — fix overlaps and text centering ────
        if elements_str.strip().startswith("["):
            from src.infrastructure.mcp.excalidraw.position_corrector import (
                correct_positions,
            )

            corrected = correct_positions(elements_str)
            logger.info(
                "excalidraw_positions_corrected_fallback",
                input_length=len(elements_str),
                output_length=len(corrected),
            )
            return {**kwargs, "elements": corrected}

        return kwargs

    def _fetch_excalidraw_cheat_sheet(self) -> str:
        """Get the read_me cheat sheet from the cached reference content.

        The cheat sheet is auto-fetched at startup by MCPClientManager and
        cached in ``reference_content``. No runtime call_tool needed.
        """
        from src.infrastructure.mcp.client_manager import get_mcp_client_manager
        from src.infrastructure.mcp.excalidraw.overrides import EXCALIDRAW_SERVER_NAME

        manager = get_mcp_client_manager()
        if manager is None:
            logger.warning("excalidraw_cheat_sheet_no_manager")
            return ""

        content = manager.reference_content.get(EXCALIDRAW_SERVER_NAME, "")
        if not content:
            logger.warning("excalidraw_cheat_sheet_not_cached")
        return content

    def _run(self, **kwargs: Any) -> str:
        """MCP tools are async only."""
        raise NotImplementedError(
            f"MCP tool '{self.name}' is async only. Use _arun() or ainvoke()."
        )
