"""Deterministic callable aliases without changing an MCP server's identity or RPC."""

import hashlib
import json
import re
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from uuid import UUID

from src.core.constants import MCP_MODEL_TOOL_NAME_MAX_LENGTH

_VALID_NAME = re.compile(rf"[A-Za-z0-9_-]{{1,{MCP_MODEL_TOOL_NAME_MAX_LENGTH}}}\Z")


def _collision_alias(name: str, identity: tuple[str, str], suffix: str = "") -> str:
    digest = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:12]
    ending = f"_{digest}{suffix}"
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", name)
    if len(stem) > MCP_MODEL_TOOL_NAME_MAX_LENGTH - len(ending) and name.startswith("mcp_"):
        # Keep the real RPC's verb when a long server label would otherwise erase it.
        stem = f"mcp_rpc_{re.sub(r'[^A-Za-z0-9_-]', '_', identity[1])}"
    return f"{stem[: MCP_MODEL_TOOL_NAME_MAX_LENGTH - len(ending)]}{ending}"


def allocate_tool_aliases(
    preferred: Mapping[tuple[str, str], str], *, reserved: Collection[str] = ()
) -> dict[tuple[str, str], str]:
    """Keep ordinary names; distinguish only aliases with multiple possible owners."""
    counts = Counter(preferred.values())
    unavailable = set(reserved) | set(preferred.values())
    result: dict[tuple[str, str], str] = {}
    for identity, name in sorted(preferred.items()):
        if counts[name] == 1 and name not in reserved and _VALID_NAME.fullmatch(name):
            result[identity] = name
            continue
        candidate = _collision_alias(name, identity)
        suffix = 2
        while candidate in unavailable:
            candidate = _collision_alias(name, identity, f"_{suffix}")
            suffix += 1
        unavailable.add(candidate)
        result[identity] = candidate
    return result


def _prefix_taken(
    prefix: str, server_id: UUID, ids: Sequence[UUID], reserved: Collection[str]
) -> bool:
    return any(other != server_id and other.hex.startswith(prefix) for other in ids) or any(
        name.startswith(f"mcp_user_{prefix}_") for name in reserved
    )


def _unique_user_prefix(server_id: UUID, ids: Sequence[UUID], reserved: Collection[str]) -> str:
    for width in range(8, 33):
        prefix = server_id.hex[:width]
        if not _prefix_taken(prefix, server_id, ids, reserved):
            return prefix
    suffix = 2
    prefix = f"{server_id.hex}_{suffix}"
    while _prefix_taken(prefix, server_id, ids, reserved):
        suffix += 1
        prefix = f"{server_id.hex}_{suffix}"
    return prefix


def allocate_user_prefixes(
    server_ids: Sequence[UUID], *, reserved: Collection[str] = ()
) -> dict[UUID, str]:
    """Extend a UUID prefix only when another server or global alias already occupies it."""
    return {
        server_id: _unique_user_prefix(server_id, server_ids, reserved) for server_id in server_ids
    }


def user_tool_aliases(
    server_id: UUID,
    rpc_names: Collection[str],
    *,
    server_prefix: str | None = None,
    reserved: Collection[str] = (),
) -> dict[str, str]:
    prefix = server_prefix or str(server_id)[:8]
    allocated = allocate_tool_aliases(
        {(str(server_id), rpc): f"mcp_user_{prefix}_{rpc}" for rpc in rpc_names}, reserved=reserved
    )
    return {rpc: allocated[(str(server_id), rpc)] for rpc in rpc_names}
