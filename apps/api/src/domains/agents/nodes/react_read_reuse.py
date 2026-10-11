"""Exact, fresh reuse of explicitly eligible reads inside a single turn."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import asdict

from langchain_core.messages import ToolMessage
from langchain_core.messages.tool import ToolCall
from langchain_core.utils.function_calling import convert_to_openai_tool

from src.core.config import get_settings
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.registry.catalogue import is_read_only_tool
from src.domains.agents.semantic.manifest_semantics import available_manifest
from src.domains.agents.semantic.param_guard import strip_placeholder_arguments
from src.domains.agents.tools.tool_resolution import resolve_tool_instance
from src.domains.agents.utils.loop_guard import compute_call_digest
from src.domains.agents.utils.react_execution_contracts import CachedRead, ReadEvidence

MAX_CACHED_READS = 32
MAX_CACHED_BYTES = 512_000


def normalized_call(call: ToolCall) -> ToolCall:
    """Use exactly the placeholder normalization applied by the native executor."""
    return {**call, "args": strip_placeholder_arguments(call["name"], call.get("args", {}))}


def read_signature(call: ToolCall) -> str:
    """Opaque signature of the current arguments, public schema and account/turn."""
    context = runtime_context_if_running()
    tool = resolve_tool_instance(call["name"])
    scope = (
        (
            str(context.user_id),
            context.thread_id,
            context.timezone,
            context.language,
            context.browser_context,
        )
        if context is not None
        else (None, None)
    )
    manifest = available_manifest(call["name"])
    schema: object = {
        "public": convert_to_openai_tool(tool) if tool is not None else None,
        "parameters": (
            [asdict(parameter) for parameter in manifest.parameters] if manifest is not None else []
        ),
        "outputs": [asdict(output) for output in manifest.outputs] if manifest is not None else [],
        "delegates_execution": manifest.delegates_execution if manifest is not None else None,
        "mcp_origin": manifest.mcp_origin if manifest is not None else None,
        "mcp_server_key": manifest.mcp_server_key if manifest is not None else None,
    }
    return compute_call_digest(
        call["name"],
        {"args": call["args"], "schema": schema, "scope": scope},
        get_settings().secret_key,
    )


def eligible_read(call: ToolCall) -> bool:
    """Conservative opt-in; refresh requests and mutations never use a result cache."""
    manifest = available_manifest(call["name"])
    args = call["args"]
    return bool(
        manifest is not None
        and not manifest.delegates_execution
        and is_read_only_tool(manifest)
        and manifest.result_reuse_ttl_seconds
        and manifest.result_reuse_ttl_seconds > 0
        and not args.get("force_refresh")
        and args.get("use_cache") is not False
        and runtime_context_if_running() is not None
    )


def cached_answer(
    call: ToolCall, cache: Mapping[str, CachedRead]
) -> tuple[ToolMessage, dict[str, RegistryItem]] | None:
    """Return a new call's answer, preserving the old observation's provenance."""
    if not eligible_read(call):
        return None
    entry = cache.get(read_signature(call))
    if entry is None or entry["expires_at"] <= time.time():
        return None
    registry = {key: RegistryItem.model_validate(value) for key, value in entry["registry"].items()}
    return (
        ToolMessage(content=entry["content"], tool_call_id=call["id"], name=call["name"]),
        registry,
    )


def cache_entry(
    call: ToolCall, message: ToolMessage, registry: Mapping[str, object], evidence: ReadEvidence
) -> CachedRead | None:
    """Cache obtained reads only; failures, partial/empty results are not negative caches."""
    if not eligible_read(call) or evidence["outcome"] != "obtained":
        return None
    manifest = available_manifest(call["name"])
    assert manifest is not None and manifest.result_reuse_ttl_seconds is not None
    if not isinstance(message.content, str):
        return None
    serialized: dict[str, object] = {}
    for key, value in registry.items():
        if isinstance(value, RegistryItem):
            serialized[key] = value.model_dump(mode="json")
        elif isinstance(value, dict):
            serialized[key] = RegistryItem.model_validate(value).model_dump(mode="json")
    return CachedRead(
        content=message.content,
        registry=serialized,
        expires_at=time.time() + manifest.result_reuse_ttl_seconds,
    )


def _incomplete(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    return (
        any(value.get(key) is True for key in ("partial", "truncated", "has_more"))
        or any(value.get(key) is False for key in ("retrieval_complete", "complete"))
        or any(value.get(key) for key in ("next_page_token", "nextPageToken", "next_cursor"))
    )


def read_evidence(raw_result: object) -> ReadEvidence:
    """Read explicit machine outcome markers rather than the model's final wording."""
    if isinstance(raw_result, Mapping):
        success = raw_result.get("success")
        data = raw_result.get("structured_data", raw_result.get("data"))
        metadata = raw_result.get("metadata", raw_result.get("tool_metadata"))
    else:
        success = getattr(raw_result, "success", None)
        data = getattr(raw_result, "structured_data", None)
        metadata = getattr(raw_result, "metadata", None)
    if success is False:
        return {"outcome": "failed"}
    if _incomplete(data) or _incomplete(metadata):
        return {"outcome": "partial"}
    if data is not None and not data:
        return {"outcome": "empty"}
    if isinstance(data, Mapping) and data.get("count") == 0:
        return {"outcome": "empty"}
    return {"outcome": "obtained" if success is True and bool(data) else "empty"}


def bound_read_cache(cache: Mapping[str, CachedRead]) -> dict[str, CachedRead]:
    """Never duplicate an unbounded registry in the checkpoint to save a read."""
    retained: dict[str, CachedRead] = {}
    size = 0
    for signature, entry in reversed(tuple(cache.items())):
        if entry["expires_at"] <= time.time() or len(retained) >= MAX_CACHED_READS:
            continue
        entry_size = len(json.dumps(entry, ensure_ascii=False).encode("utf-8"))
        if size + entry_size > MAX_CACHED_BYTES:
            continue
        retained[signature] = entry
        size += entry_size
    return dict(reversed(tuple(retained.items())))
