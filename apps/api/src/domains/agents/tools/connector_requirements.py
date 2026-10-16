"""Which provider a catalogue tool's OAuth scopes speak for (RC1.1, 2026-10-13).

The catalogue's multi-provider tools — e-mail, calendar, contacts, tasks —
declare the scopes of their GOOGLE implementation: a Google scope list has no
word for Graph or iCloud. The plan validator and the skill bypass compared
those scopes with what the account granted, whatever its provider: every
e-mail, contacts and calendar step of an Outlook or iCloud account was judged
UNAUTHORIZED (16 times in 7 days on one production account), and a skill
dropped those steps.

The provider a step runs on is read where it is decided: a tool CLASS that
serves a functional category runs on the account's ACTIVE connector of that
category (``provider_resolver``). The tool name → category map is derived by
walking the concrete ``ConnectorTool`` classes, never written by hand, and
nothing is registered in a constructor — the label tools are built per call
(correction C1 of the 2026-10-07 plan). The walk instantiates some seventy
classes whose constructors only name them, on each call: cheaper than any
cache that could be filled before the tool modules are imported.

What the account's active connectors are is the REQUEST's
(``core.context.active_connector_types_ctx``). Unknown — outside a request —
nothing is claimed: the execution, which resolves the provider, is the
authority, as it always was for a verdict (ADR-184).

The same derivation decides what a turn is OFFERED (RC2.1, production
2026-10-07, 19:32): an Outlook account was offered Gmail's settings, the
planner chose them for a mail question and the turn failed while the Outlook
mailbox had just answered. A tool bound to ONE provider — no category, a
connector the person must connect — is offered only to an account whose ACTIVE
connector of that type would run it; a category tool stays offered, its « no
provider is connected » being the honest answer; a keyless or platform-key
connector belongs to the instance (ADR-307) and is never hidden. Nothing may
offer a tool that cannot run (ADR-249's rule, for connectors).
"""

from __future__ import annotations

import inspect
from collections.abc import Collection, Iterator, Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING, Final
from uuid import UUID

from src.domains.agents.tools.base import ConnectorTool
from src.domains.connectors.models import (
    CONNECTOR_FUNCTIONAL_CATEGORIES,
    ConnectorStatus,
    ConnectorType,
)
from src.domains.connectors.provider_resolver import LEGACY_CONNECTOR_ALIASES
from src.domains.connectors.repository import ConnectorRepository
from src.infrastructure.database.session import get_db_context

if TYPE_CHECKING:
    from src.domains.agents.registry.catalogue import ToolManifest

#: Tools bound to one provider that no connector CLASS names: a plain tool whose
#: execution reaches the provider's client directly. Held to the catalogue both
#: ways by the completeness guard — every scoped manifest is named by a class or
#: declared here, and nothing declared here is stale.
PROVIDER_BOUND_WITHOUT_A_CLASS: Final[Mapping[str, ConnectorType]] = MappingProxyType(
    {
        # Gmail's own auto-reply, created as a draft and written through the
        # Gmail client by its executor.
        "set_vacation_responder_tool": ConnectorType.GOOGLE_GMAIL,
    }
)


def _concrete_tool_classes(base: type) -> Iterator[type]:
    """Every connector tool class the application defines that names itself, depth first.

    A class whose constructor still asks for its name is a base, or a tool
    built per call with it (Hue, Brave, Perplexity, weather — keyed tools with
    no OAuth scope): it names no tool by itself. The completeness guard holds
    every SCOPED manifest to a class that does.
    """
    for subclass in base.__subclasses__():
        if (
            not inspect.isabstract(subclass)
            and subclass.__module__.startswith("src.")
            and _names_itself(subclass)
        ):
            yield subclass
        yield from _concrete_tool_classes(subclass)


def _names_itself(tool_class: type) -> bool:
    """Whether the class's constructor takes no argument — it names its own tool."""
    try:
        inspect.signature(tool_class).bind()
    except TypeError:
        return False
    return True


def connector_categories() -> dict[str, str | None]:
    """Each connector tool's name → the functional category it serves.

    Returns:
        ``None`` for a tool bound to one provider (Drive, Gmail labels…), the
        category (``email``, ``calendar``…) for a tool the account's active
        provider of it serves.
    """
    categories: dict[str, str | None] = {}
    for tool_class in _concrete_tool_classes(ConnectorTool):
        category = getattr(tool_class, "functional_category", None)
        categories[str(tool_class().tool_name)] = category if isinstance(category, str) else None
    return categories


def _provider_bound_tools() -> dict[str, ConnectorType]:
    """Each tool bound to ONE provider the person must connect → that connector's type.

    A class with no category runs on its own ``connector_type``, whose
    credentials are read by that exact type (``get_connector_credentials``). A
    keyless or platform-key connector is the instance's, never the person's.
    """
    bound: dict[str, ConnectorType] = dict(PROVIDER_BOUND_WITHOUT_A_CLASS)
    for tool_class in _concrete_tool_classes(ConnectorTool):
        connector_type = getattr(tool_class, "connector_type", None)
        if (
            getattr(tool_class, "functional_category", None) is None
            and isinstance(connector_type, ConnectorType)
            and not connector_type.is_keyless
            and not getattr(tool_class, "uses_global_api_key", False)
        ):
            bound[str(tool_class().tool_name)] = connector_type
    return bound


def unconnected_tool_names(active_connector_types: Collection[str] | None) -> frozenset[str]:
    """The tools bound to a provider no ACTIVE connector of the account serves.

    Args:
        active_connector_types: The account's active connector types (their
            values); None when unknown — then nothing is hidden.

    Returns:
        The names a turn must not be offered: they could only fail.
    """
    if active_connector_types is None:
        return frozenset()
    return frozenset(
        name
        for name, connector_type in _provider_bound_tools().items()
        if connector_type.value not in active_connector_types
    )


def without_unconnected_tools(
    manifests: Sequence[ToolManifest], active_connector_types: Collection[str] | None
) -> list[ToolManifest]:
    """A turn's catalogue minus the tools no connector of the account would run.

    Args:
        manifests: The catalogue, in its order.
        active_connector_types: As for :func:`unconnected_tool_names`.

    Returns:
        The manifests offered, in the same order.
    """
    hidden = unconnected_tool_names(active_connector_types)
    return [manifest for manifest in manifests if manifest.name not in hidden]


async def unconnected_tools_of(user_id: UUID) -> frozenset[str]:
    """:func:`unconnected_tool_names` for one account, read on a short session of its own.

    The voice surfaces have no turn context: each reads the account's active
    connectors where it builds what a voice may hold.

    Args:
        user_id: The account.

    Returns:
        The tool names its voice must not be offered.
    """
    async with get_db_context() as db:
        rows = await ConnectorRepository(db).get_all_by_user(user_id, ConnectorStatus.ACTIVE)
        active = frozenset(row.connector_type.value for row in rows)
    return unconnected_tool_names(active)


def ungranted_scopes(
    manifest: ToolManifest,
    available_scopes: Collection[str],
    active_connector_types: Collection[str] | None,
) -> frozenset[str]:
    """The manifest's OAuth scopes the account has not granted — where they apply.

    Args:
        manifest: The step's tool manifest.
        available_scopes: The scopes the account's active connectors granted.
        active_connector_types: The account's active connector types (their
            values); None when unknown — then nothing is claimed.

    Returns:
        The scopes missing, or none when the step's provider is not the one
        the scopes describe: a category tool served by another provider than
        Google owes no Google scope. A tool bound to Google, or a category with
        no active provider at all, keeps the check — « connect it » is the
        honest answer then. If both Google and another provider remain active,
        the set alone cannot establish which is newest: retain Google's check
        rather than waive the scopes of a provider execution may select.
    """
    required = frozenset(manifest.permissions.required_scopes)
    if not required or active_connector_types is None:
        return frozenset()
    category = connector_categories().get(manifest.name)
    active = {
        LEGACY_CONNECTOR_ALIASES.get(member, member)
        for member in ConnectorType
        if member.value in active_connector_types
    }
    serving = active & CONNECTOR_FUNCTIONAL_CATEGORIES.get(category or "", frozenset())
    if serving and all(not member.is_google for member in serving):
        return frozenset()
    return required - frozenset(available_scopes)


__all__ = [
    "PROVIDER_BOUND_WITHOUT_A_CLASS",
    "connector_categories",
    "unconnected_tool_names",
    "unconnected_tools_of",
    "ungranted_scopes",
    "without_unconnected_tools",
]
