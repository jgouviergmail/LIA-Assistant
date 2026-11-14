"""Atomically fence temporary Redis writes without holding SQL over network I/O.

Only a current SQL admission can activate or renew a grant. Redis first issues
a one-use ticket, SQL validates the admission, then Redis consumes that SAME
ticket. Closing revokes the ticket atomically. A missing/expired ticket never
authorizes activation, even when the server clock has moved backwards.
"""

import asyncio
from collections.abc import Awaitable
from typing import Protocol
from uuid import UUID, uuid4

from src.core.config import settings
from src.core.constants import (
    REDIS_KEY_HITL_PENDING_PREFIX,
    REDIS_KEY_RUNTIME_INVENTORY_PREFIX,
    REDIS_KEY_RUNTIME_WRITER_PREFIX,
)
from src.core.conversation_execution import ExecutionRevoked, RunAdmission
from src.core.conversation_target import ConversationRef
from src.core.run_authority import current_run_authority, require_runtime_authority
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.infrastructure.async_utils import finish_owned_task
from src.infrastructure.database.session import get_db_context


class RuntimeRedisClient(Protocol):
    """The atomic command door shared by Redis and the existing HITL client."""

    def eval(self, script: str, numkeys: int, /, *args: str) -> Awaitable[object]:
        """Execute one server-side command with explicitly supplied keys."""
        ...


_CLOCK = """
local function now_ms()
    local t = redis.call('TIME')
    return tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
end
"""
_FENCES = """
local function newer(a, b)
    if string.len(a) ~= string.len(b) then return string.len(a) > string.len(b) end
    return a > b
end
"""

# Fences remain decimal STRINGS: PostgreSQL bigint outgrows Lua's exact doubles.
ISSUE_RUNTIME = _CLOCK + _FENCES + """
local old = redis.call('HMGET', KEYS[1], 'token', 'fence', 'phase')
if old[2] then
    if newer(old[2], ARGV[2]) then return 0 end
    if old[2] == ARGV[2] and (old[1] ~= ARGV[1] or old[3] == 'closed') then return 0 end
end
local deadline = now_ms() + tonumber(ARGV[3])
if old[2] ~= ARGV[2] then
    redis.call('DEL', KEYS[1])
    redis.call('HSET', KEYS[1], 'token', ARGV[1], 'fence', ARGV[2], 'phase', 'pending')
end
redis.call('HSET', KEYS[1], 'ticket', ARGV[4], 'ticket_deadline', deadline)
redis.call('PEXPIRE', KEYS[1], ARGV[3])
return deadline
"""

OPEN_RUNTIME = _CLOCK + """
local pending = redis.call('HMGET', KEYS[1], 'token', 'fence', 'phase', 'ticket', 'ticket_deadline')
if pending[1] ~= ARGV[1] or pending[2] ~= ARGV[2] or pending[3] == 'closed' then return 0 end
if pending[4] ~= ARGV[5] or pending[5] ~= ARGV[3] then return 0 end
local deadline = tonumber(pending[5])
local now = now_ms()
if not deadline or deadline <= now then return 0 end
redis.call('HSET', KEYS[1], 'token', ARGV[1], 'fence', ARGV[2],
    'phase', 'active', 'deadline', ARGV[3])
redis.call('HDEL', KEYS[1], 'ticket', 'ticket_deadline')
redis.call('PEXPIRE', KEYS[1], math.max(1, deadline - now))
return 1
"""

CLOSE_RUNTIME = _FENCES + """
local old = redis.call('HMGET', KEYS[1], 'token', 'fence')
if old[2] then
    if newer(old[2], ARGV[2]) then return 0 end
    if old[2] == ARGV[2] and old[1] ~= ARGV[1] then return 0 end
end
redis.call('HSET', KEYS[1], 'token', ARGV[1], 'fence', ARGV[2], 'phase', 'closed')
redis.call('HDEL', KEYS[1], 'ticket', 'ticket_deadline')
redis.call('PEXPIRE', KEYS[1], ARGV[3])
return 1
"""

_REQUIRE_GRANT = _CLOCK + """
local grant = redis.call('HMGET', KEYS[1], 'token', 'fence', 'phase', 'deadline')
if grant[1] ~= ARGV[1] or grant[2] ~= ARGV[2] or grant[3] ~= 'active' then return 0 end
if not tonumber(grant[4]) or tonumber(grant[4]) <= now_ms() then return 0 end
local inventory_type = redis.call('TYPE', KEYS[2]).ok
if inventory_type ~= 'none' and inventory_type ~= 'set' then return -1 end
"""

_WRITE_STRING = _REQUIRE_GRANT + """
redis.call('SET', KEYS[3], ARGV[3], 'EX', ARGV[4])
redis.call('SADD', KEYS[2], KEYS[3])
local ttl = tonumber(ARGV[4]) * 1000
if redis.call('PTTL', KEYS[2]) < ttl then redis.call('PEXPIRE', KEYS[2], ttl) end
return 1
"""

_DELETE_STRING = _REQUIRE_GRANT + """
redis.call('DEL', KEYS[3])
redis.call('SREM', KEYS[2], KEYS[3])
return 1
"""


def runtime_writer_key(target: ConversationRef) -> str:
    """Name the runtime's authority, never the account-wide admission slot."""
    return f"{REDIS_KEY_RUNTIME_WRITER_PREFIX}{target.owner_id}:{target.runtime_id}"


def runtime_inventory_key(target: ConversationRef) -> str:
    """Name the exact runtime's temporary records, independent of other discussions."""
    return f"{REDIS_KEY_RUNTIME_INVENTORY_PREFIX}{target.owner_id}:{target.runtime_id}"


async def redis_time_ms(redis: RuntimeRedisClient) -> int:
    """Read Redis's clock; a host clock cannot establish the command's deadline."""
    value = await redis.eval(_CLOCK + "return now_ms()", 0)
    if type(value) is not int:
        raise ExecutionRevoked()
    return value


async def open_runtime_writes(redis: RuntimeRedisClient, admission: RunAdmission) -> None:
    """Issue, validate, activate; a missing ticket is never silently re-created."""
    try:
        await _activate(redis, admission)
    except Exception, asyncio.CancelledError:
        # A cancelled command may already have reached Redis. Revoke even if
        # the issuance/activation acknowledgement never reached this caller.
        await finish_owned_task(asyncio.create_task(close_runtime_writes(redis, admission)))
        raise


async def _activate(redis: RuntimeRedisClient, admission: RunAdmission) -> None:
    """Keep the SQL transaction strictly between the two Redis commands."""
    allowance_ms = settings.background_runs_active_ttl_seconds * 1000
    ticket = str(uuid4())
    deadline = await redis.eval(
        ISSUE_RUNTIME,
        1,
        runtime_writer_key(admission.target),
        str(admission.owner_token),
        str(admission.fence),
        str(allowance_ms),
        ticket,
    )
    if type(deadline) is not int or deadline <= 0:
        raise ExecutionRevoked()
    async with get_db_context() as db:
        await ConversationExecutionRepository(db).require_current(admission)
    result = await redis.eval(
        OPEN_RUNTIME,
        1,
        runtime_writer_key(admission.target),
        str(admission.owner_token),
        str(admission.fence),
        str(deadline),
        str(allowance_ms),
        ticket,
    )
    if result != 1:
        raise ExecutionRevoked()


async def close_runtime_writes(redis: RuntimeRedisClient, admission: RunAdmission) -> bool:
    """Revoke by owner, retaining a marker past every opening already in flight."""
    result = await redis.eval(
        CLOSE_RUNTIME,
        1,
        runtime_writer_key(admission.target),
        str(admission.owner_token),
        str(admission.fence),
        str(settings.background_runs_active_ttl_seconds * 1000),
    )
    return result == 1


async def write_runtime_string(
    redis: RuntimeRedisClient, runtime_id: UUID, *, key: str, value: str, ttl_seconds: int
) -> None:
    """Write and inventory one declared HITL record under the exact open invocation.

    Args:
        redis: The runtime's cache client.
        runtime_id: Explicit root runtime, never a business conversation id.
        key: A pending question belonging to that runtime.
        value: Already serialized content, never logged here.
        ttl_seconds: The existing record's configured lifetime.

    Raises:
        ExecutionRevoked: Missing, stale or closed graph/Redis authority.
        ValueError: An undeclared key shape or invalid record lifetime.
        RuntimeError: An inventory with the wrong Redis type; nothing was written.
    """
    authority = current_run_authority()
    if authority is None:
        raise ExecutionRevoked()
    target = authority.admission.target
    require_runtime_authority(target.owner_id, runtime_id)
    if (
        key != f"{REDIS_KEY_HITL_PENDING_PREFIX}{runtime_id}"
        or type(ttl_seconds) is not int
        or ttl_seconds <= 0
    ):
        raise ValueError("Invalid conversation runtime record")
    result = await redis.eval(
        _WRITE_STRING,
        3,
        runtime_writer_key(target),
        runtime_inventory_key(target),
        key,
        str(authority.admission.owner_token),
        str(authority.admission.fence),
        value,
        str(ttl_seconds),
    )
    if result == -1:
        raise RuntimeError("Conversation runtime inventory has an invalid type")
    if result != 1:
        raise ExecutionRevoked()


async def delete_runtime_question(redis: RuntimeRedisClient, runtime_id: UUID) -> None:
    """An admitted continuation may consume its predecessor's question, atomically."""
    authority = current_run_authority()
    if authority is None:
        raise ExecutionRevoked()
    target = authority.admission.target
    require_runtime_authority(target.owner_id, runtime_id)
    result = await redis.eval(
        _DELETE_STRING,
        3,
        runtime_writer_key(target),
        runtime_inventory_key(target),
        f"{REDIS_KEY_HITL_PENDING_PREFIX}{runtime_id}",
        str(authority.admission.owner_token),
        str(authority.admission.fence),
    )
    if result != 1:
        raise ExecutionRevoked()


async def run_runtime_mutation(
    redis: RuntimeRedisClient,
    *,
    owner_id: UUID,
    runtime_id: UUID,
    script: str,
    keys: tuple[str, ...],
    args: tuple[str, ...],
) -> object:
    """Apply a declared multi-key mutation under the same grant as HITL writes.

    Keys 1/2 are the authority/inventory and arguments 1/2 the private fence;
    the caller's keys/arguments follow. A body result is enveloped so zero is
    a legitimate mutation result, never confused with refused authority.
    The caller inventories only runtime-owned records, never shared indexes.
    """
    authority = require_runtime_authority(owner_id, runtime_id)
    result = await redis.eval(
        _REQUIRE_GRANT + "\nlocal function mutate()\n" + script + "\nend\nreturn {1, mutate()}",
        len(keys) + 2,
        runtime_writer_key(authority.admission.target),
        runtime_inventory_key(authority.admission.target),
        *keys,
        str(authority.admission.owner_token),
        str(authority.admission.fence),
        *args,
    )
    if result == -1:
        raise RuntimeError("Conversation runtime inventory has an invalid type")
    if not isinstance(result, list) or len(result) != 2 or result[0] != 1:
        raise ExecutionRevoked()
    return result[1]
