"""Proving a declared number is the person's own: a code spoken, a code typed (lot 2).

The owner-call exception to the confirmation card rests on this: LIA dials the
number the person declared under the ``VERIFICATION`` mandate — a prompt that
reads a short code aloud and nothing else — and the person types that code in
the application. Only then is the number stamped verified
(:meth:`TelephonyIdentityService.mark_verified`), and only a verified number is
ever dialled as « you ».

Bookkeeping lives in Redis, under the person's own runtime family
(``telephony_verify:*``, ``KeyScope.USER_RUNTIME``): the code with a TTL, and
an attempts counter with the same TTL. A wrong code counts; past the cap both
keys are deleted, so the code cannot be brute-forced and the right one is no
longer worth anything — a new call is needed. The comparison is constant-time.

The code is BOUND to the number it was spoken to: the stored value carries the
number, and both the pending probe and the confirmation compare it with the
number declared NOW. Declare A, hear the code on A, switch to B, type the code
— B is not verified, because B was never heard (cold review, 2026-09-16).
Starting a call is bounded per account and per hour by the same cap as the
paid call tools: a session that could start unlimited verification calls could
make LIA ring any number it declares.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import (
    REDIS_KEY_TELEPHONY_VERIFY_ATTEMPTS_PREFIX,
    REDIS_KEY_TELEPHONY_VERIFY_PREFIX,
    REDIS_KEY_TELEPHONY_VERIFY_STARTS_PREFIX,
    TELEPHONY_VERIFICATION_RATE_WINDOW_SECONDS,
)
from src.domains.telephony.errors import (
    raise_phone_number_missing,
    raise_phone_verification_call_not_placed,
    raise_phone_verification_code_wrong,
    raise_phone_verification_locked,
    raise_phone_verification_not_pending,
    raise_phone_verification_too_many_calls,
)
from src.domains.telephony.identity import PhoneIdentity, TelephonyIdentityService
from src.domains.telephony.models import CallKind
from src.domains.telephony.service import TelephonyService
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

if TYPE_CHECKING:
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

#: What the person types is digits; anything else they typed around them
#: (a space, a dash the UI or their memory added) is not part of the code.
#: A no-break space, which a mobile keyboard can insert between digits.
_NBSP = chr(0xA0)
_NOT_A_DIGIT = str.maketrans("", "", " -." + _NBSP)
#: Separates the number a code was spoken to from the code, in the stored value.
_BOUND_SEPARATOR = "|"


@dataclass(frozen=True)
class VerificationStart:
    """What the settings page learns when a verification call leaves.

    Attributes:
        call_id: The placed call.
        expires_in_seconds: How long the spoken code stays valid.
    """

    call_id: UUID | None
    expires_in_seconds: int


class TelephonyVerificationService:
    """Places the verification call and judges the typed code."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        redis: aioredis.Redis,
        identity: TelephonyIdentityService | None = None,
        calls: TelephonyService | None = None,
    ) -> None:
        self.db = db
        self._redis = redis
        self._identity = identity or TelephonyIdentityService(db)
        self._calls = calls or TelephonyService(db)

    @staticmethod
    def _code_key(user_id: UUID) -> str:
        return f"{REDIS_KEY_TELEPHONY_VERIFY_PREFIX}{user_id}"

    @staticmethod
    def _attempts_key(user_id: UUID) -> str:
        return f"{REDIS_KEY_TELEPHONY_VERIFY_ATTEMPTS_PREFIX}{user_id}"

    @staticmethod
    def _draw_code() -> str:
        return "".join(
            secrets.choice("0123456789") for _ in range(settings.telephony_verification_code_length)
        )

    async def _bound_code(self, user_id: UUID) -> str | None:
        """The pending code, if it was spoken to the number declared NOW.

        A code spoken to another number (the person changed or cleared it
        since) is forgotten on the spot: it proves nothing about the current
        line.

        Args:
            user_id: Whose.

        Returns:
            The code, or None when nothing valid is pending.
        """
        stored = await self._redis.get(self._code_key(user_id))
        if stored is None:
            return None
        if isinstance(stored, bytes):
            stored = stored.decode()
        number, _, code = str(stored).partition(_BOUND_SEPARATOR)
        identity = await self._identity.get_identity(user_id)
        if not code or identity.phone_number != number:
            await self._forget(user_id)
            logger.info("phone_verification_code_voided", user_id=str(user_id))
            return None
        return code

    async def pending(self, user_id: UUID) -> bool:
        """Whether a spoken code is still waiting to be typed for the declared number.

        Args:
            user_id: Whose.

        Returns:
            True while a code bound to the current number lives.
        """
        return await self._bound_code(user_id) is not None

    async def _forget(self, user_id: UUID) -> None:
        await self._redis.delete(self._code_key(user_id), self._attempts_key(user_id))

    async def _admit_start(self, user_id: UUID, *, language: str) -> None:
        """Count one verification call against the account's hourly cap.

        Fail-open like every other limiter of the application: a Redis fault
        must never be the reason a person cannot verify their number.
        """
        try:
            limiter = await get_rate_limiter()
            allowed = await limiter.acquire(
                key=f"{REDIS_KEY_TELEPHONY_VERIFY_STARTS_PREFIX}{user_id}",
                max_calls=settings.telephony_rate_limit_per_hour,
                window_seconds=TELEPHONY_VERIFICATION_RATE_WINDOW_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001 — fail open, the cap is a shield not a gate
            logger.warning("phone_verification_rate_check_failed", error_type=type(exc).__name__)
            return
        if not allowed:
            raise_phone_verification_too_many_calls(language)

    async def start(self, user_id: UUID, *, language: str, display_name: str) -> VerificationStart:
        """Draw a code, keep it, and call the declared number to read it aloud.

        Args:
            user_id: Whose number.
            language: The language the call is spoken in, and of any refusal.
            display_name: What the voice calls the person.

        Returns:
            The placed call and the code's lifetime.

        Raises:
            ResourceConflictError: no number is declared, or the call could not
                be placed (a previously spoken code then stays as it was).
            PhoneVerificationLockedError: too many calls this hour.
        """
        identity = await self._identity.get_identity(user_id)
        if identity.phone_number is None:
            raise_phone_number_missing(language)
        await self._admit_start(user_id, language=language)

        code = self._draw_code()
        ttl = settings.telephony_verification_code_ttl_seconds
        result = await self._calls.initiate_call(
            user_id=user_id,
            callee_display=display_name,
            callee_phone=identity.phone_number,
            objective="",
            date_window=None,
            user_language=language,
            kind=CallKind.VERIFICATION,
            verification_code=code,
        )
        if result.status != "placed":
            # No call, no new code — and the PREVIOUS one, if any, stays: a
            # second press while the first call still rings is refused as
            # « already active », and the code being read on that call must
            # remain typeable.
            logger.info(
                "phone_verification_call_not_placed", user_id=str(user_id), status=result.status
            )
            raise_phone_verification_call_not_placed(language, reason=result.status)

        # The call left: the code it will read replaces whatever was pending,
        # bound to the number it was dialled on, with a fresh attempt counter.
        await self._forget(user_id)
        await self._redis.set(
            self._code_key(user_id), f"{identity.phone_number}{_BOUND_SEPARATOR}{code}", ex=ttl
        )
        logger.info("phone_verification_started", user_id=str(user_id), call_id=str(result.call_id))
        return VerificationStart(call_id=result.call_id, expires_in_seconds=ttl)

    async def confirm(self, user_id: UUID, typed: str, *, language: str) -> PhoneIdentity:
        """Judge the typed code; stamp the number verified on a match.

        Args:
            user_id: Whose number.
            typed: What the person typed.
            language: For the refusal's sentence.

        Returns:
            The identity, verified.

        Raises:
            ResourceConflictError: no verification is pending.
            ValidationError: the code is wrong; the sentence says how many
                tries remain.
            PhoneVerificationLockedError: the tries are spent; both keys are
                deleted and a new call is needed.
        """
        expected = await self._bound_code(user_id)
        if expected is None:
            raise_phone_verification_not_pending(language)

        attempts = int(await self._redis.incr(self._attempts_key(user_id)))
        await self._redis.expire(
            self._attempts_key(user_id), settings.telephony_verification_code_ttl_seconds
        )
        max_attempts = settings.telephony_verification_max_attempts
        if attempts > max_attempts:
            await self._forget(user_id)
            logger.info("phone_verification_locked", user_id=str(user_id))
            raise_phone_verification_locked(language)

        candidate = typed.translate(_NOT_A_DIGIT)
        # Bytes, not str: ``compare_digest`` refuses a non-ASCII str, and a
        # mobile keyboard can type digits from another script.
        if not secrets.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8")):
            attempts_left = max_attempts - attempts
            if attempts_left <= 0:
                await self._forget(user_id)
                logger.info("phone_verification_locked", user_id=str(user_id))
                raise_phone_verification_locked(language)
            raise_phone_verification_code_wrong(attempts_left, language)

        await self._forget(user_id)
        return await self._identity.mark_verified(user_id, language=language)


__all__ = ["TelephonyVerificationService", "VerificationStart"]
