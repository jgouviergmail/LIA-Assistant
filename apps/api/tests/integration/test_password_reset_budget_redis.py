"""The per-account password-reset budget on a real Redis (ADR-363).

The unit tests hold the budget to the limiter's contract with an in-memory
double; these run the composition on the real Lua sliding window: one e-mail
per interval, a day that counts only the e-mails it admitted, one budget per
account, and keys that expire with their windows. The integration conftest
purges every ``auth:*`` key before each test.
"""

from uuid import UUID, uuid4

import pytest

from src.core.config import settings
from src.core.constants import (
    PASSWORD_RESET_ACCOUNT_DAILY_WINDOW_SECONDS,
    PASSWORD_RESET_BUDGET_REDIS_PREFIX,
)
from src.domains.auth.password_reset_policy import acquire_reset_send
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

pytestmark = pytest.mark.integration

#: The limiter keeps a key a few seconds past its window; a key that outlived
#: its window by more than this would be a budget that never frees.
_EXPIRY_SLACK_SECONDS = 60


def _key(account_id: UUID, window: str) -> str:
    return f"{PASSWORD_RESET_BUDGET_REDIS_PREFIX}:{account_id}:{window}"


async def test_one_e_mail_per_interval() -> None:
    account_id = uuid4()

    assert await acquire_reset_send(account_id)
    assert not await acquire_reset_send(account_id)


async def test_refused_attempts_never_reach_the_day_count() -> None:
    account_id = uuid4()
    limiter = await get_rate_limiter()

    await acquire_reset_send(account_id)
    for _ in range(5):
        assert not await acquire_reset_send(account_id)

    assert await limiter.redis.zcard(_key(account_id, "day")) == 1


async def test_each_account_has_its_own_budget() -> None:
    assert await acquire_reset_send(uuid4())
    assert await acquire_reset_send(uuid4())


async def test_the_budget_expires_with_its_windows() -> None:
    account_id = uuid4()
    limiter = await get_rate_limiter()

    await acquire_reset_send(account_id)

    interval_ttl = await limiter.redis.ttl(_key(account_id, "interval"))
    day_ttl = await limiter.redis.ttl(_key(account_id, "day"))
    interval = settings.password_reset_account_interval_seconds
    assert interval < interval_ttl <= interval + _EXPIRY_SLACK_SECONDS
    day = PASSWORD_RESET_ACCOUNT_DAILY_WINDOW_SECONDS
    assert day < day_ttl <= day + _EXPIRY_SLACK_SECONDS
