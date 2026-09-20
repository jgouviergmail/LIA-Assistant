"""The person's own phone number: declared, stored encrypted, verified by a call (lot 1).

An owner call skips the confirmation card because the person who would
confirm is the person who picks up. That exception rests on a fact the person
asserted about THEMSELVES — the number they typed here and then heard LIA read
a code on — never on a name match in the address book: a homonym there would
send the owner's context to a stranger.

Three rules the service enforces, each a test:

- the stored form is E.164 or nothing (``phone_numbers.to_e164``);
- a CHANGED number loses its verification; the same number typed again keeps it;
- :meth:`verified_number` is the one seam callers read, and it answers only
  when the number is verified — the owner-call tool and the identity routes
  both go through it, so nothing can dial an unverified line as « you ».

The verification CALL itself (a ``VERIFICATION`` mandate reading a code aloud)
is placed by :class:`TelephonyVerificationService` (lot 2); this module holds
the record and the code's bookkeeping only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from src.core.exceptions import raise_user_not_found
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.shared.phone_domains import is_phone_domain, unknown_phone_domains
from src.domains.telephony.callback import live_unavailable_reason
from src.domains.telephony.errors import (
    raise_phone_call_mode_unknown,
    raise_phone_domain_unknown,
    raise_phone_number_invalid,
    raise_phone_number_missing,
)
from src.domains.telephony.phone_numbers import to_e164
from src.domains.users.repository import UserRepository
from src.domains.voice_sessions.session import VoiceSessionMode, as_voice_session_mode

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PhoneIdentity:
    """What the settings page shows, and what an owner call may rely on.

    Attributes:
        phone_number: The declared number in E.164, or None.
        verified: Whether LIA has heard the person answer this number.
        verified_at: When that happened.
        rich_context_enabled: Whether an owner call carries the chat's context
            beyond the free/busy projection.
        disabled_domains: The phone domains the person switched OFF for their
            own calls (lot 8); everything else the phone offers stays on, a
            domain added later included.
        call_mode: How the person CHOSE their own calls to run (ADR-301):
            ``delegated`` (Live) or ``direct`` (Live direct).
        live_available: Whether this instance can run a Live call at all —
            the vendor must be able to call this API back.
        live_unavailable_reason: Why not, when it cannot (a stable code the
            settings page translates); None when it can.
        call_mode_effective: What a call placed now would actually run: the
            choice, or ``direct`` when Live is unavailable — stated here so
            the page never shows a mode the dial path will not honour.
    """

    phone_number: str | None
    verified: bool
    verified_at: datetime | None
    rich_context_enabled: bool
    disabled_domains: tuple[str, ...] = ()
    call_mode: VoiceSessionMode = "delegated"
    live_available: bool = True
    live_unavailable_reason: str | None = None

    @property
    def call_mode_effective(self) -> VoiceSessionMode:
        """The mode a call placed now runs."""
        return self.call_mode if self.live_available else "direct"


class TelephonyIdentityService:
    """Reads and writes the person's phone identity on the ``users`` row."""

    def __init__(self, db: AsyncSession, *, users: UserRepository | None = None) -> None:
        self.db = db
        self.users = users or UserRepository(db)

    async def _user(self, user_id: UUID) -> Any:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise_user_not_found(user_id)
        return user

    @staticmethod
    def _stored_number(user: Any) -> str | None:
        """The decrypted number, or None when there is none or it is unreadable.

        Unreadable ciphertext (a rotated key) reads as « no number »: the page
        must render and the person can declare it again; it must never turn
        into a 500 or, worse, a verified line nobody can read.
        """
        token = user.phone_number_encrypted
        if not token:
            return None
        try:
            return decrypt_data(token)
        except Exception as exc:  # noqa: BLE001 — degrade to "not set"
            logger.warning(
                "phone_number_decrypt_failed",
                user_id=str(user.id),
                error_type=type(exc).__name__,
            )
            return None

    @classmethod
    def _identity_of(cls, user: Any) -> PhoneIdentity:
        number = cls._stored_number(user)
        verified_at = user.phone_number_verified_at if number else None
        reason = live_unavailable_reason()
        return PhoneIdentity(
            phone_number=number,
            verified=verified_at is not None,
            verified_at=verified_at,
            rich_context_enabled=bool(user.phone_rich_context_enabled),
            disabled_domains=tuple(
                d for d in (user.phone_disabled_domains or []) if is_phone_domain(str(d))
            ),
            call_mode=as_voice_session_mode(str(user.phone_call_mode or "delegated")),
            live_available=reason is None,
            live_unavailable_reason=reason,
        )

    async def get_identity(self, user_id: UUID) -> PhoneIdentity:
        """The person's phone identity.

        Args:
            user_id: Whose.

        Returns:
            The identity; empty when no number is declared.
        """
        return self._identity_of(await self._user(user_id))

    async def verified_number(self, user_id: UUID) -> str | None:
        """The number an owner call may dial as « you » — verified, or None.

        Args:
            user_id: Whose.

        Returns:
            The E.164 number when verified; None otherwise.
        """
        identity = self._identity_of(await self._user(user_id))
        return identity.phone_number if identity.verified else None

    async def set_number(self, user_id: UUID, raw: str, *, language: str = "en") -> PhoneIdentity:
        """Declare (or re-declare) the number.

        Args:
            user_id: Whose.
            raw: What the person typed.
            language: For the refusal's sentence.

        Returns:
            The identity after the write.

        Raises:
            ValidationError: when the input is not a dialable E.164 line.
        """
        number = to_e164(raw)
        if number is None:
            raise_phone_number_invalid(language)
        user = await self._user(user_id)
        if self._stored_number(user) == number:
            # The same line, typed again: nothing to write, the verification
            # stands. Re-encrypting would rotate the token for no reason.
            return self._identity_of(user)
        await self.users.update(
            user,
            {
                "phone_number_encrypted": encrypt_data(number),
                # A new line is a new identity: it must be heard again.
                "phone_number_verified_at": None,
            },
        )
        await self.db.commit()
        logger.info("phone_number_declared", user_id=str(user_id))
        return self._identity_of(user)

    async def clear_number(self, user_id: UUID) -> None:
        """Forget the number and its verification.

        Args:
            user_id: Whose.
        """
        user = await self._user(user_id)
        await self.users.update(
            user, {"phone_number_encrypted": None, "phone_number_verified_at": None}
        )
        await self.db.commit()
        logger.info("phone_number_cleared", user_id=str(user_id))

    async def mark_verified(self, user_id: UUID, *, language: str = "en") -> PhoneIdentity:
        """Stamp the declared number as heard — called once a code matched.

        Args:
            user_id: Whose.
            language: For the refusal's sentence.

        Returns:
            The identity after the write.

        Raises:
            ResourceConflictError: no number is declared — a stamp with no
                line under it would be a verified number nobody can read.
        """
        user = await self._user(user_id)
        if self._stored_number(user) is None:
            raise_phone_number_missing(language)
        await self.users.update(user, {"phone_number_verified_at": datetime.now(UTC)})
        await self.db.commit()
        logger.info("phone_number_verified", user_id=str(user_id))
        return self._identity_of(user)

    async def set_rich_context(self, user_id: UUID, enabled: bool) -> PhoneIdentity:
        """Switch the rich context of owner calls on or off.

        Args:
            user_id: Whose.
            enabled: The new value.

        Returns:
            The identity after the write.
        """
        user = await self._user(user_id)
        await self.users.update(user, {"phone_rich_context_enabled": enabled})
        await self.db.commit()
        logger.info("phone_rich_context_set", user_id=str(user_id), enabled=enabled)
        return self._identity_of(user)

    async def set_call_mode(
        self, user_id: UUID, mode: str, *, language: str = "en"
    ) -> PhoneIdentity:
        """Choose how the person's own calls run (ADR-301).

        The choice is stored whatever the instance can run today: a callback
        that becomes public later honours it without another click. The
        EFFECTIVE mode is derived on every read.

        Args:
            user_id: Whose.
            mode: ``delegated`` (Live) or ``direct`` (Live direct).
            language: The caller's language, for a translated refusal.

        Returns:
            The identity after the write.

        Raises:
            ValidationError: On a mode off the vocabulary.
        """
        try:
            stored = as_voice_session_mode(mode)
        except ValueError:
            raise_phone_call_mode_unknown(language)
        user = await self._user(user_id)
        await self.users.update(user, {"phone_call_mode": stored})
        await self.db.commit()
        logger.info("phone_call_mode_set", user_id=str(user_id), mode=stored)
        return self._identity_of(user)

    async def set_disabled_domains(
        self, user_id: UUID, domains: list[str], *, language: str = "en"
    ) -> PhoneIdentity:
        """Replace the set of phone domains the person switched off (lot 8).

        Stored as the DISABLED set, so a domain the phone starts offering
        later is on by default — parity with the chat is the rule, the
        switch is the exception. A NEW list is stored (the JSONB rule).

        Args:
            user_id: Whose.
            domains: The domains to switch off; must all be phone domains.
            language: The caller's language, for a translated refusal.

        Returns:
            The identity after the write.

        Raises:
            ValidationError: On a domain the phone does not offer.
        """
        if unknown_phone_domains(domains):
            raise_phone_domain_unknown(language)
        user = await self._user(user_id)
        stored = sorted(set(domains))
        await self.users.update(user, {"phone_disabled_domains": stored})
        await self.db.commit()
        logger.info("phone_disabled_domains_set", user_id=str(user_id), count=len(stored))
        return self._identity_of(user)


__all__ = ["PhoneIdentity", "TelephonyIdentityService"]
