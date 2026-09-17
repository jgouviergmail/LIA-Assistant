"""Replay real ReAct turns against the tool-selection policy (ADR-293).

A MEASUREMENT, never a gate: it needs the registry, the semantic selector's
embedding cache and one small embedding call per turn. It answers, for a
deployment's own turns, what the relevance selection binds and whether every
tool the loop actually called would still have been offered — the evidence
the cap alone could never give.

Input: a JSON list of turns, each ``{"query": str, "domains": [str], "tools":
[str]}`` — the router's detected domains and the tools the loop called, as the
``react_setup_complete``, ``router_v3_complete`` and ``tool_execution_started``
log events carry them. The file is the operator's own extraction; nothing in
the repository holds anyone's turns. The replay covers the NATIVE catalogue:
user MCP servers live in a per-request context the harness does not build.
The binding is the selector's own ``select`` — the loop's public seam — under
the same per-request manifests, so the harness cannot drift from the loop.

Usage (inside the API container or with the API environment loaded)::

    python scripts/react/measure_tool_selection.py --turns turns.json [--top-k 40]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

from src.infrastructure.database.registry import import_all_models

import_all_models()

from src.core.config import settings  # noqa: E402
from src.core.constants import EXECUTION_MODE_REACT  # noqa: E402
from src.core.context import request_tool_manifests_ctx  # noqa: E402
from src.domains.agents.registry.agent_registry import get_global_registry  # noqa: E402
from src.domains.agents.registry.catalogue import manifests_for_mode  # noqa: E402
from src.domains.agents.registry.catalogue_loader import initialize_catalogue  # noqa: E402
from src.domains.agents.services.react_tool_selector import (  # noqa: E402
    ReactToolSelector,
    bound_tool_tokens,
)
from src.domains.agents.services.tool_selector import initialize_tool_selector  # noqa: E402
from src.domains.agents.tools.tool_registry import ensure_tools_loaded  # noqa: E402


@dataclass(frozen=True)
class _Turn:
    """The one thing the selector reads of a turn's intelligence."""

    domains: list[str]


def _norm(name: str) -> str:
    return name[:-5] if name.endswith("_tool") else name


async def main(turns_path: Path, top_k: int) -> int:
    ensure_tools_loaded()
    registry = get_global_registry()
    initialize_catalogue(registry)
    manifests = manifests_for_mode(registry.list_tool_manifests(), EXECUTION_MODE_REACT)
    order = [m.name for m in manifests]
    agent_of = {m.name: str(getattr(m, "agent", "") or "") for m in manifests}
    selector = await initialize_tool_selector(registry.list_tool_manifests())
    settings.react_tool_semantic_top_k = top_k
    react_selector = ReactToolSelector()

    turns = [t for t in json.loads(turns_path.read_text(encoding="utf-8")) if t.get("query")]
    bound_counts: list[int] = []
    bound_tokens: list[int] = []
    misses: list[tuple[str, list[str]]] = []
    unreachable_families = 0
    token = request_tool_manifests_ctx.set(list(manifests))
    try:
        every_tool, _ = react_selector.select(_Turn(domains=[]), ranking=None)
        full_tokens = bound_tool_tokens(every_tool)
        for turn in turns:
            domains = turn.get("domains") or []
            embedding = await selector.embed_query(turn["query"])
            ranking = selector.rank_tools(embedding, manifests)
            wrapped, _hitl = react_selector.select(_Turn(domains=domains), ranking=ranking)
            bound = [tool.name for tool in wrapped]
            bound_counts.append(len(bound))
            bound_tokens.append(bound_tool_tokens(wrapped))
            by_norm = {_norm(n): n for n in order}
            used = {_norm(t) for t in turn.get("tools", [])}
            bound_norm = {_norm(n) for n in bound}
            missing = sorted(u for u in used if u in by_norm and u not in bound_norm)
            if missing:
                misses.append((turn["query"][:60], missing))
                bound_families = {agent_of.get(n, "") for n in bound}
                if any(agent_of[by_norm[u]] not in bound_families for u in missing):
                    unreachable_families += 1
    finally:
        request_tool_manifests_ctx.reset(token)
    cap = settings.react_agent_max_tools
    print(f"turns: {len(turns)}; react-available manifests: {len(order)}; top_k={top_k}; cap={cap}")
    print(
        f"bound per turn: median {statistics.median(bound_counts):.0f}, "
        f"max {max(bound_counts)} — schema tokens median {statistics.median(bound_tokens):.0f} "
        f"(every available tool: {full_tokens})"
    )
    print(
        f"turns where a tool the loop called would not have been bound: {len(misses)}; "
        f"of which its FAMILY was unreachable: {unreachable_families}"
    )
    for query, missing in misses:
        print(f"  {missing} | {query!r}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--turns", required=True, type=Path, help="JSON list of turns")
    parser.add_argument(
        "--top-k",
        type=int,
        default=settings.react_tool_semantic_top_k,
        help="Semantic slice (default: the configured REACT_TOOL_SEMANTIC_TOP_K)",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.turns, args.top_k)))
