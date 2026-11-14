"""Atomic logical browser-session admission and token-fenced recovery metadata.

One bounded hash holds ownership WITH metadata. A missing/expired/evicted
record cannot be revived by an old owner's update or renewal. Redis TIME is
the authority for expiry across workers; a PID is never an ownership token.
"""

import asyncio
from typing import Literal
from uuid import UUID

from redis.exceptions import RedisError

from src.core.browser_scope import BrowserScope
from src.core.config import settings
from src.core.constants import BROWSER_COORDINATION_TIMEOUT_SECONDS, REDIS_KEY_BROWSER_POOL_REGISTRY
from src.infrastructure.browser.errors import BrowserRefusal, BrowserRefusalReason
from src.infrastructure.browser.models import BrowserSessionInfo
from src.infrastructure.cache import redis as redis_cache


class BrowserCoordinationUnavailable(RuntimeError):
    """The pool may apply its bounded local fallback while Redis is unavailable."""


_CHANGE = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local op, user, token = ARGV[1], ARGV[2], ARGV[3]
local ttl = tonumber(ARGV[4])
-- Probe support AND permission before any write. This reserved non-UUID field
-- cannot be an application user. A failed Lua command does not roll back prior
-- writes, so an unsupported server must never leave an unexpiring new record.
local supported = redis.pcall('HPEXPIREAT', KEYS[1], now + ttl,
                             'FIELDS', 1, '__expiry_capability_probe__')
if type(supported) == 'table' and supported.err then return {'unsupported', ''} end
local function decode(raw)
    if not raw then return nil end
    local ok, item = pcall(cjson.decode, raw)
    if not ok or type(item) ~= 'table' or type(item.expires_ms) ~= 'number'
       or type(item.info) ~= 'table' or type(item.info.session_id) ~= 'string'
       then return nil end
    return item
end
-- The registry is bounded by the configured limit (1..10). Prune at EVERY
-- operation: an active user's renewals must not retain a crashed worker's
-- expired private metadata indefinitely by extending the whole hash's TTL.
local entries = redis.call('HGETALL', KEYS[1])
for index = 1, #entries, 2 do
    local item = decode(entries[index + 1])
    if not item or item.expires_ms <= now then
        redis.call('HDEL', KEYS[1], entries[index])
    else
        redis.call('HPEXPIREAT', KEYS[1], item.expires_ms, 'FIELDS', 1, entries[index])
    end
end
-- Any pre-field-expiry registry is safe to migrate only after all its live
-- fields have their own deadline. Other users cannot extend that deadline.
redis.call('PERSIST', KEYS[1])
if op == 'claim' then
    local info = cjson.decode(ARGV[5])
    local previous = decode(redis.call('HGET', KEYS[1], user))
    if not previous and ARGV[7] ~= '' then
        local legacy = decode(redis.call('HGET', KEYS[1], ARGV[7]))
        if legacy and legacy.info.user_id == info.user_id
           and (not legacy.info.runtime_id or legacy.info.runtime_id == cjson.null) then
            previous = legacy
            redis.call('HDEL', KEYS[1], ARGV[7])
        end
    end
    if not previous and redis.call('HLEN', KEYS[1]) >= tonumber(ARGV[6]) then
        return {'full', ''}
    end
    if previous then
        info.current_url = previous.info.current_url
        info.page_title = previous.info.page_title
    end
    redis.call('HSET', KEYS[1], user, cjson.encode({expires_ms=now+ttl, info=info}))
    redis.call('HPEXPIREAT', KEYS[1], now+ttl, 'FIELDS', 1, user)
    return {'ok', previous and cjson.encode(previous.info) or ''}
end
local item = decode(redis.call('HGET', KEYS[1], user))
if not item or item.expires_ms <= now then
    redis.call('HDEL', KEYS[1], user)
    return {'lost', ''}
end
if item.info.session_id ~= token then return {'lost', ''} end
if op == 'release' then
    redis.call('HDEL', KEYS[1], user)
    return {'ok', ''}
end
if op == 'update' then item.info = cjson.decode(ARGV[5]) end
item.expires_ms = now + ttl
redis.call('HSET', KEYS[1], user, cjson.encode(item))
redis.call('HPEXPIREAT', KEYS[1], now+ttl, 'FIELDS', 1, user)
return {'ok', ''}
"""


async def _change(
    operation: Literal["claim", "renew", "update", "release"],
    scope: BrowserScope,
    token: str,
    info: BrowserSessionInfo | None = None,
) -> tuple[bool, BrowserSessionInfo | None]:
    try:
        async with asyncio.timeout(BROWSER_COORDINATION_TIMEOUT_SECONDS):
            redis = await redis_cache.get_redis_cache()
            reply = await redis.eval(
                _CHANGE,
                1,
                REDIS_KEY_BROWSER_POOL_REGISTRY,
                operation,
                scope.key,
                token,
                settings.browser_session_timeout_seconds * 1000,
                info.model_dump_json() if info else "",
                settings.browser_max_concurrent_sessions,
                scope.legacy_key or "",
            )
    except (RedisError, OSError) as exc:
        raise BrowserCoordinationUnavailable("browser coordination unavailable") from exc
    verdict = reply[0].decode() if isinstance(reply[0], bytes) else reply[0]
    if verdict == "full":
        raise BrowserRefusal(BrowserRefusalReason.CAPACITY)
    if verdict == "unsupported":
        raise BrowserRefusal(BrowserRefusalReason.COORDINATION_UNSUPPORTED)
    if verdict not in {"ok", "lost"}:
        raise ValueError("unexpected browser coordination verdict")
    try:
        previous = BrowserSessionInfo.model_validate_json(reply[1]) if reply[1] else None
    except ValueError:
        previous = None
    return verdict == "ok", previous


async def reserve(scope: BrowserScope, info: BrowserSessionInfo) -> BrowserSessionInfo | None:
    """Reserve before allocation; recovery transfers ownership of this runtime only."""
    _require_scope(scope, info)
    _, previous = await _change("claim", scope, info.session_id, info)
    return previous


async def renew(scope: BrowserScope, token: str) -> bool:
    """An old owner cannot revive an expired record or overwrite its replacement."""
    owned, _ = await _change("renew", scope, token)
    return owned


async def update(scope: BrowserScope, info: BrowserSessionInfo) -> bool:
    """Publish navigation only if this context still owns the logical session."""
    _require_scope(scope, info)
    owned, _ = await _change("update", scope, info.session_id, info)
    return owned


async def release(scope: BrowserScope, token: str) -> None:
    """Remove our record only; a later takeover keeps all its metadata."""
    await _change("release", scope, token)


def _require_scope(scope: BrowserScope, info: BrowserSessionInfo) -> None:
    """A writer cannot attribute another runtime's metadata to this field."""
    if info.user_id != str(scope.owner_id) or info.runtime_id != scope.runtime_id:
        raise BrowserRefusal(BrowserRefusalReason.SCOPE_UNAVAILABLE)


_FORGET = """
local fields = redis.call('HKEYS', KEYS[1])
local removed = 0
for _, field in ipairs(fields) do
    if field == ARGV[1] or string.sub(field, 1, #ARGV[1]+1) == ARGV[1] .. ':' then
        if ARGV[2] == '' or field == ARGV[1] .. ':' .. ARGV[2]
           or (field == ARGV[1] and ARGV[2] == ARGV[1]) then
            removed = removed + redis.call('HDEL', KEYS[1], field)
        end
    end
end
return removed
"""


async def forget(owner_id: UUID, runtime_id: UUID | None = None) -> int:
    """Retire exact runtime fields, or every owned field on account erasure.

    The lifecycle caller has already fenced new admissions. Superseded workers
    retire their local context on renewal; updates cannot recreate a lost field.
    A Redis failure propagates so durable cleanup can retry it.
    """
    async with asyncio.timeout(BROWSER_COORDINATION_TIMEOUT_SECONDS):
        redis = await redis_cache.get_redis_cache()
        removed = int(
            await redis.eval(
                _FORGET,
                1,
                REDIS_KEY_BROWSER_POOL_REGISTRY,
                str(owner_id),
                str(runtime_id) if runtime_id is not None else "",
            )
        )
    return removed
