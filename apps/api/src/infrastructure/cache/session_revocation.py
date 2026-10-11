"""One atomic owned selection; raw session ids stay inside the Redis boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError, raise_step_up_required
from src.core.session_freshness import step_up_valid_until

if TYPE_CHECKING:
    from src.infrastructure.cache.session_store import SessionStore, UserSession

_REVOKE_SELECTED = """
local function owned(key)
    local saved = redis.call('GET', key)
    if not saved then return nil end
    local valid, data = pcall(cjson.decode, saved)
    if not valid or type(data) ~= 'table' or data.user_id ~= ARGV[1] then
        return false
    end
    return data
end
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
if tonumber(ARGV[6]) > 0 and now >= tonumber(ARGV[6]) then return -3 end
if ARGV[2] == '1' then
    local current = owned(KEYS[2])
    if not current then return -1 end
    if ARGV[3] ~= '' and (current.step_up_at ~= ARGV[3]
        or now < tonumber(ARGV[4]) or now > tonumber(ARGV[5])) then return -4 end
end
for i = 3, #KEYS do
    local selected = owned(KEYS[i])
    if selected == false then return -2 end
    if selected and redis.call('SISMEMBER', KEYS[1], ARGV[i + 4]) ~= 1 then
        return -2
    end
end
local removed = 0
for i = 3, #KEYS do
    removed = removed + redis.call('DEL', KEYS[i])
    redis.call('SREM', KEYS[1], ARGV[i + 4])
end
return removed
"""


def _freshness_bounds(
    current: UserSession | None, require_fresh_step_up: bool, approved_until: datetime | None
) -> tuple[str, int, int, int]:
    now = datetime.now(UTC)
    deadline = 0
    if approved_until is not None:
        if approved_until.tzinfo is None or approved_until.utcoffset() is None:
            raise ValueError("Approval expiry requires a timezone")
        deadline = int(approved_until.timestamp() * 1000)
    if not require_fresh_step_up:
        return "", 0, 0, deadline
    if current is None:
        raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
    stamp = current.step_up_at
    valid_until = step_up_valid_until(stamp, now, settings.step_up_window_seconds)
    if stamp is None or valid_until is None:
        raise_step_up_required()
    return (
        stamp.isoformat(),
        int(stamp.timestamp() * 1000),
        int(valid_until.timestamp() * 1000),
        deadline,
    )


def _revocation_result(result: object, target_count: int) -> int:
    if type(result) is not int:
        raise ValueError("Invalid session revocation receipt")
    if result == -4:
        raise_step_up_required()
    if result in {-1, -3}:
        raise AuthorizationError(
            detail={"error_code": "SESSION_UNAVAILABLE" if result == -1 else "INTERACTION_EXPIRED"}
        )
    if result == -2:
        raise ResourceConflictError("sessions", detail={"error_code": "STALE_STATE"})
    if result < 0 or result > target_count:
        raise ValueError("Invalid session revocation receipt")
    return result


async def revoke_selected_sessions(
    store: SessionStore,
    actor_id: UUID,
    selected: tuple[UserSession, ...],
    *,
    current: UserSession | None = None,
    require_fresh_step_up: bool = False,
    approved_until: datetime | None = None,
) -> int:
    """Remove only this already-resolved selection, after validating every live row.

    The caller owns current account/capability authorization and exact HITL.
    When supplied, the current session and fresh step-up are checked again
    inside the mutation. Expired targets are harmless; a mismatched owner,
    missing current session or withdrawn proof refuses the whole selection.
    A newly created session is never added to this frozen selection.
    """
    owner = str(actor_id)
    sessions = selected + ((current,) if current is not None else ())
    if any(item.user_id != owner or not item.session_id for item in sessions):
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    ids = [item.session_id for item in selected]
    if len(set(ids)) != len(ids):
        raise ValueError("A session selection must be unique")
    stamp, started, valid_until, deadline = _freshness_bounds(
        current, require_fresh_step_up, approved_until
    )
    index = f"user:{owner}:sessions"
    keys = [index, f"session:{current.session_id}" if current is not None else index]
    keys.extend(f"session:{identity}" for identity in ids)
    result: object = await store.redis.eval(
        _REVOKE_SELECTED,
        len(keys),
        *keys,
        owner,
        "1" if current is not None else "0",
        stamp,
        started,
        valid_until,
        deadline,
        *ids,
    )
    return _revocation_result(result, len(selected))
