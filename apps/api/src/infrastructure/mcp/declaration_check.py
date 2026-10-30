"""A tool's CURRENT declaration, read before a call served from an unverified catalogue.

Spec 2026-10-21 §5.5 (M3). A turn may build a call from a catalogue past the
server's own ``ttlMs`` (it is served while revalidated, Q1). Before that call
the SAME ephemeral session lists the tools and compares the called tool:

- **missing** — the server no longer offers it;
- **incompatible** — the call's arguments do not validate against the current
  input schema (the argument model the adapter itself uses), or carry a
  parameter the server removed;
- **tightened** — the current annotations make it a stronger mutation than
  the frozen ones (newly destructive): the confirmation the person was asked
  for, or not asked for, was decided on a weaker declaration.

Any of the three refuses the call: it is never sent, nothing retries it, and
the model reads a structured failure (ADR-303). A looser declaration is only a
difference — a server's word that a tool became read-only is not believed
(``declared_tool_category`` tightens only).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from pydantic import ValidationError

from src.infrastructure.mcp.catalogue_fingerprint import canonical_fingerprint
from src.infrastructure.mcp.catalogue_snapshot import catalogue_fingerprint
from src.infrastructure.mcp.json_schema import properties_of
from src.infrastructure.mcp.pool_catalogue import (
    PoolEntry,
    frozen_declaration,
    list_every_tool,
    normalize_tool,
)
from src.infrastructure.mcp.rate_limit import MCPDeclarationChangedError
from src.infrastructure.mcp.registration import declared_tool_category
from src.infrastructure.mcp.tool_adapter import build_args_schema
from src.infrastructure.observability.metrics_mcp import mcp_user_declaration_checks_total

#: What the check found when the call may go: the same declaration, or another one
#: the call still fits (a revalidation is then due).
DeclarationVerdict = Literal["identical", "compatible"]

#: How strong a mutation a declared category is: only a RISE refuses.
_MUTATION_RANK: dict[str | None, int] = {None: 0, "update": 1, "delete": 2}


@dataclass
class DeclarationCheck:
    """One call's check, run inside the call's session; it keeps its verdict.

    Attributes:
        tool_name: The tool about to be called.
        arguments: The arguments it will be called with.
        frozen: The declaration the call was built from, when known.
        verdict: Set once the check let the call go.
        listing_fingerprint: The fingerprint of the WHOLE catalogue the session
            listed — what verifies an entry, never the called tool alone.
    """

    tool_name: str
    arguments: Mapping[str, Any]
    frozen: Mapping[str, Any] | None
    verdict: DeclarationVerdict | None = None
    listing_fingerprint: str | None = None

    async def verify(self, client: Any) -> None:
        """Read the current declaration and refuse a call it no longer admits.

        Args:
            client: The open MCP session the call will use.

        Raises:
            MCPDeclarationChangedError: The call must not be sent.
        """
        listed, _first, _outcome = await list_every_tool(client)
        declarations = [normalize_tool(tool) for tool in listed]
        self.listing_fingerprint = catalogue_fingerprint(declarations)
        current = next((tool for tool in declarations if tool["name"] == self.tool_name), None)
        if current is None:
            raise MCPDeclarationChangedError("missing")
        if _rank(current) > _rank(self.frozen):
            raise MCPDeclarationChangedError("tightened")
        if not _arguments_fit(current, self.frozen, self.arguments):
            raise MCPDeclarationChangedError("incompatible")
        same = self.frozen is not None and canonical_fingerprint(
            dict(self.frozen)
        ) == canonical_fingerprint(current)
        self.verdict = "identical" if same else "compatible"


def check_for(
    entry: PoolEntry,
    tool_name: str,
    arguments: Mapping[str, Any],
    built_from: str | None,
    declaration: Mapping[str, Any] | None,
) -> DeclarationCheck | None:
    """The check a call owes, or None when it may go unchecked.

    A call is checked when the entry is past its server's freshness, or when it was
    built from ANOTHER catalogue than the entry holds now (a revalidation replaced it
    mid-turn — fresh review 2026-10-29), against the declaration it was built from.

    Args:
        entry: The pool entry the pool holds now.
        tool_name: The tool about to be called.
        arguments: Its arguments.
        built_from: The catalogue fingerprint the calling adapter was built from.
        declaration: The tool's declaration the call was built from.
    """
    rebuilt = built_from is not None and built_from != entry.catalogue_fingerprint
    if entry.catalogue_verified and not rebuilt:
        return None
    frozen = declaration if declaration is not None else frozen_declaration(entry, tool_name)
    return DeclarationCheck(tool_name, arguments, frozen)


def settle_declaration(
    entry: PoolEntry,
    check: DeclarationCheck | None,
    outcome: str | None,
    on_stale: Callable[[UUID, UUID], None] | None,
) -> None:
    """Count a check; the entry is verified only when the listing IS its catalogue.

    The verdict speaks for the called tool alone: one unchanged tool proved nothing
    about another that became destructive (fresh review 2026-10-29). The entry is
    verified when the whole listing equals the catalogue it holds, and a refresh is
    asked for whenever it does not.

    Args:
        entry: The pool entry the pool holds now.
        check: The check that ran, if any.
        outcome: The verdict, or the refusal's reason; None when nothing was checked.
        on_stale: The revalidation the composition root installed, if any.
    """
    if check is None or outcome is None:
        return
    mcp_user_declaration_checks_total.labels(outcome=outcome).inc()
    if check.listing_fingerprint == entry.catalogue_fingerprint:
        entry.catalogue_verified = True
    elif on_stale is not None:
        on_stale(entry.user_id, entry.server_id)


def _rank(tool: Mapping[str, Any] | None) -> int:
    category = declared_tool_category(tool.get("annotations") if tool else None)
    return _MUTATION_RANK.get(category, 0)


def _arguments_fit(
    current: Mapping[str, Any], frozen: Mapping[str, Any] | None, arguments: Mapping[str, Any]
) -> bool:
    model = build_args_schema(dict(current.get("input_schema") or {}))
    if model is not None:
        try:
            model.model_validate(dict(arguments))
        except ValidationError:
            return False
    removed = set(_parameters(frozen)) - set(_parameters(current))
    return not removed & set(arguments)


def _parameters(tool: Mapping[str, Any] | None) -> dict[str, Any]:
    return properties_of(tool.get("input_schema") if tool else None)


__all__ = ["DeclarationCheck", "DeclarationVerdict", "check_for", "settle_declaration"]
