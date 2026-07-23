"""Live-session watcher for SSE streams (security program D2, Lot 4).

A revoked BFF session must cut its active SSE subscriptions within one
keepalive interval ("sign out this device" acts immediately). The check is
a single Redis GET at keepalive cadence — fail-open on infrastructure
errors so a Redis hiccup never kills healthy streams. Detached background
runs (ADR-117) are unaffected by design: only the subscriber side closes.
"""

from contextlib import suppress

import structlog

from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore

logger = structlog.get_logger(__name__)

# SSE transport comment emitted just before closing a revoked subscriber.
SESSION_REVOKED_COMMENT = ": session-revoked\n\n"


async def session_still_valid(session_id: str | None) -> bool:
    """Whether the BFF session behind an SSE stream still exists.

    Args:
        session_id: The ``lia_session`` cookie value captured at connect
            time; None disables the check (defensive — e.g. tests).

    Returns:
        False only when Redis positively reports the session gone.
    """
    if not session_id:
        return True

    # Fail-open: an infrastructure error must not sever healthy streams —
    # revocation enforcement resumes at the next keepalive tick.
    with suppress(Exception):
        redis = await get_redis_session()
        session = await SessionStore(redis).get_session(session_id)
        if session is None:
            logger.info("sse_session_revoked_detected", session_id=session_id)
            return False
    return True
