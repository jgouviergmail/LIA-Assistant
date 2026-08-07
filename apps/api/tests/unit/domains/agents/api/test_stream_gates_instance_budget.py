"""The pre-stream gate distinguishes a personal limit from an instance pause.

Both block, but they mean opposite things to the visitor: "you reached your
quota, contact your administrator" is wrong and actively misleading when the
whole deployment paused until tomorrow — there is nothing the visitor or the
administrator can do about it today.

What must hold:
- the gate carries a DEDICATED error code for the instance ceiling, so the
  frontend can localize the right sentence in all 6 languages;
- the backend never ships the user-visible sentence itself (the reason field
  stays technical, for logs and the admin API);
- the personal-limit path is untouched.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.constants import (
    INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE,
    INSTANCE_DAILY_BUDGET_LIMIT_NAME,
    USAGE_LIMIT_EXCEEDED_ERROR_CODE,
)
from src.domains.agents.api.stream_gates import usage_limit_error_chunk
from src.domains.usage_limits.schemas import UsageLimitStatus
from src.domains.usage_limits.service import UsageLimitCheckResult

pytestmark = pytest.mark.unit


def _patch_check(result: UsageLimitCheckResult) -> object:
    return patch(
        "src.domains.usage_limits.service.UsageLimitService.check_user_allowed",
        AsyncMock(return_value=result),
    )


async def test_an_exhausted_instance_uses_its_own_error_code() -> None:
    blocked = UsageLimitCheckResult(
        allowed=False,
        status=UsageLimitStatus.BLOCKED_INSTANCE_BUDGET,
        blocked_reason="Instance daily budget exhausted",
        exceeded_limit=INSTANCE_DAILY_BUDGET_LIMIT_NAME,
    )
    with _patch_check(blocked):
        chunk = await usage_limit_error_chunk(uuid4())
    assert chunk is not None
    assert chunk.metadata["error_code"] == INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE
    assert chunk.metadata["limit"] == INSTANCE_DAILY_BUDGET_LIMIT_NAME


async def test_a_personal_limit_keeps_the_historical_error_code() -> None:
    blocked = UsageLimitCheckResult(
        allowed=False,
        status=UsageLimitStatus.BLOCKED_LIMIT,
        blocked_reason="Usage limit exceeded: cycle_tokens",
        exceeded_limit="cycle_tokens",
    )
    with _patch_check(blocked):
        chunk = await usage_limit_error_chunk(uuid4())
    assert chunk is not None
    assert chunk.metadata["error_code"] == USAGE_LIMIT_EXCEEDED_ERROR_CODE


async def test_the_gate_no_longer_short_circuits_on_the_per_user_flag() -> None:
    blocked = UsageLimitCheckResult(
        allowed=False,
        status=UsageLimitStatus.BLOCKED_INSTANCE_BUDGET,
        blocked_reason="Instance daily budget exhausted",
        exceeded_limit=INSTANCE_DAILY_BUDGET_LIMIT_NAME,
    )
    with _patch_check(blocked):
        chunk = await usage_limit_error_chunk(uuid4())
    # The old early-return on `usage_limits_enabled` would have skipped the
    # check entirely and let an exhausted instance keep spending.
    assert chunk is not None
    assert chunk.metadata["error_code"] == INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE


async def test_an_allowed_user_gets_no_chunk() -> None:
    allowed = UsageLimitCheckResult(
        allowed=True, status=UsageLimitStatus.OK, blocked_reason=None, exceeded_limit=None
    )
    with _patch_check(allowed):
        assert await usage_limit_error_chunk(uuid4()) is None
