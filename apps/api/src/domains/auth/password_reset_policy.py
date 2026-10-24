"""Who may receive a password-reset link (ADR-363).

A reset link lets whoever reads the mailbox choose the account's password, so
three kinds of account are never sent one:

- a **deleted** account: its address is kept for billing, its person is gone;
- an **administrator**: the most privileged account is not recovered by e-mail
  — attempts are counted and alerted on instead;
- an account that **signs in with a provider and has no password**: the link
  would CREATE a password, a second door outside the provider's protection.
  It is sent a notice saying how it signs in instead.

An account that disabled its password for passkeys, and signs in with no
provider, keeps the link: that is the documented way back when the passkeys are
lost (ADR-143, arbitration A8); one that also signs in with a provider is sent
the notice, and the provider is its way back. The same decision is applied when
a link is USED, so a link issued before an account changed state cannot outlive
the change, and it is what the Security settings state as the way back
(``recovery_without_password``).
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

import structlog
from redis.exceptions import RedisError

from src.core.config import settings
from src.core.constants import (
    PASSWORD_RESET_ACCOUNT_DAILY_WINDOW_SECONDS,
    PASSWORD_RESET_BUDGET_REDIS_PREFIX,
)
from src.domains.users.models import User
from src.infrastructure.observability.metrics_auth import (
    password_reset_confirmations_total,
    password_reset_requests_total,
)
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

logger = structlog.get_logger(__name__)


class ResetDecision(StrEnum):
    """What a password-reset request does for an account."""

    LINK = "link"
    NOTICE = "notice"
    REFUSE_DELETED = "refuse_deleted"
    REFUSE_SUPERUSER = "refuse_superuser"


class PasswordRecovery(StrEnum):
    """What a reset request leaves an account that holds no password.

    Published by ``GET /auth/step-up/status``: the Security settings state this
    way back, never one the reset decision refuses.
    """

    EMAIL_LINK = "email_link"
    PROVIDER = "provider"
    NONE = "none"


class ResetRequestOutcome(StrEnum):
    """What one reset request did — the ``outcome`` of ``password_reset_requests_total``."""

    LINK_SENT = "link_sent"
    NOTICE_SENT = "notice_sent"
    SEND_FAILED = "send_failed"
    THROTTLED = "throttled"
    UNKNOWN_ACCOUNT = "unknown_account"
    REFUSED_DELETED = "refused_deleted"
    REFUSED_SUPERUSER = "refused_superuser"


class ResetUseOutcome(StrEnum):
    """What one use of a reset link gave — the ``outcome`` of ``password_reset_confirmations_total``.

    ``rejected_token`` is every refusal of the token verifier (signature, type,
    expiry, or a single-use link replayed — the replay keeps its own log event,
    ``password_reset_token_reused``).
    """

    COMPLETED = "completed"
    REJECTED_TOKEN = "rejected_token"
    STALE_TOKEN = "stale_token"
    UNKNOWN_ACCOUNT = "unknown_account"
    INELIGIBLE = "ineligible"


#: The decisions that send nothing, and how each is counted.
REFUSED_REQUEST_OUTCOMES: dict[ResetDecision, ResetRequestOutcome] = {
    ResetDecision.REFUSE_DELETED: ResetRequestOutcome.REFUSED_DELETED,
    ResetDecision.REFUSE_SUPERUSER: ResetRequestOutcome.REFUSED_SUPERUSER,
}


def record_reset_request(outcome: ResetRequestOutcome) -> None:
    """Count what a reset request did."""
    password_reset_requests_total.labels(outcome=outcome.value).inc()


def record_reset_use(outcome: ResetUseOutcome) -> None:
    """Count what a reset link gave when used."""
    password_reset_confirmations_total.labels(outcome=outcome.value).inc()


# Every outcome exposes its series from the start, at zero: a counter's first
# event is otherwise invisible to ``increase()``, the alert would miss the
# opening request of a burst, and a panel would read "No data" for a healthy 0.
for _request_outcome in ResetRequestOutcome:
    password_reset_requests_total.labels(outcome=_request_outcome.value)
for _use_outcome in ResetUseOutcome:
    password_reset_confirmations_total.labels(outcome=_use_outcome.value)


#: How each sign-in provider the code writes into ``users.oauth_provider`` is
#: named in the notice. Held equal to the writers by a unit test.
SIGN_IN_PROVIDER_LABELS: dict[str, str] = {"google": "Google"}


def decide_reset(user: User) -> ResetDecision:
    """Decide what a reset request — or a reset link being used — may do.

    Args:
        user: The account the request names.

    Returns:
        The decision; only ``LINK`` lets a link be issued or used.
    """
    return _decide(user, has_password=user.hashed_password is not None)


def recovery_without_password(user: User) -> PasswordRecovery:
    """What a reset request would leave the account once it holds no password.

    The reset decision itself, read for the account without its password: the
    Security settings state it beside a password already disabled, and in the
    dialog that disables one (ADR-143, arbitration A8).

    Args:
        user: The signed-in account.

    Returns:
        ``EMAIL_LINK`` (the link stays the way back), ``PROVIDER`` (a notice
        names the provider it signs in with) or ``NONE`` (nothing is sent).
    """
    decision = _decide(user, has_password=False)
    if decision is ResetDecision.LINK:
        return PasswordRecovery.EMAIL_LINK
    if decision is ResetDecision.NOTICE:
        return PasswordRecovery.PROVIDER
    return PasswordRecovery.NONE


def _decide(user: User, *, has_password: bool) -> ResetDecision:
    """The one rule behind ``decide_reset`` and ``recovery_without_password``."""
    if user.is_deleted:
        return ResetDecision.REFUSE_DELETED
    if user.is_superuser:
        return ResetDecision.REFUSE_SUPERUSER
    if not has_password and user.oauth_provider is not None:
        return ResetDecision.NOTICE
    return ResetDecision.LINK


def sign_in_provider_label(provider: str) -> str:
    """The provider's name as the notice says it.

    Args:
        provider: The ``users.oauth_provider`` value.

    Returns:
        The declared label, or the stored value itself for a provider no
        writer declares (the unit test refuses such a writer).
    """
    return SIGN_IN_PROVIDER_LABELS.get(provider, provider)


async def acquire_reset_send(user_id: UUID) -> bool:
    """Spend one e-mail of the account's reset budget, whatever IP asks.

    The short window is asked first, so an attempt it refuses never reaches the
    day's count: the day counts the e-mails it admitted, never the refused
    attempts — hammering the route cannot spend a victim's day. A store that
    cannot be reached lets the e-mail leave — the limiter's own doctrine, and
    the per-IP limiter still stands in front of the route.

    Args:
        user_id: The account the e-mail would reach.

    Returns:
        True when an e-mail may leave now.
    """
    prefix = f"{PASSWORD_RESET_BUDGET_REDIS_PREFIX}:{user_id}"
    try:
        limiter = await get_rate_limiter()
        if not await limiter.acquire(
            key=f"{prefix}:interval",
            max_calls=1,
            window_seconds=settings.password_reset_account_interval_seconds,
        ):
            return False
        return await limiter.acquire(
            key=f"{prefix}:day",
            max_calls=settings.password_reset_account_daily_max,
            window_seconds=PASSWORD_RESET_ACCOUNT_DAILY_WINDOW_SECONDS,
        )
    except (RedisError, OSError) as error:
        logger.error(
            "password_reset_budget_unavailable",
            user_id=str(user_id),
            error_type=type(error).__name__,
        )
        return True
