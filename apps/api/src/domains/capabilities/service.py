"""What LIA can actually do for this account, in one read.

The starter checklist detects seven capabilities CLIENT-side, through seven
hooks. That is fine for seven items on a card the reader dismisses once. It is
not fine for a living map of everything the assistant can do: a dozen requests
fired at mount, a dozen loading states, and a dozen chances for one of them to
disagree with another about whether voice is on.

So this reads them server-side, in one pass, following the briefing doctrine:
independent probes gathered with ``asyncio.gather``, **each on its own
session** (an ``AsyncSession`` is not safe for concurrent use), and every probe
failing SOFT — a capability whose probe raised is reported as not-ready rather
than taking the page down. A map that refuses to draw because one node could
not be counted is worse than a map with one dim node.

Three states, and the difference between the last two is the whole point:

- **unavailable** — the instance disabled the subsystem. It is not offered at
  all (gate-keeper, ADR-061): a control the product cannot honour is worse
  than an absent one;
- **dormant** — available, nothing set up. It carries the ONE next step;
- **live** — genuinely usable, with what makes it so (a count, a name).

No level, no experience points, no comparison with anyone. "Three connectors
linked" is a fact about this account; "you are 62 % complete" is a score, and
a score invites a competition nobody asked to enter.

## Availability is the effective one, not the deployment's

Since the capability switches (ADR-216 family), an administrator can turn image
generation, documents, MCP, telephony… off at runtime, inside the deployment's
ceiling. Reading the raw ``settings.*_enabled`` flag would let the map announce
as available something the operator switched off an hour ago. The set of
disabled capabilities is therefore read ONCE per request and composed in.

## The map may not fall behind the product

Nodes are declared in tables, and ``PLATFORM_CAPABILITY_NODES`` +
``CAPABILITIES_OFF_THE_MAP`` **partition** the ``PlatformCapability`` enum —
asserted at import, so a capability added without deciding its fate on the map
is a boot failure, not a silent omission (ADR-085 doctrine). Between v1.30.5
and v1.30.9 the product gained document generation, plugins and habits while
the map kept describing an older assistant; that class of drift is what the
assert closes.
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import func, select

from src.core.config import settings
from src.domains.feature_switches.registry import PlatformCapability, disabled_capabilities
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only, breaks an import cycle
    from src.domains.users.models import User

logger = get_logger(__name__)


@dataclass(frozen=True)
class CapabilityProbe:
    """One node of the map, as the service resolved it.

    Attributes:
        key: Stable identifier — the client resolves its label from it, so a
            new capability never surfaces as a raw i18n key.
        available: Whether this instance offers the subsystem at all.
        active: Whether the account can actually use it right now.
        detail: A COUNT the reader can verify, when there is one. Never a
            score: "3 connectors" is a fact, "62 %" is a competition.
    """

    key: str
    available: bool
    active: bool
    detail: int | None = None


@dataclass(frozen=True)
class _CountedNode:
    """A capability whose liveness is "this account owns at least one".

    Attributes:
        key: The map node it draws.
        load_model: Imports and returns the mapped class. A callable rather
            than the class itself: these imports are deferred on purpose, so
            the domain graph keeps no edge from capabilities to every domain.
        capability: The platform switch bounding it, when it has one — the
            deployment ceiling AND the operator's switch, composed.
        env_flag: A plain settings flag, for subsystems with no switch.
        load_filters: Extra equality filters narrowing what counts, resolved
            at call time for the same reason ``load_model`` is — a filter
            value often comes from an enum living in that domain.
        count_with: Counts through a REPOSITORY instead of a plain table
            count, for a capability whose "what counts" rule lives there
            (peers: accepted, either direction). Re-expressing such a rule as
            a filter here would make this module a second authority on it
            (ADR-185). Mutually exclusive with ``load_model``.
    """

    key: str
    load_model: Callable[[], Any] | None = None
    capability: PlatformCapability | None = None
    env_flag: str | None = None
    load_filters: Callable[[], Mapping[str, Any]] | None = None
    count_with: Callable[[UUID], Awaitable[int]] | None = None


# Deliberately NOT nodes (audited 2026-08-20, evolution program): the
# activity timeline and the proposals inbox are WINDOWS over other nodes'
# state (proactivity, habits, journals, relations) — a node for them would
# re-count what those nodes already count, making the map a second
# authority on the same figures (ADR-185). The briefing readout rides the
# "voice" switch; procedural memories ride the "memory" tally.
COUNTED_NODES: tuple[_CountedNode, ...] = (
    _CountedNode("connectors", lambda: _import("connectors.models", "Connector")),
    _CountedNode(
        "memory",
        lambda: _import("memories.models", "Memory"),
        # ADR-235: invalidated memories stay in the table (supersession
        # trail) — the node counts the ACTIVE set, the figure the panel shows.
        load_filters=lambda: {"invalidated_at": None},
    ),
    _CountedNode(
        "interests",
        lambda: _import("interests.models", "UserInterest"),
        load_filters=lambda: {"status": _import("interests.models", "InterestStatus").ACTIVE.value},
    ),
    _CountedNode("routines", lambda: _import("scheduled_actions.models", "ScheduledAction")),
    _CountedNode("relations", lambda: _import("open_loops.models", "OpenLoop")),
    _CountedNode(
        "journals", lambda: _import("journals.models", "JournalEntry"), env_flag="journals_enabled"
    ),
    _CountedNode(
        "spaces",
        lambda: _import("rag_spaces.models", "RAGSpace"),
        capability=PlatformCapability.RAG_SPACES,
    ),
    _CountedNode(
        "channels",
        lambda: _import("channels.models", "UserChannelBinding"),
        env_flag="channels_enabled",
    ),
    _CountedNode(
        "skills",
        lambda: _import("skills.models", "UserSkillState"),
        capability=PlatformCapability.SKILLS,
    ),
    # Agent Plugins (ADR-225) — shipped v1.30.7, absent from the map until
    # 2026-08-18. No platform switch of its own: plugins carry skills and MCP
    # servers, each already switchable.
    _CountedNode(
        "plugins", lambda: _import("plugins.models", "UserPlugin"), env_flag="plugins_enabled"
    ),
    # Learned habits (ADR-214) — shipped v1.28.0, same omission.
    _CountedNode(
        "habits", lambda: _import("habits.models", "UserHabit"), env_flag="habits_enabled"
    ),
    _CountedNode(
        "mcp_servers",
        lambda: _import("user_mcp.models", "UserMCPServer"),
        capability=PlatformCapability.MCP,
    ),
    _CountedNode(
        "telephony",
        lambda: _import("telephony.models", "PhoneCall"),
        capability=PlatformCapability.TELEPHONY,
    ),
    # Counted through the repository that owns the "accepted, either
    # direction" rule rather than by re-expressing it here.
    _CountedNode("peers", env_flag="peers_enabled", count_with=lambda uid: _count_peers(uid)),
)

#: Capabilities the account switches on rather than fills: they carry no tally,
#: so they publish ``detail=None`` and the client says "Active" rather than
#: inventing "Active — 0 items" (ADR-185).
SWITCH_NODE_KEYS: tuple[str, ...] = (
    "voice",
    "proactivity",
    "personality",
    "images",
    "documents",
)

#: Every node key the payload can carry. The client must be able to name each.
MAP_NODE_KEYS: frozenset[str] = frozenset(
    [node.key for node in COUNTED_NODES] + list(SWITCH_NODE_KEYS)
)

#: Which map node a platform capability draws. Several capabilities may share
#: one node (speech-to-text and text-to-speech are both "voice" to a reader).
PLATFORM_CAPABILITY_NODES: dict[PlatformCapability, str] = {
    PlatformCapability.STT: "voice",
    PlatformCapability.TTS: "voice",
    PlatformCapability.IMAGE_GENERATION: "images",
    PlatformCapability.DOCUMENT_GENERATION: "documents",
    PlatformCapability.RAG_SPACES: "spaces",
    PlatformCapability.SKILLS: "skills",
    PlatformCapability.MCP: "mcp_servers",
    PlatformCapability.TELEPHONY: "telephony",
}

#: Capabilities deliberately absent from the map, and why. The map's third
#: column is "the ONE next step"; a capability with no per-account state and
#: no destination would draw a star that never changes and links nowhere.
CAPABILITIES_OFF_THE_MAP: dict[PlatformCapability, str] = {
    PlatformCapability.ATTACHMENTS: (
        "Ambient: the paperclip is either in the composer or not. Nothing to "
        "set up, nothing to count, and no settings section to send anyone to."
    ),
    PlatformCapability.WEB_SEARCH: (
        "Ambient: the assistant reaches the web when a question needs it. No "
        "per-account state, so the star could only ever be lit."
    ),
    PlatformCapability.BROWSER: (
        "Ambient, same as web search: an ability the planner uses on its own, "
        "with nothing for the reader to configure or verify."
    ),
}


def _assert_capability_map_coverage() -> None:
    """Refuse to boot when a platform capability has no decided map fate.

    ADR-085 doctrine. The alternative is the failure this whole module now
    guards against: a feature ships and the map quietly keeps describing the
    product as it was.

    Raises:
        AssertionError: Listing the undecided or double-declared members.
    """
    mapped, excluded = set(PLATFORM_CAPABILITY_NODES), set(CAPABILITIES_OFF_THE_MAP)
    undecided = set(PlatformCapability) - mapped - excluded
    assert not undecided, (
        "PlatformCapability members with no capability-map decision: "
        + ", ".join(sorted(c.value for c in undecided))
        + " — add a node in PLATFORM_CAPABILITY_NODES or a reason in "
        "CAPABILITIES_OFF_THE_MAP."
    )
    assert not mapped & excluded, "A capability cannot be both mapped and excluded."
    unknown = {key for key in PLATFORM_CAPABILITY_NODES.values() if key not in MAP_NODE_KEYS}
    assert not unknown, f"PLATFORM_CAPABILITY_NODES points at unknown nodes: {sorted(unknown)}"


_assert_capability_map_coverage()


def _import(module: str, name: str) -> Any:
    """Import one domain model by name, at call time.

    Args:
        module: Path under ``src.domains``, e.g. ``memories.models``.
        name: Mapped class to return.

    Returns:
        The mapped class.
    """
    return getattr(importlib.import_module(f"src.domains.{module}"), name)


async def _count(model: Any, user_id: UUID, **filters: Any) -> int:
    """Count rows of one user-scoped table, on its OWN session.

    ``model`` is deliberately untyped: the helper accepts any mapped class
    carrying ``user_id``, and SQLAlchemy exposes those columns as ``Mapped[…]``
    descriptors that a ``Protocol`` cannot describe without making
    ``model.user_id == user_id`` un-typeable. The alternative — one counting
    function per table — would be ten copies of this query.

    Args:
        model: The mapped class. Must carry a ``user_id`` column.
        user_id: Owner.
        **filters: Extra equality filters.

    Returns:
        The count, or 0 when the read failed — a probe never raises, so one
        unreachable table cannot blank the whole map.
    """
    try:
        async with get_db_context() as db:
            stmt = select(func.count()).select_from(model).where(model.user_id == user_id)
            for column, value in filters.items():
                stmt = stmt.where(getattr(model, column) == value)
            return int((await db.execute(stmt)).scalar() or 0)
    except Exception as exc:  # noqa: BLE001 — a probe degrades, it never fails
        logger.debug(
            "capability_probe_failed", model=getattr(model, "__name__", "?"), error=str(exc)
        )
        return 0


def _offers(
    capability: PlatformCapability | None,
    env_flag: str | None,
    disabled: frozenset[PlatformCapability],
) -> bool:
    """Whether this instance offers a subsystem right now.

    Args:
        capability: Its platform switch, when it has one. ``disabled`` already
            composes the deployment ceiling with the operator's switch, so
            membership answers the whole question.
        env_flag: A plain settings flag, for subsystems with no switch.
        disabled: Capabilities currently off.

    Returns:
        True when the subsystem is offered; a subsystem with neither bound is
        always offered.
    """
    if capability is not None:
        return capability not in disabled
    if env_flag is not None:
        return bool(getattr(settings, env_flag, False))
    return True


async def _counted(
    node: _CountedNode, user_id: UUID, disabled: frozenset[PlatformCapability]
) -> CapabilityProbe:
    """Resolve one counted capability.

    Args:
        node: Its declaration.
        user_id: Owner.
        disabled: Capabilities currently off.

    Returns:
        Its probe. An unavailable subsystem is never queried — the router
        drops it from the payload anyway (gate-keeper, ADR-061).
    """
    if not _offers(node.capability, node.env_flag, disabled):
        return CapabilityProbe(node.key, available=False, active=False)
    if node.count_with is not None:
        total = await node.count_with(user_id)
        return CapabilityProbe(node.key, available=True, active=total > 0, detail=total)
    try:
        assert node.load_model is not None, f"{node.key} declares no way to count"
        model = node.load_model()
    except Exception as exc:  # noqa: BLE001 — a probe degrades, it never fails
        logger.debug("capability_model_import_failed", node=node.key, error=str(exc))
        return CapabilityProbe(node.key, available=True, active=False, detail=0)
    filters = node.load_filters() if node.load_filters else {}
    total = await _count(model, user_id, **filters)
    return CapabilityProbe(node.key, available=True, active=total > 0, detail=total)


async def _count_peers(user_id: UUID) -> int:
    """Accepted peer connections, counted by the repository that owns the rule.

    "Accepted, either direction" lives in ``PeersRepository``; re-expressing
    it as a filter here would make this module a second authority on who is
    connected to whom (ADR-185).

    Args:
        user_id: Owner.

    Returns:
        The count, or 0 when the read failed — like every other probe.
    """
    try:
        async with get_db_context() as db:
            from src.domains.peers.repository import PeersRepository

            return len(await PeersRepository(db).list_accepted_for_user(user_id))
    except Exception as exc:  # noqa: BLE001 — a probe degrades, it never fails
        logger.debug("capability_probe_failed", model="peers", error=str(exc))
        return 0


def _from_user(user: User, disabled: frozenset[PlatformCapability]) -> list[CapabilityProbe]:
    """Capabilities the USER row already answers — no query needed.

    Reading them from the authenticated row rather than re-querying keeps the
    map's answer identical to the one every other surface gives.

    Args:
        user: The authenticated user row.
        disabled: Capabilities currently off.

    Returns:
        One probe per switch-shaped capability, each with ``detail=None``:
        they are switches, not collections, and "Active — 0 items" would read
        as an empty capability rather than as one with nothing to count.
    """
    speech = _offers(PlatformCapability.STT, None, disabled) or _offers(
        PlatformCapability.TTS, None, disabled
    )
    images = _offers(PlatformCapability.IMAGE_GENERATION, None, disabled)
    documents = _offers(PlatformCapability.DOCUMENT_GENERATION, None, disabled)
    return [
        CapabilityProbe(
            "voice",
            available=speech,
            active=speech and (user.voice_enabled or user.voice_mode_enabled),
        ),
        CapabilityProbe(
            "proactivity",
            available=settings.heartbeat_enabled,
            active=settings.heartbeat_enabled and user.heartbeat_enabled,
        ),
        CapabilityProbe(
            "personality",
            available=True,
            active=user.personality_id is not None,
        ),
        # Image generation is an explicit per-account opt-in; document
        # generation has none — an instance that offers it offers it to
        # everyone, so the node is live as soon as it is available. Claiming a
        # dormant state would send the reader looking for a switch that does
        # not exist.
        CapabilityProbe(
            "images",
            available=images,
            active=images and bool(getattr(user, "image_generation_enabled", False)),
        ),
        CapabilityProbe("documents", available=documents, active=documents),
    ]


async def resolve_capabilities(user: User) -> list[CapabilityProbe]:
    """Every capability of the map, resolved in one pass.

    Args:
        user: The authenticated user row.

    Returns:
        One probe per capability, in a STABLE order — the map's layout is
        deterministic, so the same account draws the same picture twice.
    """
    user_id: UUID = user.id
    # One read for every switch, before any probe: the alternative is a Redis
    # round-trip per capability on a page-load path.
    disabled = await disabled_capabilities()
    probes = await asyncio.gather(
        *(_counted(node, user_id, disabled) for node in COUNTED_NODES),
        return_exceptions=False,
    )
    return [*probes, *_from_user(user, disabled)]
