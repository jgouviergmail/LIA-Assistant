"""Peer-connection awareness for the query analyzer (defect 2026-07-30).

The analyzer must decide whether "Est-ce que Jerome G est dispo demain ?" is a
question about the USER's calendar (``event``), about their address book
(``contact``), or about another USER of this instance who shares their
calendar (``peer``). Measured on the dev instance, it answered
``event`` + ``contact`` three times out of four and ``peer`` once — for the
byte-identical sentence. The three misroutes each produced a plan over
``get_events_tool`` / ``get_contacts_tool``, i.e. the ASKING user's own data;
both steps failed the OAuth scope check on an account with no connectors, the
whole plan was invalidated, and the user was told nothing was configured while
the connection, the share and the peer's calendar were all healthy.

The root cause is missing knowledge, not a weak description: the ``peer``
domain is described as "Connections with OTHER USERS of this LIA instance",
which the model cannot apply without knowing who those users are. This module
supplies exactly that fact, in two layers:

1. :func:`load_connected_peer_names` + :func:`format_peer_directory` inject the
   user's accepted connections into the analyzer prompt — the LLM can then
   recognise the name on its own (root-cause fix).
2. :func:`detect_mentioned_peers` + :func:`apply_peer_domain_correction` add
   ``peer`` deterministically when a connected name was mentioned and the LLM
   still answered with a peer-confusable domain (guarantee).

Two deliberate trade-offs, both load-bearing:

- **Additive, never substitutive.** "Suis-je libre demain pour voir Jerome ?"
  genuinely needs the asking user's own calendar. Removing ``event`` would
  trade one broken query class for another, so the correction only ever
  appends and lets the semantic tool selector arbitrate — which it does
  correctly: on the one turn that routed ``peer``,
  ``get_peer_availability_tool`` scored 0.944 against 0.028 for
  ``get_events_tool``.
- **Recall over precision, bounded by a gate.** Matching a first name can
  over-trigger (a peer named "Rose" against "une rose rouge"). The cost is one
  extra low-scoring candidate tool; the cost of the opposite error is the
  feature not working at all. The :data:`PEER_CONFUSABLE_DOMAINS` gate bounds
  it to the domains where a peer read is plausible, and every correction is
  counted and logged so over-triggering is observable rather than silent.

No cache: this is one indexed query per action turn, behind a feature flag,
against a router phase whose LLM call costs ~4 s. A TTL cache would add a
staleness window in which a freshly accepted connection stays unroutable —
paying a real defect class for an unmeasurable gain.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Final
from uuid import UUID

from src.core.config import settings
from src.domains.peers.repository import PeersRepository
from src.domains.shared.name_mentions import detect_mentioned_names, usable_names
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

PEER_DOMAIN: Final[str] = "peer"

# Domains an analyzer verdict must contain for the correction to fire.
# `event` and `task` are exactly what a peer can share (spec A1: calendar
# availability and task titles); `contact` is the address-book domain the LLM
# reaches for when it mistakes a connected user for a contact — the measured
# misroute. Anything else (email, weather, places…) is a turn where a peer
# name is incidental, and where adding the peer tools would be noise.
PEER_CONFUSABLE_DOMAINS: Final[frozenset[str]] = frozenset({"event", "task", "contact"})

# Rendered when the user has no accepted connection. An empty section reads as
# a truncated prompt; an explicit sentinel reads as "nobody", which is the fact.
PEER_DIRECTORY_EMPTY: Final[str] = "(none — this user has no connected users)"

# A one- or two-letter token ("G" in "Jérôme G") occurs in nearly every
# sentence: matching it alone would fire the correction on every turn.
# Prompt budget. Beyond this the directory stops being a useful hint and
# starts costing tokens on every single turn.
_MAX_DIRECTORY_NAMES: Final[int] = 50


async def load_connected_peer_names(user_id: str | None) -> list[str]:
    """Load the display names of the user's accepted peer connections.

    Args:
        user_id: ``langgraph_user_id`` from the run configurable. Absent on
            automated runs and malformed in tests — both yield no names rather
            than an error.

    Returns:
        Display names, or an empty list when peers are disabled, the id is
        unusable, or the database is unreachable.
    """
    if not getattr(settings, "peers_enabled", False):
        return []
    try:
        peer_owner = UUID(str(user_id))
    except AttributeError, TypeError, ValueError:
        return []
    try:
        async with get_db_context() as db:
            return await PeersRepository(db).list_accepted_peer_display_names(peer_owner)
    except Exception as exc:
        # Degrade to "no directory": the awareness layer is lost for this turn,
        # raising would lose the turn. The deterministic layer degrades with it
        # (no names, no correction), which is the same state as before the fix.
        logger.warning(
            "peer_directory_load_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return []


def format_peer_directory(names: Sequence[str | None]) -> str:
    """Render the connected-users block injected in the analyzer prompt.

    Args:
        names: Peer display names, in repository order.

    Returns:
        One ``- name`` line per peer, bounded by :data:`_MAX_DIRECTORY_NAMES`,
        or :data:`PEER_DIRECTORY_EMPTY` when there is nobody to list.
    """
    usable = usable_names(names)
    if not usable:
        return PEER_DIRECTORY_EMPTY
    shown = usable[:_MAX_DIRECTORY_NAMES]
    # `full_name` is user-controlled free text and the prompt template is
    # rendered with `str.format` — the same escaping the template already
    # applies to `user_query`.
    lines = [f"- {name.replace('{', '{{').replace('}', '}}')}" for name in shown]
    if len(usable) > len(shown):
        lines.append(f"- (+{len(usable) - len(shown)} more)")
    return "\n".join(lines)


def detect_mentioned_peers(
    texts: Iterable[str | None],
    peer_names: Sequence[str | None],
) -> list[str]:
    """Find which connected peers are named in the turn's texts.

    Matching is accent- and case-insensitive (the exact ``fold_name`` semantics
    the peer tools already use to resolve a name against the connection list —
    the routing and the tool must agree on who exists), on whole words, over
    the full name and each of its tokens.

    Args:
        texts: Every text that may carry the name — the original query, the
            English pivot, and the values of resolved references (``"mon
            frère"`` → ``"Jérôme G"``, where the name is in the mapping and
            never in what the user typed).
        peer_names: Display names of the user's accepted connections.

    Returns:
        The matching display names, in directory order, without duplicates.
    """
    return detect_mentioned_names(texts, peer_names)


def apply_peer_domain_correction(
    domains: Sequence[str],
    mentioned_peers: Sequence[str],
) -> list[str]:
    """Add the ``peer`` domain when a connected user was named but not routed.

    Args:
        domains: Domains as decided by the analyzer LLM, primary first.
        mentioned_peers: Output of :func:`detect_mentioned_peers`.

    Returns:
        A new list — ``domains`` unchanged, or with ``peer`` appended.
    """
    corrected = list(domains)
    if not corrected or not mentioned_peers or PEER_DOMAIN in corrected:
        return corrected
    if not any(domain in PEER_CONFUSABLE_DOMAINS for domain in corrected):
        return corrected

    from src.infrastructure.observability.metrics_registry import peer_domain_correction_total

    # No PII at INFO: the COUNT of named peers, never the names themselves.
    logger.info(
        "peer_domain_correction_applied",
        domains_before=corrected,
        mentioned_count=len(mentioned_peers),
    )
    logger.debug("peer_domain_correction_names", mentioned_peers=list(mentioned_peers))
    peer_domain_correction_total.labels(primary_domain=corrected[0]).inc()
    return [*corrected, PEER_DOMAIN]
