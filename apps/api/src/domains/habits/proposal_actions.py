"""What accepting a proposal DOES — one handler per kind, held complete at boot (ADR-375).

The registry is keyed by ``ProposalKind`` and checked complete when the
application starts (ADR-085): a kind added without its handler refuses to boot
rather than answering « accepted » to a click that did nothing.

Habits owns the handlers that touch routines (``proposal_handlers``);
``heartbeat`` owns the two that change its own preferences and INSTALLS them,
because it imports habits and habits importing it back would close a cycle —
the ``usage_ports`` doctrine. The boot imports both owners explicitly before
asserting (an already-imported module wires nothing, ADR-270).

A handler runs INSIDE the decision's transaction, after the proposal is
claimed. When it cannot act on what the person was shown — the routine cap
reached, the routine gone or changed, the settings changed — it raises
``ProposalActionRefused`` with a stable reason: the caller rolls the claim back,
the proposal stays open, and the card says why in the person's language.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.habits.models import HabitProposal, ProposalKind
from src.domains.users.models import User


class ProposalRefusal(StrEnum):
    """Why an accepted proposal could not be carried out — translated by the card."""

    ROUTINE_LIMIT = "routine_limit"
    ROUTINE_GONE = "routine_gone"
    ROUTINE_CHANGED = "routine_changed"
    SETTINGS_CHANGED = "settings_changed"


class ProposalActionRefused(Exception):
    """A handler could not act on what the person was shown."""

    def __init__(self, reason: ProposalRefusal) -> None:
        """Name the refusal.

        Args:
            reason: The stable reason the card translates.
        """
        super().__init__(reason.value)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ProposalActionResult:
    """What an act left behind, for the card to point at.

    Attributes:
        routine_id: The routine created, moved or to be opened, when there is one.
    """

    routine_id: UUID | None = None


class ProposalAction(Protocol):
    """Carry out one accepted proposal inside the caller's transaction."""

    async def __call__(
        self, db: AsyncSession, user: User, proposal: HabitProposal
    ) -> ProposalActionResult:
        """Act on the proposal's facts.

        Args:
            db: The decision's session; the caller commits or rolls back.
            user: The person accepting.
            proposal: The claimed proposal (status ``accepted``).

        Returns:
            What the act left behind.

        Raises:
            ProposalActionRefused: When the act no longer matches what was shown.
        """
        ...


_ACTIONS: dict[ProposalKind, ProposalAction] = {}


def install_proposal_action(kind: ProposalKind, action: ProposalAction) -> None:
    """Register the handler of one kind (its owner calls this at import).

    Args:
        kind: The kind it carries out.
        action: The handler.
    """
    _ACTIONS[kind] = action


def proposal_action(kind: ProposalKind) -> ProposalAction:
    """The handler of a kind — complete by the boot assertion.

    Args:
        kind: The proposal's kind.

    Returns:
        Its handler.
    """
    return _ACTIONS[kind]


def installed_proposal_actions() -> Mapping[ProposalKind, ProposalAction]:
    """Every installed handler (read-only view, for the boot assertion and tests)."""
    return dict(_ACTIONS)


def assert_proposal_actions_complete() -> None:
    """Refuse to boot with a kind nobody can carry out (ADR-085).

    Raises:
        AssertionError: Naming each kind without a handler (raised, never
            ``assert``-ed: an optimised interpreter strips assertions).
    """
    missing = sorted(kind.value for kind in ProposalKind if kind not in _ACTIONS)
    if missing:
        raise AssertionError(f"habit proposal kinds without an action: {missing}")
