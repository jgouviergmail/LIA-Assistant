"""An Apple operation that ANSWERS « not there » is not a failure to retry (ADR-344).

``_execute_with_retry`` retried every exception three times with a growing
pause — a draft or a file that is not there cost seven seconds of sleeping
before the same answer, and counted against the circuit breaker as an outage.
"""

from __future__ import annotations

import ssl
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.mailbox_drafts import MailboxDraftNotFoundError
from src.domains.connectors.schemas import AppleCredentials

pytestmark = pytest.mark.unit


@pytest.fixture
def breaker() -> MagicMock:
    breaker = MagicMock()
    breaker.check = AsyncMock()
    breaker.record_success = AsyncMock()
    breaker.record_failure = AsyncMock()
    return breaker


@pytest.fixture
def client(breaker: MagicMock) -> Iterator[AppleEmailClient]:
    instance = AppleEmailClient(
        user_id=uuid4(),
        credentials=AppleCredentials(apple_id="jane@icloud.com", app_password="abcd-efgh"),
        connector_service=MagicMock(),
    )
    with (
        patch.object(instance, "_rate_limit", AsyncMock()),
        patch.object(instance, "_get_circuit_breaker", MagicMock(return_value=breaker)),
    ):
        yield instance


@pytest.mark.parametrize("answer", [MailboxDraftNotFoundError("7"), ValueError("not an address")])
async def test_a_final_answer_is_raised_at_once(
    client: AppleEmailClient, breaker: MagicMock, answer: Exception
) -> None:
    calls: list[Any] = []

    async def absent() -> None:
        calls.append(1)
        raise answer

    with (
        patch("asyncio.sleep", AsyncMock()) as slept,
        pytest.raises(type(answer)),
    ):
        await client._execute_with_retry("get_draft", absent)

    assert len(calls) == 1
    slept.assert_not_awaited()
    breaker.record_failure.assert_not_awaited()


async def test_a_transient_failure_is_still_retried(client: AppleEmailClient) -> None:
    calls: list[Any] = []

    async def flaky() -> str:
        calls.append(1)
        if len(calls) < 2:
            raise OSError("connection reset")
        return "ok"

    with patch("asyncio.sleep", AsyncMock()):
        assert await client._execute_with_retry("list_drafts", flaky) == "ok"

    assert len(calls) == 2


async def test_a_certificate_refusal_is_one_failure_without_invalidating_credentials(
    client: AppleEmailClient, breaker: MagicMock
) -> None:
    operation = AsyncMock(side_effect=ssl.SSLCertVerificationError("untrusted certificate"))
    with (
        patch("asyncio.sleep", AsyncMock()) as slept,
        patch.object(client, "_handle_auth_failure", AsyncMock()) as invalidate,
        pytest.raises(ssl.SSLCertVerificationError),
    ):
        await client._execute_with_retry("list_drafts", operation)
    operation.assert_awaited_once()
    slept.assert_not_awaited()
    invalidate.assert_not_awaited()
    breaker.record_failure.assert_awaited_once()
    breaker.record_success.assert_not_awaited()
