"""Pure transitions. Redis serializes commits; API workers never own simulations."""

import math
from dataclasses import dataclass, field

from src.core.constants import (
    WORLD_CAPACITY_DEFAULT,
    WORLD_IDLE_SECONDS_DEFAULT,
    WORLD_LEASE_SECONDS_DEFAULT,
    WORLD_OFFER_SECONDS_DEFAULT,
    WORLD_QUEUE_SECONDS_DEFAULT,
    WORLD_QUEUE_SIZE_DEFAULT,
)
from src.domains.world.avatar import AvatarAppearance
from src.domains.world.collision import WORLD, arrival, move, private_home
from src.domains.world.poses import stand
from src.domains.world.presence import drop_presence, prune_presences, track_actor_presence
from src.domains.world.schemas import (
    ActorState,
    PublicActor,
    Waiter,
    WorldState,
    WorldView,
)


@dataclass(frozen=True)
class Identity:
    account_id: str
    alias: str
    language: str
    binding: str = ""
    appearance: AvatarAppearance = field(default_factory=AvatarAppearance)
    appearance_revision: int = 0


@dataclass(frozen=True)
class Limits:
    capacity: int = WORLD_CAPACITY_DEFAULT
    queue_size: int = WORLD_QUEUE_SIZE_DEFAULT
    lease_seconds: float = WORLD_LEASE_SECONDS_DEFAULT
    queue_seconds: float = WORLD_QUEUE_SECONDS_DEFAULT
    offer_seconds: float = WORLD_OFFER_SECONDS_DEFAULT
    idle_seconds: float = WORLD_IDLE_SECONDS_DEFAULT


class Authority:
    def __init__(self, limits: Limits) -> None:
        """Bind the pure authority to the configured admission and lease limits."""
        self.limits = limits

    def prune(self, state: WorldState, now: float) -> None:
        """Expire inactive actors and waiters, then offer free capacity in FIFO order."""
        prune_presences(state, now)
        state.actors = {
            key: actor
            for key, actor in state.actors.items()
            if actor.expires_at > now and actor.activity_at + self.limits.idle_seconds > now
        }
        state.queue = [
            waiter
            for waiter in state.queue
            if waiter.expires_at > now
            and (waiter.offered_until is None or waiter.offered_until > now)
        ]
        free = max(0, self.limits.capacity - len(state.actors))
        for index, waiter in enumerate(state.queue):
            if index < free and waiter.offered_until is None:
                waiter.offered_until = now + self.limits.offer_seconds

    def join(self, state: WorldState, identity: Identity, controller: str, now: float) -> None:
        """Admit one account or renew its own queued controller without bypassing FIFO offers."""
        self.prune(state, now)
        if identity.account_id in state.actors:
            return
        waiter = next((w for w in state.queue if w.account_id == identity.account_id), None)
        if self._can_enter(state, waiter, controller):
            state.queue = [w for w in state.queue if w.account_id != identity.account_id]
            state.actors[identity.account_id] = ActorState(
                account_id=identity.account_id,
                alias=identity.alias,
                appearance=identity.appearance,
                appearance_revision=identity.appearance_revision,
                language=identity.language,
                controller=controller,
                binding=identity.binding,
                position=arrival(actor.position for actor in state.actors.values()),
                moved_at=now,
                expires_at=now + self.limits.lease_seconds,
                activity_at=now,
            )
            track_actor_presence(state, identity.account_id, controller, now)
        elif waiter is not None and waiter.controller == controller:
            waiter.expires_at = now + self.limits.queue_seconds
        elif waiter is None and len(state.queue) < self.limits.queue_size:
            state.queue.append(
                Waiter(
                    account_id=identity.account_id,
                    controller=controller,
                    binding=identity.binding,
                    expires_at=now + self.limits.queue_seconds,
                )
            )

    def _can_enter(self, state: WorldState, waiter: Waiter | None, controller: str) -> bool:
        """Check free capacity and the controlling tab's existing queue offer."""
        return len(state.actors) < self.limits.capacity and (
            not state.queue
            or (
                waiter is not None
                and waiter.controller == controller
                and waiter.offered_until is not None
            )
        )

    def takeover(self, state: WorldState, account: str, controller: str, now: float) -> None:
        """Rotate an admitted account's controller and reset its movement sequence."""
        actor = state.actors.get(account)
        if actor is not None:
            actor.controller, actor.seq, actor.moved_at = controller, 0, now
            actor.expires_at = now + self.limits.lease_seconds
            actor.activity_at = now
            track_actor_presence(state, account, controller, now)

    @staticmethod
    def leave(state: WorldState, account: str, controller: str) -> None:
        """Release only this controller's actor or queue entry; stale tabs cannot evict successors."""
        drop_presence(state, account, controller)
        actor = state.actors.get(account)
        if actor is not None and actor.controller == controller:
            del state.actors[account]
        state.queue = [
            w for w in state.queue if w.account_id != account or w.controller != controller
        ]

    def resume(
        self,
        state: WorldState,
        identity: Identity,
        previous: str,
        controller: str,
        now: float,
    ) -> bool:
        """Transfer an actor or waiter only when the previous controller and cookie binding match."""
        actor = state.actors.get(identity.account_id)
        if actor is not None and actor.controller == previous and actor.binding == identity.binding:
            activity_at = actor.activity_at
            self.takeover(state, identity.account_id, controller, now)
            # Transport recovery is not a human action; only explicit takeover
            # or a subsequent activity command resets the idle deadline.
            actor.activity_at = activity_at
            track_actor_presence(state, identity.account_id, controller, now)
            return True
        for waiter in state.queue:
            if (
                waiter.account_id == identity.account_id
                and waiter.controller == previous
                and waiter.binding == identity.binding
            ):
                waiter.controller = controller
                waiter.expires_at = now + self.limits.queue_seconds
                return True
        return False

    def heartbeat(
        self,
        state: WorldState,
        account: str,
        controller: str,
        now: float,
        *,
        visible: bool,
        active: bool,
    ) -> None:
        """Renew visibility and activity leases only for the actor's current controller."""
        actor = state.actors.get(account)
        if actor is None or actor.controller != controller:
            return
        if visible:
            actor.expires_at = now + self.limits.lease_seconds
        if active:
            actor.activity_at = now

    def move(
        self,
        state: WorldState,
        account: str,
        controller: str,
        seq: int,
        dx: float,
        dy: float,
        now: float,
        *,
        running: bool = False,
    ) -> bool:
        """Apply a fresh sequence with bounded elapsed time, normalized speed and authoritative collision."""
        actor = state.actors.get(account)
        if actor is None or actor.controller != controller or seq <= actor.seq:
            return False
        if (
            actor.expires_at <= now
            or actor.activity_at + self.limits.idle_seconds <= now
            or not math.isfinite(dx + dy)
        ):
            return False
        if not stand(actor):
            return False
        actor.pose_result = None
        dt = max(0.0, min(0.1, now - actor.moved_at))
        length = math.hypot(dx, dy)
        speed = WORLD.movement.run if running else WORLD.movement.walk
        scale = speed * dt / max(1, length)
        before = actor.position
        actor.position = move(before, dx * scale, dy * scale)
        mx, my = actor.position["x"] - before["x"], actor.position["y"] - before["y"]
        actor.walking = math.hypot(mx, my) > 0.0001
        if actor.walking:
            actor.facing = (
                (0 if mx > 0 else 2) if abs(mx) > abs(my) + 1e-9 else (1 if my > 0 else 3)
            )
            actor.activity_at = now
        actor.seq, actor.moved_at = seq, now
        return True

    @staticmethod
    def public_actor(actor: ActorState, now: float) -> PublicActor:
        """Project public appearance and stop stale walking animation without exposing account fences."""
        return PublicActor(
            appearance=actor.appearance,
            pose=actor.pose,
            id=actor.public_id,
            alias=actor.alias,
            position=actor.position.copy(),
            facing=actor.facing,
            walking=actor.walking and now - actor.moved_at < 0.25,
        )

    def project(
        self,
        state: WorldState,
        account: str,
        blocked: set[str],
        now: float,
        controller: str = "",
    ) -> WorldView:
        """Build the requesting account's snapshot, omitting blocked people and private-home occupants."""
        view = WorldView(epoch=state.epoch, revision=state.revision, status="absent")
        own = state.actors.get(account)
        if own is None:
            for index, waiter in enumerate(state.queue):
                if waiter.account_id == account:
                    view.controlling = waiter.controller == controller
                    view.status, view.position, view.offer_until = (
                        "waiting",
                        index + 1,
                        waiter.offered_until,
                    )
            return view
        view.status, view.you, view.ack = "active", self.public_actor(own, now), own.seq
        view.pose_result = own.pose_result
        view.controlling = own.controller == controller
        view.idle_until = own.activity_at + self.limits.idle_seconds
        view.actors = [
            self.public_actor(a, now)
            for key, a in state.actors.items()
            if key != account
            and key not in blocked
            and a.expires_at > now
            and not private_home(a.position)
        ]
        return view
