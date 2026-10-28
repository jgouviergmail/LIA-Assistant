"""Redis is the one serial authority, with bounded optimistic transactions.

There is no process-local fallback or background worker simulator to elect.
Every committed movement has the actor controller fence and epoch of this state.
Cancellation after EXEC may lose an acknowledgment, never the sequence fence.

Reading and publishing fail differently on purpose. A stored record the strict
reader refuses raises the reader's ``ValidationError``: account erasure relies on
it to try the declared older generations. A record a transition PRODUCED that the
strict reader refuses is a server defect: it raises ``WorldIntegrityError``, is
logged by its rule code and counted, and is never published.
"""

import asyncio
import hashlib
import re
from collections.abc import Callable

import structlog
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from redis.exceptions import WatchError

from src.core.constants import (
    REDIS_KEY_WORLD_RUNTIME_PREFIX,
    WORLD_AUTHORITY_TIMEOUT_DEFAULT,
)
from src.domains.world.collision import SCENE
from src.domains.world.schemas import WorldState, WorldStateShape
from src.infrastructure.observability.metrics_world import world_authority_integrity_failures_total

MAX_STATE_BYTES = 128 * 1024
MAX_CAS_ATTEMPTS = 16
# An authored validator code (``game_members``); any other refusal text is
# reported by its Pydantic error type, so no input value ever reaches a log line.
_RULE_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}")
_VALUE_ERROR_PREFIX = "Value error, "
logger = structlog.get_logger(__name__)


class WorldUnavailable(RuntimeError):
    """The shared authority cannot establish an outcome; re-read, never simulate locally."""

    @property
    def code(self) -> str:
        """The authored refusal code this failure was raised with."""
        return str(self.args[0]) if self.args else "world_unavailable"


class WorldIntegrityError(RuntimeError):
    """A transition produced a record the strict reader refuses: a defect, never published."""

    def __init__(self, code: str, area: str) -> None:
        """Carry only the refused rule and the record area, never an input value.

        Args:
            code: Authored validator code, or the Pydantic error type of the refusal.
            area: Top-level authority field holding the refused value, or ``record``.
        """
        super().__init__(code)
        self.code = code
        self.area = area


def decode_authority_state[State: BaseModel](raw: str | bytes | None, model: type[State]) -> State:
    """Apply the same byte ceiling before validating a current or legacy authority generation.

    Args:
        raw: Stored authority document, or None when the key does not exist.
        model: Strict generation reader.

    Returns:
        The decoded generation; a missing key starts a fresh one.

    Raises:
        WorldUnavailable: The document exceeds the authority byte ceiling.
        ValidationError: The document is not a valid record of this generation.
    """
    if raw is None:
        return model()
    if len(raw) > MAX_STATE_BYTES:
        raise WorldUnavailable("world_state_limit")
    size = len(raw.encode("utf-8")) if isinstance(raw, str) else len(raw)
    if size > MAX_STATE_BYTES:
        raise WorldUnavailable("world_state_limit")
    return model.model_validate_json(raw)


def _integrity_failure(error: ValidationError, fields: frozenset[str]) -> WorldIntegrityError:
    """Name, log and count a refused post-transition record without quoting any value.

    Args:
        error: The strict reader's refusal of the record a transition produced.
        fields: The generation's declared top-level fields, bounding the area label.

    Returns:
        The integrity failure the store raises in place of the validation error.
    """
    details = error.errors(include_url=False, include_context=False, include_input=False)
    first = details[0] if details else None
    code, area = "unknown", "record"
    if first is not None:
        message = first["msg"].removeprefix(_VALUE_ERROR_PREFIX)
        authored = first["type"] == "value_error" and _RULE_CODE.fullmatch(message) is not None
        code = message if authored else first["type"]
        location = first["loc"][0] if first["loc"] else None
        area = location if isinstance(location, str) and location in fields else "record"
    logger.error("world_authority_integrity_failed", error_code=code, area=area)
    world_authority_integrity_failures_total.labels(area=area).inc()
    return WorldIntegrityError(code, area)


class AuthorityStore[State: WorldStateShape]:
    def __init__(
        self,
        redis: Redis,
        *,
        namespace: str,
        ttl: int,
        timeout: float = WORLD_AUTHORITY_TIMEOUT_DEFAULT,
        scene: str | None = SCENE,
    ) -> None:
        """Bind Redis authority and message fencing to the full instance/scene identity."""
        self.redis = redis
        # Only lifecycle cleanup selects an older scene; admission uses SCENE.
        suffix = f":{scene}" if scene is not None else ""
        self.key = f"{REDIS_KEY_WORLD_RUNTIME_PREFIX}{namespace}{suffix}"
        # Preserve the full instance AND scene identity in Redis content and
        # SQL spend fences; a trailing scene version alone is not a namespace.
        # The durable namespace column admits forty characters.
        self.message_namespace = hashlib.sha256(self.key.encode("utf-8")).hexdigest()[:40]
        self.ttl = ttl
        self.timeout = timeout

    @staticmethod
    def decode(raw: str | bytes | None) -> State:
        """Require a generation-specific strict reader at the persistence boundary."""
        raise NotImplementedError

    @staticmethod
    def encode(state: State) -> str:
        """Serialize a current authority; legacy erasure overrides its field-set policy."""
        return state.model_dump_json()

    async def read(self) -> tuple[State, float]:
        """Read authoritative state and Redis wall-clock time under the configured I/O deadline.

        Returns:
            The decoded record and the Redis Unix time of the read.

        Raises:
            WorldUnavailable: The stored record exceeds the authority byte ceiling.
            ValidationError: The stored record is not a record of this generation.
            TimeoutError: The authority deadline expires.
        """
        async with asyncio.timeout(self.timeout):
            seconds, micros = await self.redis.time()
            return (
                self.decode(await self.redis.get(self.key)),
                float(seconds) + float(micros) / 1e6,
            )

    async def update[R](self, transition: Callable[[State, float], R]) -> tuple[State, R]:
        """Commit a pure transition under a bounded optimistic transaction.

        Args:
            transition: In-place snapshot mutation receiving Redis Unix seconds.
                It may run again after contention, so it must have no external effects.

        Returns:
            Committed state and the result of its accepted transition invocation.

        Raises:
            WorldUnavailable: The published record would exceed the byte ceiling,
                or contention exhausted the bounded attempts.
            ValidationError: The STORED record is not a record of this generation;
                lifecycle erasure tries the declared older generations on it.
            WorldIntegrityError: The transition produced a record the strict reader
                refuses — a server defect; nothing is published.
            TimeoutError: The overall authority deadline expires. Re-read before retrying
                a business operation: cancellation can lose an already committed ack.
        """
        async with asyncio.timeout(self.timeout):
            return await self._update(transition)

    async def _update[R](self, transition: Callable[[State, float], R]) -> tuple[State, R]:
        """Watch authority, run the transition and atomically publish its incremented revision and TTL."""
        for _ in range(MAX_CAS_ATTEMPTS):
            try:
                async with self.redis.pipeline(transaction=True) as pipe:
                    await pipe.watch(self.key)
                    state = self.decode(await pipe.get(self.key))
                    seconds, micros = await self.redis.time()
                    result = transition(state, float(seconds) + float(micros) / 1e6)
                    state.revision += 1
                    serialized = self.encode(state)
                    if len(serialized.encode("utf-8")) > MAX_STATE_BYTES:
                        raise WorldUnavailable("world_state_limit")
                    # Validate the complete post-transition record once, before
                    # publishing. Intermediate mutable assignments need not be
                    # individually valid, but a committed authority always is.
                    try:
                        self.decode(serialized)
                    except ValidationError as error:
                        # ``from None``: the refusal quotes the record's values.
                        raise _integrity_failure(
                            error, frozenset(type(state).model_fields)
                        ) from None
                    pipe.multi()
                    pipe.set(self.key, serialized, ex=self.ttl)
                    await pipe.execute()
                    return state, result
            except WatchError:
                continue
        raise WorldUnavailable("world_contention")


class WorldStore(AuthorityStore[WorldState]):
    """Current admission authority; older generations are only available to erasure."""

    @staticmethod
    def decode(raw: str | bytes | None) -> WorldState:
        """Decode strict bounded state; only a missing key creates a new epoch."""
        return decode_authority_state(raw, WorldState)
