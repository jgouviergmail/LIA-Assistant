"""Bound the pure authority to native live policy and Redis transactions."""

import secrets
from dataclasses import dataclass

from src.core.constants import WORLD_PRESENCE_LEASE_SECONDS
from src.domains.world.authority import Identity
from src.domains.world.configuration import (
    configured_arcade_enabled,
    configured_authority,
    configured_game_limits,
)
from src.domains.world.emotes import apply_emote, emote_refusal, refuse_emote
from src.domains.world.game_commands import GameCommand
from src.domains.world.game_lifecycle import prune_games
from src.domains.world.game_projection import project_games
from src.domains.world.game_reconciliation import reconcile_game_policy
from src.domains.world.policy import WorldPolicy, commit_admission, read_policy
from src.domains.world.poses import apply_pose
from src.domains.world.presence import drop_presence, renew_presence, track_actor_presence
from src.domains.world.schemas import (
    ControlCommand,
    HeartbeatCommand,
    MoveCommand,
    PoseCommand,
    WorldCommand,
    WorldState,
    WorldView,
)
from src.domains.world.socket_models import EmoteCommand
from src.domains.world.store import WorldStore


@dataclass(frozen=True)
class WorldConnection:
    identity: Identity
    controller: str


class WorldService:
    def __init__(self, store: WorldStore) -> None:
        """Combine configured pure authority with a scene-scoped Redis store."""
        self.store, self.authority = store, configured_authority()

    async def enter(self, identity: Identity, resume: str | None) -> WorldConnection:
        """Commit account-locked admission, optionally rotating a valid resumed controller.

        Args:
            identity: The authenticated World identity.
            resume: The previous controller the socket asks to resume, if any.

        Returns:
            The connection, holding a fresh controller generation.
        """
        controller = secrets.token_urlsafe(32)

        def apply(state: WorldState, now: float) -> None:
            """Apply this service operation to a watched snapshot; CAS conflicts may replay this pure mutation."""
            self.authority.prune(state, now)
            self._prune_games(state, now)
            idle = state.presences.get(identity.account_id)
            if (
                resume
                and identity.account_id not in state.actors
                and idle is not None
                and idle.controller == resume
                and idle.binding == identity.binding
            ):
                idle.controller = controller
                idle.expires_at = now + WORLD_PRESENCE_LEASE_SECONDS
                return
            if resume:
                self.authority.resume(state, identity, resume, controller, now)
            self.authority.join(state, identity, controller, now)

        await commit_admission(identity.account_id, self.store, apply)
        return WorldConnection(identity, controller)

    async def command(self, connection: WorldConnection, command: WorldCommand) -> None:
        """Apply one validated command under the current epoch and authoritative transaction fence.

        Args:
            connection: The commanding socket's identity and controller.
            command: The validated non-game command.

        Raises:
            ValueError: A game command, which needs the session-bound game door.
        """
        if isinstance(command, GameCommand):
            raise ValueError("game_requires_session_policy")
        account, controller = connection.identity.account_id, connection.controller

        def apply(state: WorldState, now: float) -> None:
            """Apply this service operation to a watched snapshot; CAS conflicts may replay this pure mutation."""
            self.authority.prune(state, now)
            if command.epoch != state.epoch:
                return
            if isinstance(command, MoveCommand):
                self.authority.move(
                    state,
                    account,
                    controller,
                    command.seq,
                    command.dx,
                    command.dy,
                    now,
                    running=command.running,
                )
            elif isinstance(command, PoseCommand):
                apply_pose(state, account, controller, command.seq, command.slot, now)
            elif isinstance(command, EmoteCommand):
                apply_emote(state, account, controller, command.seq, command.emote, now)
            elif isinstance(command, HeartbeatCommand):
                self.authority.heartbeat(
                    state,
                    account,
                    controller,
                    now,
                    visible=command.visible,
                    active=command.active,
                )
                self._queue_heartbeat(state, account, controller, command.visible, now)
            elif isinstance(command, ControlCommand):
                self._control(state, connection, command, now)
            self._settle_command(state, account, controller, now)

        if isinstance(command, ControlCommand) and command.type == "accept":
            await commit_admission(account, self.store, apply)
        else:
            await self.store.update(apply)

    async def refuse_emote(self, connection: WorldConnection, command: EmoteCommand) -> bool:
        """Settle a gesture that cannot be published, without reading native policy.

        A cooldown or visibility refusal publishes nothing, so it needs no fresh
        policy: one read predicts it, and the commit decides it again — a gesture
        that became publishable in between is left untouched for the policy path.

        Args:
            connection: The sending socket's identity and controller.
            command: The validated gesture.

        Returns:
            True when the refusal was committed under the gesture's sequence;
            False when the gesture may be published (or is inert) and must take
            the policy-checked path.
        """
        account, controller = connection.identity.account_id, connection.controller
        state, now = await self.store.read()
        self.authority.prune(state, now)
        if command.epoch != state.epoch or (
            emote_refusal(state, account, controller, command.seq, now) is None
        ):
            return False

        def apply(current: WorldState, now: float) -> bool:
            """Record the refusal only if the watched snapshot still refuses the gesture."""
            self.authority.prune(current, now)
            if command.epoch != current.epoch or not refuse_emote(
                current, account, controller, command.seq, now
            ):
                return False
            self._settle_command(current, account, controller, now)
            return True

        _, refused = await self.store.update(apply)
        return refused

    def _settle_command(self, state: WorldState, account: str, controller: str, now: float) -> None:
        """Every accepted socket command renews presence and settles game deadlines."""
        track_actor_presence(state, account, controller, now)
        renew_presence(state, account, controller, now)
        self._prune_games(state, now)

    def _queue_heartbeat(
        self,
        state: WorldState,
        account: str,
        controller: str,
        visible: bool,
        now: float,
    ) -> None:
        """Renew only a visible waiter's current controller lease."""
        if account in state.actors or not visible:
            return
        for waiter in state.queue:
            if waiter.account_id == account and waiter.controller == controller:
                waiter.expires_at = now + self.authority.limits.queue_seconds

    def _control(
        self,
        state: WorldState,
        connection: WorldConnection,
        command: ControlCommand,
        now: float,
    ) -> None:
        """Apply explicit leave, offered entry or controller takeover without changing account ownership."""
        identity, controller = connection.identity, connection.controller
        if command.type == "leave":
            self.authority.leave(state, identity.account_id, controller)
        elif command.type == "accept":
            self.authority.join(state, identity, controller, now)
        elif command.type == "takeover":
            actor = state.actors.get(identity.account_id)
            if actor is not None:
                self.authority.takeover(state, identity.account_id, controller, now)
                actor.binding = identity.binding
            for waiter in state.queue:
                if waiter.account_id == identity.account_id:
                    waiter.controller, waiter.binding = controller, identity.binding
                    waiter.expires_at = now + self.authority.limits.queue_seconds

    async def policy(self, cookie: str, connection: WorldConnection) -> WorldPolicy:
        """Refresh native policy, remove revoked accounts and reconcile the owner's public identity."""
        state, _ = await self.store.read()
        observed = (
            set(state.actors) | set(state.presences) | {waiter.account_id for waiter in state.queue}
        )
        for table in state.games.values():
            observed.update(member.account for member in table.members)
            if table.pending is not None:
                observed.add(table.pending.account)
        policy = await read_policy(cookie, connection.identity.account_id, observed)
        invalid = observed - policy.eligible

        def reconcile(current: WorldState, now: float) -> None:
            """Remove ineligible accounts and refresh the owner's nonstale public appearance."""
            for key in invalid:
                current.actors.pop(key, None)
                current.presences.pop(key, None)
            current.queue = [waiter for waiter in current.queue if waiter.account_id not in invalid]
            own = current.actors.get(connection.identity.account_id)
            if own is not None:
                own.language = policy.language
                if policy.public_identity is not None:
                    own.alias = policy.public_identity.name
                    if policy.public_identity.revision >= own.appearance_revision:
                        own.appearance = policy.public_identity.appearance
                        own.appearance_revision = policy.public_identity.revision
            self.authority.prune(current, now)
            reconcile_game_policy(
                current,
                connection.identity.account_id,
                policy,
                observed,
                now,
                configured_game_limits(),
            )
            self._prune_games(current, now)

        await self.store.update(reconcile)
        return policy

    async def disconnect(self, connection: WorldConnection) -> None:
        """Withdraw live peer presence while preserving the actor's bounded reconnect grace."""

        def withdraw(state: WorldState, now: float) -> None:
            """Persist the first disconnect timestamp once, never when a view happens to read it."""
            drop_presence(state, connection.identity.account_id, connection.controller)
            self._prune_games(state, now)

        await self.store.update(withdraw)

    async def revoke(self, connection: WorldConnection) -> None:
        """Explicit native revocation releases only this controller and withdraws its games atomically."""

        def withdraw(state: WorldState, now: float) -> None:
            """A stale cookie cannot evict a successor; missing admissions end games without a winner."""
            self.authority.leave(state, connection.identity.account_id, connection.controller)
            self._prune_games(state, now)

        await self.store.update(withdraw)

    @staticmethod
    def _prune_games(state: WorldState, now: float) -> bool:
        """The child flag withdraws all games without affecting World admission."""
        if not configured_arcade_enabled():
            changed = bool(state.games)
            state.games.clear()
            return changed
        return prune_games(state, now, configured_game_limits())

    def _settle_deadlines(self, state: WorldState, now: float) -> bool:
        """Apply the actor and game deadlines a projection must not show as live; report game changes."""
        self.authority.prune(state, now)
        return self._prune_games(state, now)

    async def view(self, connection: WorldConnection, policy: WorldPolicy) -> WorldView:
        """Project current authoritative state through this viewer's eligibility and blocking policy.

        Args:
            connection: The viewing socket's identity and controller.
            policy: The viewer's fresh eligibility and block policy.

        Returns:
            The viewer-filtered snapshot, with games only while the arcade is enabled.
        """
        state, now = await self.store.read()
        if self._settle_deadlines(state, now):
            await self.store.update(self._prune_games)
            # Re-anchor from Redis after committing a real deadline transition,
            # and project the re-read through the same deadlines as the first.
            state, now = await self.store.read()
            self._settle_deadlines(state, now)
        state.actors = {key: actor for key, actor in state.actors.items() if key in policy.eligible}
        view = self.authority.project(
            state,
            connection.identity.account_id,
            set(policy.blocked),
            now,
            connection.controller,
        )
        if configured_arcade_enabled():
            view.cabinets, view.game, view.game_request = project_games(
                state, connection.identity.account_id, connection.controller, policy, now
            )
        return view
