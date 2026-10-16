"""Atomic logical browser-session admission and token-fenced recovery metadata.

One bounded hash holds ownership WITH metadata. A missing/expired/evicted
record cannot be revived by an old owner's update or renewal. Redis TIME is
the authority for expiry across workers; a PID is never an ownership token.
"""

import asyncio
from typing import Literal

from redis.exceptions import RedisError

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
    local previous = decode(redis.call('HGET', KEYS[1], user))
    if not previous and redis.call('HLEN', KEYS[1]) >= tonumber(ARGV[6]) then
        return {'full', ''}
    end
    local info = cjson.decode(ARGV[5])
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
    user_id: str,
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
                user_id,
                token,
                settings.browser_session_timeout_seconds * 1000,
                info.model_dump_json() if info else "",
                settings.browser_max_concurrent_sessions,
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


async def reserve(user_id: str, info: BrowserSessionInfo) -> BrowserSessionInfo | None:
    """Reserve before context allocation; same-user recovery transfers logical ownership."""
    _, previous = await _change("claim", user_id, info.session_id, info)
    return previous


async def renew(user_id: str, token: str) -> bool:
    """An old owner cannot revive an expired record or overwrite its replacement."""
    owned, _ = await _change("renew", user_id, token)
    return owned


async def update(user_id: str, info: BrowserSessionInfo) -> bool:
    """Publish navigation only if this context still owns the logical session."""
    owned, _ = await _change("update", user_id, info.session_id, info)
    return owned


async def release(user_id: str, token: str) -> None:
    """Remove our record only; a later takeover keeps all its metadata."""
    await _change("release", user_id, token)
