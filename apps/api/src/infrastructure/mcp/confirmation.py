"""Who decides whether LIA asks before a personal MCP tool, and who drives a server.

Spec 2026-10-30 (D1, D4, D6, D9). A personal tool's confirmation is decided by the
first level that says something: the tool's own choice (``user_mcp_tool_choices``), its
server (``user_mcp_servers.hitl_required``), the account (``users.mcp_hitl_required``),
the instance (``MCP_HITL_REQUIRED``). The ReAct
shape of an iterative server is its own choice (``react_expand_iterative``), else the
instance default (``REACT_MCP_EXPAND_ITERATIVE_ENABLED``). Nothing here locks: the
instance values are DEFAULTS (owner decision, 2026-10-30).

This module is the one reader of both instance settings (guarded), so the page, the
synthesis of what a server will do and a run cannot disagree about a default. Reads are
forgiving — a value that is not a boolean falls through to the next level rather than
failing a run — and writes are strict (the API schemas accept booleans only).

It is also where a server's DECLARATION is read (ADR-263): what a tool owes the person
is derived from the server's own annotations, never asserted. The manifest builder
(``registration.py``) asks this module, so the reading has one home.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from src.core.config import settings
from src.domains.agents.registry.catalogue import POLICIES_REQUIRING_REASON
from src.infrastructure.mcp.catalogue_fingerprint import canonical_fingerprint

if TYPE_CHECKING:
    from src.domains.agents.registry.catalogue import MutationPolicy, ToolCategory

__all__ = [
    "NO_TOOL_CHOICES",
    "ConfirmationReason",
    "ConfirmationSource",
    "ServerConfirmation",
    "ServerToolConfirmations",
    "StoredToolChoice",
    "ToolChoice",
    "ToolConfirmation",
    "confirmation_reason",
    "declaration_fingerprint",
    "dedicated_agents_available",
    "declaration_reason",
    "declared_tool_category",
    "derive_mcp_mutation_policy",
    "derive_mcp_mutation_policy_reason",
    "effective_react_expand",
    "instance_confirmation",
    "resolve_server_confirmation",
    "resolve_tool_confirmation",
    "suspended_choices",
]


class ConfirmationSource(StrEnum):
    """The level whose value decided a server's confirmation."""

    SERVER = "server"
    ACCOUNT = "account"
    INSTANCE = "instance"


class ConfirmationReason(StrEnum):
    """Why LIA asks — or does not ask — before a tool's call (a closed vocabulary)."""

    TOOL_ALWAYS = "tool_always"
    TOOL_NEVER = "tool_never"
    SERVER_ALWAYS = "server_always"
    ACCOUNT_ALWAYS = "account_always"
    INSTANCE_ALWAYS = "instance_always"
    DECLARED_DESTRUCTIVE = "declared_destructive"
    DECLARED_MODIFYING = "declared_modifying"
    DECLARED_ADDITIVE = "declared_additive"
    DECLARED_READ_ONLY = "declared_read_only"
    NOT_DECLARED = "not_declared"


_ALWAYS_REASONS = {
    ConfirmationSource.SERVER: ConfirmationReason.SERVER_ALWAYS,
    ConfirmationSource.ACCOUNT: ConfirmationReason.ACCOUNT_ALWAYS,
    ConfirmationSource.INSTANCE: ConfirmationReason.INSTANCE_ALWAYS,
}


@dataclass(frozen=True)
class ServerConfirmation:
    """A server's resolved confirmation.

    Attributes:
        always: True asks before every call of the server's tools, reads included;
            False follows what the server declares, tool by tool.
        source: The level that decided.
    """

    always: bool
    source: ConfirmationSource


class ToolChoice(StrEnum):
    """The person's choice for one tool — the first level (spec 2026-10-30 D6)."""

    ALWAYS = "always"
    NEVER = "never"


@dataclass(frozen=True)
class StoredToolChoice:
    """A tool choice as stored, with the declaration it was made against.

    Attributes:
        choice: Always or never.
        fingerprint: :func:`declaration_fingerprint` of the tool when it was chosen.
    """

    choice: ToolChoice
    fingerprint: str


#: No tool has a choice of its own — an immutable default, shared safely.
NO_TOOL_CHOICES: Mapping[str, StoredToolChoice] = MappingProxyType({})


@dataclass(frozen=True)
class ToolConfirmation:
    """One tool's confirmation once its own choice is read.

    Attributes:
        hitl_required: LIA asks before every call (the tool's *always*, else the
            server's resolved confirmation).
        standing_approval: The tool's *never*: what its declaration owes is approved
            in advance — the manifest builder marks it when the declaration owes a
            confirmation, and only then.
        choice: The choice that applied; None when the levels below decided.
        suspended: A *never* made against another declaration: it does not apply
            until the person chooses again.
    """

    hitl_required: bool
    standing_approval: bool
    choice: ToolChoice | None
    suspended: bool


def declaration_fingerprint(tool: Mapping[str, Any]) -> str:
    """What a *never* is bound to: the tool's annotations and input schema.

    The description is left out — servers reword it for cosmetic reasons — so a
    choice survives a rewording and is suspended by a change of what the tool
    declares or accepts.

    Args:
        tool: A normalized tool of the server's catalogue.

    Returns:
        A stable hexadecimal digest.
    """
    return canonical_fingerprint(
        {
            "annotations": tool.get("annotations") or {},
            "input_schema": tool.get("input_schema") or {},
        }
    )


def resolve_tool_confirmation(
    server_always: bool, stored: StoredToolChoice | None, tool: Mapping[str, Any]
) -> ToolConfirmation:
    """A tool's confirmation: its own choice, else its server's (spec 2026-10-30 D1, D6).

    *Always* applies whatever the declaration — asking more needs no binding. *Never*
    applies only to the declaration it was chosen against; otherwise it is suspended
    and the levels below decide.

    Args:
        server_always: The server's resolved confirmation (``ServerConfirmation.always``).
        stored: The tool's stored choice, if any.
        tool: The tool as the catalogue lists it now.

    Returns:
        The tool's confirmation.
    """
    if stored is None:
        return ToolConfirmation(server_always, False, None, False)
    if stored.choice is ToolChoice.ALWAYS:
        return ToolConfirmation(True, False, ToolChoice.ALWAYS, False)
    if stored.fingerprint == declaration_fingerprint(tool):
        return ToolConfirmation(False, True, ToolChoice.NEVER, False)
    return ToolConfirmation(server_always, False, None, True)


@dataclass(frozen=True)
class ServerToolConfirmations:
    """A server's resolved confirmation and its tools' choices, read once per run.

    Attributes:
        server_always: The server's resolved confirmation (the task's, for a dedicated
            agent).
        choices: The stored choices, by the tool's name on the server.
    """

    server_always: bool
    choices: Mapping[str, StoredToolChoice]

    def for_tool(self, tool: Mapping[str, Any]) -> ToolConfirmation:
        """The confirmation of one tool of the catalogue, by its exact name.

        Forgiving: a stored value that is not a choice falls through to the levels
        below rather than failing a run.
        """
        stored = self.choices.get(str(tool.get("name", "")))
        if not isinstance(stored, StoredToolChoice):
            stored = None
        return resolve_tool_confirmation(self.server_always, stored, tool)


def suspended_choices(
    tools: Sequence[Mapping[str, Any]], choices: Mapping[str, StoredToolChoice]
) -> int:
    """How many listed tools carry a « never » made against another declaration.

    What the server's card says until the person chooses again (spec 2026-10-30 D6);
    a choice for a tool the catalogue no longer lists is inert, and not counted.

    Args:
        tools: The server's last catalogue.
        choices: Its tools' stored choices.

    Returns:
        The number of suspended choices.
    """
    resolved = ServerToolConfirmations(False, choices)
    return sum(1 for tool in tools if resolved.for_tool(tool).suspended)


def instance_confirmation() -> bool:
    """The instance's default, ``MCP_HITL_REQUIRED`` — for accounts that never chose.

    Also the rule of the administrator's servers, registered once at boot.

    Returns:
        True when the instance asks before every MCP call by default.
    """
    return settings.mcp_hitl_required


def resolve_server_confirmation(
    server_value: bool | None, account_value: bool | None
) -> ServerConfirmation:
    """A personal server's confirmation: the server's choice, else the account's, else the instance's.

    Args:
        server_value: ``user_mcp_servers.hitl_required`` as stored (None: never chosen).
        account_value: ``users.mcp_hitl_required`` as stored (None: never chosen).

    Returns:
        The resolved confirmation and the level it came from.
    """
    if isinstance(server_value, bool):
        return ServerConfirmation(server_value, ConfirmationSource.SERVER)
    if isinstance(account_value, bool):
        return ServerConfirmation(account_value, ConfirmationSource.ACCOUNT)
    return ServerConfirmation(instance_confirmation(), ConfirmationSource.INSTANCE)


def dedicated_agents_available() -> bool:
    """Whether this instance runs dedicated agents at all (``MCP_REACT_ENABLED``).

    Off, an iterative server is registered like a standard one: its tools are
    driven directly in both modes, and the page offers no dedicated-agent choice.

    Returns:
        True when an iterative server may get its dedicated agent.
    """
    return settings.mcp_react_enabled


def effective_react_expand(server_value: bool | None) -> bool:
    """Whether the ReAct loop drives an iterative server's tools directly.

    Args:
        server_value: ``user_mcp_servers.react_expand_iterative`` as stored, or None
            for a server that never chose (and every administrator server).

    Returns:
        True when the loop binds the server's individual tools; False when it hands
        the task to the server's dedicated agent.
    """
    if isinstance(server_value, bool):
        return server_value
    return settings.react_mcp_expand_iterative_enabled


def react_drives_tools_directly(
    *, react_expand: bool, has_individuals: bool, is_mcp_app: bool
) -> bool:
    """Whether the ReAct loop binds an iterative server's tools rather than its task.

    Read by the ReAct selector and by the synthesis of what a server will do, so the
    page cannot describe a shape the loop does not take.

    Args:
        react_expand: The task manifest's resolved shape (:func:`effective_react_expand`).
        has_individuals: Whether the server's individual tools resolved for the run.
        is_mcp_app: Whether the server is an MCP App, which keeps its dedicated agent
            for the app workflow (spec 2026-10-29, D5).

    Returns:
        True when the loop drives the server's tools directly.
    """
    return react_expand and has_individuals and not is_mcp_app


def declared_tool_category(annotations: Any) -> ToolCategory | None:
    """Derive a catalogue category from a server behaviour hint — tightening only.

    The MCP specification is normative here:

        "For trust & safety and security, clients MUST consider tool
         annotations to be untrusted unless they come from trusted servers."

    So the asymmetry below is a requirement, not caution. A declared MUTATION is
    acted upon: the worst a lying server buys itself is one confirmation too
    many. A declared ``readOnlyHint: true`` is NOT, because a declared category
    WINS over the name heuristic in ``_declared_mutation_flag`` — believing it
    would remove the tool from the invalid-mutation safety net, from HITL scope
    detection and from the read-only requirement of the initiative phase, on the
    word of a third party.

    Returning None is therefore the safe answer, not a failure: it leaves
    ``MUTATION_TOOL_PATTERNS`` in charge exactly as before.

    What this buys, measured on one real server: none of ``cancel_subscription``,
    ``upgrade``, ``disconnect_institution`` or ``forget`` carries one of the nine
    mutation verbs, so every one of them is classified read-only by the name
    heuristic today.

    Args:
        annotations: Normalised hints from :func:`extract_tool_annotations`, of
            any shape.

    Returns:
        ``"delete"`` for a declared destructive tool, ``"update"`` for one
        declared as performing only additive updates, or None when the
        declaration says nothing this codebase may safely act on.
    """
    if not isinstance(annotations, dict):
        return None
    destructive = annotations.get("destructive_hint")
    read_only = annotations.get("read_only_hint")
    if destructive is True:
        return "delete"
    if read_only is False:
        # Spec: destructiveHint defaults to TRUE, and "If false, the tool
        # performs only additive updates" — both are mutations either way.
        return "update" if destructive is False else "delete"
    return None


def derive_mcp_mutation_policy(hitl_required: bool, annotations: Any) -> MutationPolicy | None:
    """Derive the confirmation a third-party MCP tool owes (ADR-263).

    Never more permissive than what is known, and asymmetric for the same
    reason as :func:`declared_tool_category`: a declared mutation is acted upon,
    a declared read-only is not believed.

    - the server's HITL setting is the USER's decision and wins outright;
    - a declared destructive tool, or one declared "not read-only" with nothing
      said about destruction (the spec defaults ``destructiveHint`` to true),
      gets ``confirm``;
    - one explicitly declared "not read-only AND not destructive" — the spec's
      "performs only additive updates" — gets ``reversible``;
    - anything else yields None: no policy is derived, and the name heuristic
      keeps its job exactly as before.

    Args:
        hitl_required: Resolved per-server HITL requirement (the server's choice,
            else the account's, else ``MCP_HITL_REQUIRED`` — see
            :func:`resolve_server_confirmation`).
        annotations: Normalised hints from :func:`extract_tool_annotations`, of
            any shape — a third party is not obliged to be well-formed.

    Returns:
        The derived policy, or None when nothing may safely be concluded.
    """
    if hitl_required:
        return "confirm"
    category = declared_tool_category(annotations)
    if category == "delete":
        return "confirm"
    if category == "update":
        return "reversible"
    return None


def derive_mcp_mutation_policy_reason(policy: MutationPolicy | None) -> str | None:
    """The written justification a derived exempting policy owes (ADR-263).

    ``reversible`` skips the confirmation, so the completeness doctrine demands
    a reason. For a third-party tool the reason is not ours to invent: it is
    what the SERVER declared, quoted as such.

    Args:
        policy: The derived policy, or None.

    Returns:
        The reason for a policy that requires one, else None.
    """
    if policy in POLICIES_REQUIRING_REASON:
        return (
            "The server declares this tool non-destructive and additive-only "
            "(MCP annotations); LIA never loosens that declaration."
        )
    return None


def declaration_reason(annotations: object) -> ConfirmationReason:
    """What the server's declaration of one tool says, as a reason.

    The same reading as ``declared_tool_category`` (the manifest's category), so the
    reason never contradicts what the manifest carries: a declared destructive tool,
    or one declared "not read-only" with nothing said about destruction (the MCP
    specification defaults ``destructiveHint`` to true), is a deletion; one declared
    "not read-only, not destructive" only adds.

    Args:
        annotations: Normalised hints, of any shape — a third party is not obliged
            to be well-formed.

    Returns:
        The declaration's reason.
    """
    if not isinstance(annotations, dict):
        return ConfirmationReason.NOT_DECLARED
    category = declared_tool_category(annotations)
    if category == "update":
        return ConfirmationReason.DECLARED_ADDITIVE
    if category == "delete":
        if annotations.get("destructive_hint") is True:
            return ConfirmationReason.DECLARED_DESTRUCTIVE
        return ConfirmationReason.DECLARED_MODIFYING
    if annotations.get("read_only_hint") is True:
        return ConfirmationReason.DECLARED_READ_ONLY
    return ConfirmationReason.NOT_DECLARED


def confirmation_reason(
    server: ServerConfirmation, annotations: object, choice: ToolChoice | None = None
) -> ConfirmationReason:
    """Why a tool is asked about, or not: its own choice first, then the levels below.

    Args:
        server: The server's resolved confirmation.
        annotations: The tool's normalised hints.
        choice: The tool's choice that applied (a suspended one does not).

    Returns:
        The tool's choice, the level that asks for every call, or what the
        declaration says.
    """
    if choice is ToolChoice.ALWAYS:
        return ConfirmationReason.TOOL_ALWAYS
    if choice is ToolChoice.NEVER:
        return ConfirmationReason.TOOL_NEVER
    if server.always:
        return _ALWAYS_REASONS[server.source]
    return declaration_reason(annotations)
