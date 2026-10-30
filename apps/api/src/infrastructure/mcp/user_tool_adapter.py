"""
User MCP Tool Adapter — Wraps per-user MCP tools as LangChain BaseTool instances.

Similar to MCPToolAdapter but for user-declared MCP servers.
Uses the UserMCPClientPool instead of the admin MCPClientManager.

Naming convention: "mcp_user_{server_id_prefix}_{tool_name}"

Phase: evolution F2.1 — MCP Per-User
Created: 2026-02-28
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable, Collection, Mapping
from copy import deepcopy
from typing import Any
from uuid import UUID

import structlog
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from src.core.config import settings
from src.core.constants import MCP_USER_TOOL_NAME_PREFIX
from src.core.field_names import FIELD_REGISTRY_ID
from src.domains.agents.constants import CONTEXT_DOMAIN_MCP
from src.domains.agents.data_registry.mcp_metadata import (
    mcp_item_payload,
    mcp_server_origin,
    mcp_source_display,
)
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
    generate_registry_id,
)
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.mcp.gated_tool import EffectGatedMCPTool
from src.infrastructure.mcp.rate_limit import (
    MCPDeclarationChangedError,
    MCPRateLimitError,
    MCPToolExecutionError,
)
from src.infrastructure.mcp.semantic_observations import (
    observation_notice,
    semantic_observation_data,
)
from src.infrastructure.mcp.tool_adapter import build_args_schema, nullable_parameter_names
from src.infrastructure.mcp.tool_aliases import allocate_tool_aliases
from src.infrastructure.mcp.utils import (
    build_mcp_app_output,
    decode_mcp_result,
    drop_none_values,
    result_text_data,
)
from src.infrastructure.observability.metrics_mcp import (
    mcp_connection_errors_total,
    mcp_tool_duration_seconds,
    mcp_tool_invocations_total,
)

logger = structlog.get_logger(__name__)

# Verb prefixes stripped when deriving a collection key from MCP tool names
_VERB_PREFIXES = frozenset(
    {"search", "list", "get", "find", "fetch", "query", "create", "delete", "update"}
)


def _parse_mcp_structured_items(raw_result: str) -> tuple[list[dict], str | None] | None:
    """Parse MCP raw result into structured items if possible.

    Returns:
        ``(items_list, detected_key)`` when the result contains a JSON array of
        dicts. *detected_key* is the dict field name that held the array when
        the top-level value was an object, or ``None`` when the top-level value
        was itself the array.

        ``None`` when the result is not parseable as structured items (plain
        text, scalar JSON, array of scalars, etc.) — caller should fall back
        to the single-wrapper behaviour.
    """
    try:
        parsed = json.loads(raw_result)
    except json.JSONDecodeError, TypeError:
        return None

    # Top-level list of dicts → direct structured items
    if isinstance(parsed, list):
        if parsed and all(isinstance(item, dict) for item in parsed):
            return (parsed, None)
        # Empty list is valid (0 items)
        if not parsed:
            return ([], None)
        # Array of scalars → not structured
        return None

    # Top-level dict → look for the largest list-of-dicts value
    if isinstance(parsed, dict):
        best_key: str | None = None
        best_items: list[dict] = []
        for key, value in parsed.items():
            if (
                isinstance(value, list)
                and value
                and all(isinstance(item, dict) for item in value)
                and len(value) > len(best_items)
            ):
                best_key = key
                best_items = value
        if best_key is not None:
            return (best_items, best_key)

    return None


def _derive_collection_key(tool_name: str) -> str:
    """Derive a pluralised collection key from an MCP tool name.

    Examples::

        search_repositories → "repositories"
        list_commits        → "commits"
        get_user            → "users"
        ping                → "pings"
    """
    parts = tool_name.lower().split("_")
    # Strip leading verb prefix(es)
    while parts and parts[0] in _VERB_PREFIXES:
        parts.pop(0)
    key = "_".join(parts) if parts else "items"
    if not key.endswith("s"):
        key += "s"
    return key


class UserMCPToolAdapter(EffectGatedMCPTool, BaseTool):
    """
    LangChain BaseTool adapter for per-user MCP tools.

    Wraps an MCP tool discovered from a user's personal MCP server,
    making it invokable through the parallel_executor pipeline.

    Naming: "mcp_user_{server_id[:8]}_{tool_name}"
    """

    name: str = ""
    # ADR-263: memoises the gated call built by ``EffectGatedMCPTool``.
    _gated_call: Callable[..., Awaitable[Any]] | None = PrivateAttr(default=None)
    _nullable_arguments: frozenset[str] = PrivateAttr(default_factory=frozenset)
    _output_schema: dict[str, object] | None = PrivateAttr(default=None)
    # What the call is built from: the entry's catalogue and this tool's declaration.
    # The pool checks a call whose catalogue is no longer the entry's (fresh review I2).
    _built_from: str | None = PrivateAttr(default=None)
    _declaration: dict[str, Any] | None = PrivateAttr(default=None)
    description: str = ""
    server_id: UUID = Field(default=UUID(int=0))
    user_id: UUID = Field(default=UUID(int=0))
    mcp_tool_name: str = ""
    server_name_label: str = ""  # For Prometheus labels
    server_display_name: str = ""  # Human-readable server name for card display
    server_url: str = ""  # Public origin only; never carries endpoint credentials
    args_schema: type[BaseModel] | None = None
    timeout_seconds: int = 30
    app_resource_uri: str | None = None
    #: Server-declared behaviour hints. UNTRUSTED per the MCP spec: read only
    #: where they TIGHTEN a decision (see ``declares_destructive_tool``).
    annotations: dict[str, Any] | None = None

    @classmethod
    def from_discovered_tool(
        cls,
        server_id: UUID,
        user_id: UUID,
        server_name: str,
        tool_name: str,
        description: str,
        input_schema: dict[str, Any],
        timeout_seconds: int = 30,
        app_resource_uri: str | None = None,
        annotations: dict[str, Any] | None = None,
        server_url: str = "",
        output_schema: dict[str, object] | None = None,
        *,
        server_prefix: str | None = None,
        reserved_aliases: Collection[str] = (),
        tool_alias: str | None = None,
        built_from: str | None = None,
        declaration: Mapping[str, Any] | None = None,
    ) -> UserMCPToolAdapter:
        """
        Create a UserMCPToolAdapter from discovered tool data.

        Reuses build_args_schema() from the admin MCP tool_adapter. ``built_from``
        (the entry's catalogue fingerprint) and ``declaration`` (this tool's) travel
        with every call, so the pool can check a call against what it was built from.
        """
        # Prefix ensures uniqueness and identification as user MCP tool
        server_prefix = server_prefix or str(server_id)[:8]
        prefixed_name = (
            tool_alias
            or allocate_tool_aliases(
                {
                    (
                        str(server_id),
                        tool_name,
                    ): f"{MCP_USER_TOOL_NAME_PREFIX}_{server_prefix}_{tool_name}"
                },
                reserved=reserved_aliases,
            )[(str(server_id), tool_name)]
        )
        args_model = build_args_schema(input_schema)

        adapter = cls(
            name=prefixed_name,
            description=description,
            server_id=server_id,
            user_id=user_id,
            mcp_tool_name=tool_name,
            server_name_label=f"user_{server_prefix}",
            server_display_name=server_name,
            server_url=mcp_server_origin(server_url),
            args_schema=args_model,
            timeout_seconds=timeout_seconds,
            app_resource_uri=app_resource_uri,
            annotations=annotations,
        )
        adapter._nullable_arguments = nullable_parameter_names(input_schema)
        adapter._output_schema = deepcopy(output_schema)
        adapter._built_from = built_from
        adapter._declaration = deepcopy(dict(declaration)) if declaration is not None else None
        return adapter

    async def _call_server(self, **kwargs: Any) -> UnifiedToolOutput:
        """
        Execute the user MCP tool via the pool.

        Returns UnifiedToolOutput with RegistryItem for HTML card rendering.
        Metrics reuse the same Prometheus counters as admin MCP tools
        with a "user_" prefix on the server_name label.
        """
        from src.infrastructure.mcp.user_pool import get_user_mcp_pool

        # Omit unset optional params (materialised as None by the args schema) so
        # strictly-typed MCP servers don't reject them as null.
        arguments = drop_none_values(kwargs, keep_nullable=self._nullable_arguments)

        start = time.perf_counter()
        try:
            pool = get_user_mcp_pool()
            if pool is None:
                raise RuntimeError("User MCP pool not initialized")

            raw_result = await pool.call_tool(
                user_id=self.user_id,
                server_id=self.server_id,
                tool_name=self.mcp_tool_name,
                arguments=arguments,
                timeout_seconds=self.timeout_seconds,
                built_from=self._built_from,
                declaration=self._declaration,
            )
            observations = semantic_observation_data(
                decode_mcp_result(raw_result), self._output_schema
            )

            mcp_tool_invocations_total.labels(
                server_name=self.server_name_label,
                tool_name=self.mcp_tool_name,
                status="success",
            ).inc()

            # ---------------------------------------------------------------
            # MCP Apps: fetch HTML resource if tool has an associated UI
            # ---------------------------------------------------------------
            if self.app_resource_uri:
                html_content = await pool.read_resource(
                    self.user_id,
                    self.server_id,
                    self.app_resource_uri,
                    self.timeout_seconds,
                )
                if html_content:
                    input_schema = (
                        self.args_schema.model_json_schema() if self.args_schema else None
                    )
                    return build_mcp_app_output(
                        raw_result=raw_result,
                        html_content=html_content,
                        tool_name=self.mcp_tool_name,
                        adapter_name=self.name,
                        server_display_name=self.server_display_name,
                        server_id=str(self.server_id),
                        server_key="",
                        server_source="user",
                        resource_uri=self.app_resource_uri,
                        source_label=self.server_name_label,
                        tool_arguments=arguments,
                        tool_input_schema=input_schema,
                        semantic_observations=observations,
                    )

            # ---------------------------------------------------------------
            # Parse structured items from JSON results (evolution F2.4)
            # ---------------------------------------------------------------
            # MCP tools return raw strings.  When the result is a JSON array
            # of dicts (or a dict wrapping such an array), we create one
            # RegistryItem *per item* so that:
            #   1. for_each expansion can iterate → $item.name works
            #   2. McpResultCard renders structured cards (not raw JSON blobs)
            # For non-JSON / scalar results we fall back to the single wrapper.
            # ---------------------------------------------------------------
            parsed = _parse_mcp_structured_items(raw_result)

            if parsed is not None:
                items_list, detected_key = parsed
                collection_key = detected_key or _derive_collection_key(self.mcp_tool_name)
                # ``result`` is the canonical schema path, so a server's own
                # collection named "result" keeps that name INSIDE the root.
                if collection_key == "result":
                    collection_key = _derive_collection_key(self.mcp_tool_name)

                # Cap items to prevent registry explosion (e.g., list_commits
                # returning 100+ items per page × N repos in a for_each).
                max_items = settings.mcp_max_structured_items_per_call
                if len(items_list) > max_items:
                    items_list = items_list[:max_items]

                registry_updates: dict[str, RegistryItem] = {}
                structured_items: list[dict[str, Any]] = []

                for idx, item_data in enumerate(items_list):
                    unique_key = f"{self.server_id}_{self.mcp_tool_name}_{idx}_{time.time_ns()}"
                    rid = generate_registry_id(RegistryItemType.MCP_RESULT, unique_key)
                    registry_updates[rid] = RegistryItem(
                        id=rid,
                        type=RegistryItemType.MCP_RESULT,
                        payload=mcp_item_payload(
                            item_data,
                            self.server_display_name,
                            self.mcp_tool_name,
                            self.server_url,
                        ),
                        meta=RegistryItemMeta(
                            source=f"mcp_{self.server_name_label}",
                            domain=CONTEXT_DOMAIN_MCP,
                            tool_name=self.name,
                        ),
                    )
                    structured_items.append({**item_data, FIELD_REGISTRY_ID: rid})

                # Short summary for LLM context — the actual data is in the
                # registry (rendered via McpResultCard HTML cards).  Passing
                # the raw result here would pollute the response LLM prompt
                # with large JSON/text and cause it to reproduce it verbatim.
                summary = (
                    f"[MCP] Tool '{self.mcp_tool_name}' on "
                    f"'{self.server_display_name}': "
                    f"{len(items_list)} item(s) returned"
                )
                return UnifiedToolOutput.data_success(
                    message=summary + observation_notice(observations),
                    registry_updates=registry_updates,
                    structured_data={
                        "result": decode_mcp_result(raw_result),
                        **result_text_data(raw_result),
                        **observations,
                        collection_key: structured_items,
                    },
                    metadata={
                        "mcp_result_projection": True,
                        "mcp_display_collection_key": collection_key,
                        "mcp_result_collection_path": (
                            f"result.{detected_key}" if detected_key is not None else "result"
                        ),
                    },
                )

            # Fallback: single wrapper (non-JSON or non-iterable result)
            unique_key = f"{self.server_id}_{self.mcp_tool_name}_{time.time_ns()}"
            item_id = generate_registry_id(RegistryItemType.MCP_RESULT, unique_key)
            registry_item = RegistryItem(
                id=item_id,
                type=RegistryItemType.MCP_RESULT,
                payload={
                    "tool_name": self.mcp_tool_name,
                    "server_name": self.server_display_name,
                    "result": raw_result,
                },
                meta=RegistryItemMeta(
                    source=f"mcp_{self.server_name_label}",
                    domain=CONTEXT_DOMAIN_MCP,
                    tool_name=self.name,
                    display=mcp_source_display(
                        self.server_display_name, self.mcp_tool_name, self.server_url
                    ),
                ),
            )

            # Short summary — full result is stored in registry payload
            # ("result" key) and rendered via McpResultCard.
            summary = (
                f"[MCP] Tool '{self.mcp_tool_name}' on "
                f"'{self.server_display_name}': result received"
            )
            return UnifiedToolOutput.data_success(
                message=summary + observation_notice(observations),
                registry_updates={item_id: registry_item},
                structured_data={
                    "result": decode_mcp_result(raw_result),
                    **result_text_data(raw_result),
                    **observations,
                    CONTEXT_DOMAIN_MCP: [
                        {
                            "tool_name": self.mcp_tool_name,
                            "server_name": self.server_display_name,
                            "result": raw_result,
                        }
                    ],
                },
                metadata={
                    "mcp_result_projection": True,
                    "mcp_display_collection_key": CONTEXT_DOMAIN_MCP,
                },
            )

        except (MCPDeclarationChangedError, MCPRateLimitError) as exc:
            return self._refusal(exc)

        except Exception as exc:
            mcp_tool_invocations_total.labels(
                server_name=self.server_name_label,
                tool_name=self.mcp_tool_name,
                status="error",
            ).inc()
            if not isinstance(exc, MCPToolExecutionError):
                mcp_connection_errors_total.labels(
                    server_name=self.server_name_label,
                    error_type=type(exc).__name__,
                ).inc()

            logger.warning(
                "user_mcp_tool_error",
                user_id=str(self.user_id),
                server_id=str(self.server_id),
                tool_name=self.mcp_tool_name,
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=not isinstance(exc, MCPToolExecutionError),
            )

            raise

        finally:
            elapsed = time.perf_counter() - start
            mcp_tool_duration_seconds.labels(
                server_name=self.server_name_label,
                tool_name=self.mcp_tool_name,
            ).observe(elapsed)

    def _refusal(self, exc: MCPDeclarationChangedError | MCPRateLimitError) -> UnifiedToolOutput:
        """A typed refusal the server answered with — never a connection failure."""
        mcp_tool_invocations_total.labels(
            server_name=self.server_name_label,
            tool_name=self.mcp_tool_name,
            status="error",
        ).inc()
        if isinstance(exc, MCPRateLimitError):
            logger.info(
                "user_mcp_tool_rate_limited",
                server_id=str(self.server_id),
                tool_name=self.mcp_tool_name,
                retry_after=exc.retry_after,
            )
            return UnifiedToolOutput.failure(
                message=str(exc),
                error_code="RATE_LIMIT_EXCEEDED",
                metadata={"retry_after": exc.retry_after},
            )
        # The server answered with a new declaration (spec 2026-10-21 §5.5).
        logger.info(
            "user_mcp_tool_declaration_changed",
            server_id=str(self.server_id),
            tool_name=self.mcp_tool_name,
            reason=exc.reason,
        )
        return UnifiedToolOutput.failure(
            message=str(exc), error_code="CONFLICT", metadata={"reason": exc.reason}
        )

    def _run(self, **kwargs: Any) -> str:
        """User MCP tools are async only."""
        raise NotImplementedError(
            f"User MCP tool '{self.name}' is async only. Use _arun() or ainvoke()."
        )
