"""Pure bounded social gestures; no free text, provider calls or business dispatch.

A gesture is refused (hidden sender, private home, exhausted serial, cooldown) or
published. A refusal publishes nothing, so ``refuse_emote`` can settle it before
the socket reads native policy; only a gesture that may be published needs it.
"""

from typing import Literal

from src.core.constants import WORLD_EMOTE_SECONDS, WORLD_RECEIPT_RING_SIZE
from src.domains.world.collision import private_home
from src.domains.world.schemas import ActorState, WorldState
from src.domains.world.socket_models import CommandReceipt, EmoteKind, EmoteReceipt, EmoteState

EmoteRefusal = Literal["unavailable", "rate_limited"]


def record_receipt(actor: ActorState, receipt: CommandReceipt) -> None:
    """Keep exact owner outcomes even when a later command arrives before a snapshot.

    Args:
        actor: The commanding actor whose bounded ring receives the receipt.
        receipt: The command's exact outcome.
    """
    actor.receipts = [*actor.receipts[-(WORLD_RECEIPT_RING_SIZE - 1) :], receipt]


def _fresh_sender(
    state: WorldState, account: str, controller: str, seq: int, now: float
) -> ActorState | None:
    """The sender's actor when this controller's sequence is fresh and its admission live."""
    actor = state.actors.get(account)
    if (
        actor is None
        or actor.controller != controller
        or seq <= actor.seq
        or actor.expires_at <= now
    ):
        return None
    return actor


def _refusal(actor: ActorState, now: float) -> EmoteRefusal | None:
    """Visibility refusals take precedence over the takeover-proof cooldown."""
    if not actor.visible or private_home(actor.position) or actor.emote_serial == 2**31 - 1:
        return "unavailable"
    if now < actor.emote_after:
        return "rate_limited"
    return None


def _record_refusal(actor: ActorState, seq: int, now: float) -> bool:
    """Consume the sequence and record the refusal, or leave a publishable gesture untouched."""
    refusal = _refusal(actor, now)
    if refusal is None:
        return False
    actor.seq = seq
    record_receipt(actor, EmoteReceipt(seq=seq, result=refusal))
    return True


def emote_refusal(
    state: WorldState, account: str, controller: str, seq: int, now: float
) -> EmoteRefusal | None:
    """Predict, without mutating anything, the refusal a fresh gesture would receive.

    Args:
        state: Observed authority.
        account: Sending account.
        controller: Sending controller generation.
        seq: The gesture's controller sequence.
        now: Redis Unix time of the observation.

    Returns:
        ``unavailable`` or ``rate_limited``; None when the gesture may be
        published, or when a stale controller or sequence makes it inert.
    """
    actor = _fresh_sender(state, account, controller, seq, now)
    return None if actor is None else _refusal(actor, now)


def refuse_emote(state: WorldState, account: str, controller: str, seq: int, now: float) -> bool:
    """Settle a refused gesture under its sequence, publishing nothing.

    Args:
        state: Watched authority snapshot.
        account: Sending account.
        controller: Sending controller generation.
        seq: The gesture's controller sequence.
        now: Redis Unix time of the commit.

    Returns:
        True when a refusal was recorded; False leaves a publishable (or inert)
        gesture untouched for the policy-checked path.
    """
    actor = _fresh_sender(state, account, controller, seq, now)
    return actor is not None and _record_refusal(actor, seq, now)


def apply_emote(
    state: WorldState, account: str, controller: str, seq: int, emote: EmoteKind, now: float
) -> bool:
    """Consume a fresh controller sequence, enforcing visibility and a takeover-proof cooldown.

    Args:
        state: Watched authority snapshot.
        account: Sending account.
        controller: Sending controller generation.
        seq: The gesture's controller sequence.
        emote: One gesture of the closed public catalogue.
        now: Redis Unix time of the commit.

    Returns:
        True when the gesture was published; a refusal is recorded as a receipt.
    """
    actor = _fresh_sender(state, account, controller, seq, now)
    if actor is None or _record_refusal(actor, seq, now):
        return False
    actor.seq = seq
    actor.emote_serial += 1
    actor.emote_after = now + WORLD_EMOTE_SECONDS
    actor.emote = EmoteState(emote=emote, serial=actor.emote_serial, expires_at=actor.emote_after)
    actor.activity_at = now
    record_receipt(actor, EmoteReceipt(seq=seq, result="accepted"))
    return True
