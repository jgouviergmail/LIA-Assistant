"""Retire exact runtime Redis authority and its declared temporary inventory."""

from src.core.config import settings
from src.core.constants import (
    CONVERSATION_CLEANUP_PAGE_SIZE,
    REDIS_KEY_HITL_PENDING_PREFIX,
    SKILL_PROPOSAL_KEY_PREFIX,
)
from src.core.conversation_target import ConversationRef
from src.infrastructure.cache.key_families import is_reset_purgeable
from src.infrastructure.observability.metrics_key_families import (
    conversation_cleanup_inventory_refusals_total,
    conversation_reset_keys_deleted_total,
)
from src.infrastructure.streaming.runtime_redis import (
    RuntimeRedisClient,
    runtime_inventory_key,
    runtime_writer_key,
)

_PURGE = """
local writer_type = redis.call('TYPE', KEYS[1]).ok
if writer_type ~= 'none' and writer_type ~= 'hash' then return -1 end
redis.call('HSET', KEYS[1], 'phase', 'closed')
redis.call('HDEL', KEYS[1], 'ticket', 'ticket_deadline', 'deadline')
redis.call('PEXPIRE', KEYS[1], ARGV[1])
local inventory_type = redis.call('TYPE', KEYS[2]).ok
if inventory_type ~= 'none' and inventory_type ~= 'set' then return -1 end
local members = redis.call('SRANDMEMBER', KEYS[2], tonumber(ARGV[2]))
-- Validate the complete bounded batch before deleting any of its records.
for _, key in ipairs(members) do
    if key ~= KEYS[3] then
        if string.sub(key, 1, #ARGV[3]) ~= ARGV[3] then return -1 end
        local raw = redis.call('GET', key)
        if raw then
            local ok, item = pcall(cjson.decode, raw)
            if not ok or type(item) ~= 'table' or item.owner_id ~= ARGV[4] then return -1 end
            local legacy = item.runtime_id == nil or item.runtime_id == cjson.null
            if item.runtime_id ~= ARGV[5] and not (legacy and ARGV[4] == ARGV[5]) then return -1 end
            -- ProposalStore retires pending offers before this inventory pass.
            -- A claimed installation has its own account-scoped lifecycle.
            if item.status == 'pending' then return -1 end
        end
    end
end
local deleted = redis.call('DEL', KEYS[3])
for _, key in ipairs(members) do redis.call('SREM', KEYS[2], key) end
return {redis.call('SCARD', KEYS[2]), deleted}
"""


async def purge_runtime_inventory(redis: RuntimeRedisClient, target: ConversationRef) -> bool:
    """Purge exact keys, refusing an unknown member rather than guessing its scope.

    The caller has retired this runtime in SQL and joined its producers. The
    marker invalidates every outstanding activation ticket, including a lost
    acknowledgement. Its TTL is housekeeping, never proof of writer termination.
    """
    hitl_key = f"{REDIS_KEY_HITL_PENDING_PREFIX}{target.runtime_id}"
    if not is_reset_purgeable(hitl_key):
        conversation_cleanup_inventory_refusals_total.inc()
        return False
    while True:
        result = await redis.eval(
            _PURGE,
            3,
            runtime_writer_key(target),
            runtime_inventory_key(target),
            hitl_key,
            str(settings.background_runs_active_ttl_seconds * 1000),
            str(CONVERSATION_CLEANUP_PAGE_SIZE),
            f"{SKILL_PROPOSAL_KEY_PREFIX}:{target.owner_id}:",
            str(target.owner_id),
            str(target.runtime_id),
        )
        if (
            not isinstance(result, list)
            or len(result) != 2
            or any(type(n) is not int or n < 0 for n in result)
        ):
            conversation_cleanup_inventory_refusals_total.inc()
            return False
        remaining, deleted = result
        conversation_reset_keys_deleted_total.labels(
            family=REDIS_KEY_HITL_PENDING_PREFIX.rstrip(":")
        ).inc(deleted)
        if remaining == 0:
            return True
