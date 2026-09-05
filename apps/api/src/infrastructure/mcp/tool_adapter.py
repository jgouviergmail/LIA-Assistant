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
from pydantic import BaseModel, Field, PrivateAttr, create_model

from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.mcp.gated_tool import EffectGatedMCPTool
from src.infrastructure.mcp.json_schema import (
    annotation_for,
    as_property_spec,
    description_of,
    properties_of,
    required_of,
    resolve_property,
)
from src.infrastructure.mcp.utils import build_mcp_app_output, drop_none_values
from src.infrastructure.observability.metrics_mcp import (
    mcp_connection_errors_total,
    mcp_tool_duration_seconds,
    mcp_tool_invocations_total,
)

logger = structlog.get_logger(__name__)


def build_args_schema(
    input_schema: dict[str, Any],
) -> type[BaseModel] | None:
    """Build a Pydantic model from MCP tool JSON Schema.

    Converts JSON Schema properties to Pydantic fields for LangChain argument
    validation. Every declaration a server can send is interpreted through
    :mod:`src.infrastructure.mcp.json_schema`, so this never raises on a
    hostile payload — a tool lost to a ``TypeError`` is a capability the user
    silently no longer has.

    Composition keywords are read, not refused: the MCP spec admits every JSON
    Schema 2020-12 keyword here, and answering one ``$ref`` with no schema at
    all published the tool to the model as a single opaque ``kwargs`` object —
    no field names, no descriptions, no required list, hence uncallable. A
    property whose type stays undecidable keeps its name and description and is
    validated permissively; the MCP server remains the authority on its own
    contract.

    Args:
        input_schema: JSON Schema dict from MCP list_tools()

    Returns:
        Pydantic model class, or None when the schema declares no usable
        property at all.
    """
    properties = properties_of(input_schema)
    if not properties:
        return None

    required_fields = required_of(input_schema)
    field_definitions: dict[str, Any] = {}

    for field_name, raw_spec in properties.items():
        if field_name.startswith("_"):
            # Pydantic refuses a leading-underscore field name. Skipping the
            # parameter costs one argument; letting create_model raise costs
            # the whole tool.
            logger.debug("mcp_schema_underscore_field_skipped", field_name=field_name)
            continue

        field_spec = as_property_spec(raw_spec)
        resolved = resolve_property(field_spec, input_schema)
        if resolved.name is None:
            python_type: Any = Any
        else:
            python_type = annotation_for(resolved.name, resolved.spec)

        # A $ref'd property carries its description at the reference site; the
        # target carries it when the reference site does not.
        description = description_of(field_spec) or description_of(resolved.spec)

        if field_name in required_fields:
            # A required parameter the server declared nullable stays nullable:
            # rejecting a value the server accepts would make us stricter than
            # the contract we implement.
            annotation = python_type | None if resolved.nullable else python_type
            field_definitions[field_name] = (
                annotation,
                Field(description=description),
            )
        else:
            default = field_spec.get("default", resolved.spec.get("default"))
            field_definitions[field_name] = (
                python_type | None,
                Field(default=default, description=description),
            )

    if not field_definitions:
        return None

    try:
        return create_model("MCPToolInput", **field_definitions)
    except Exception as e:
        logger.warning(
            "mcp_schema_conversion_failed",
            error=str(e),
            field_count=len(field_definitions),
        )
        return None


class MCPToolAdapter(EffectGatedMCPTool, BaseTool):
    """
    LangChain BaseTool adapter for MCP tools.

    Wraps an MCP tool discovered from an external server, making it
    invokable through the standard parallel_executor pipeline.

    Naming convention: "mcp_{server_name}_{tool_name}"
    """

    name: str = ""
    # ADR-263: memoises the gated call built by ``EffectGatedMCPTool``.
    _gated_call: Callable[..., Awaitable[Any]] | None = PrivateAttr(default=None)
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

    async def _call_server(self, **kwargs: Any) -> UnifiedToolOutput:
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

        # Omit unset optional params (materialised as None by the args schema) so
        # strictly-typed MCP servers don't reject them as null.
        arguments = drop_none_values(kwargs)

        start = time.perf_counter()
        try:
            manager = get_mcp_client_manager()
            if manager is None:
                raise RuntimeError("MCP client manager not initialized")

            result = await manager.call_tool(
                self.server_name,
                self.mcp_tool_name,
                arguments,
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
                        tool_arguments=arguments,
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

    def _run(self, **kwargs: Any) -> str:
        """MCP tools are async only."""
        raise NotImplementedError(
            f"MCP tool '{self.name}' is async only. Use _arun() or ainvoke()."
        )
