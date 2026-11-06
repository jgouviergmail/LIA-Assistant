"""Leaving a mailing list from a message (ADR-369, lot 3; RFC 8058).

The page shows what the message says; an act re-reads it, so nothing the page sends
is ever posted to. The one POST goes to an address checked and pinned (ADR-326),
carrying the RFC's one line and nothing of the person, and only a 2xx counts: a
redirect is a new address nobody checked, and a refusal is said.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from src.core.exceptions import BaseAPIException
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.mail_unsubscribe import Unsubscribe
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import mail_leaving
from src.domains.workbench.errors import (
    NOT_SUPPORTED_BY_PROVIDER,
    PROVIDER_REFUSED,
    refusal_code_of,
)
from src.domains.workbench.schemas.mail import MailUnsubscribe
from src.infrastructure.utils.url_validation import UrlValidationResult

pytestmark = pytest.mark.unit

USER = uuid4()
PAGE = "https://example.org/leave?u=1"
ONE_CLICK = Unsubscribe(web_url=PAGE, mail_to=None, one_click=True)


def _door(ways: Unsubscribe | None) -> Any:
    client = MagicMock(read_unsubscribe=AsyncMock(return_value=ways))

    @contextlib.asynccontextmanager
    async def opened(*_args: Any, **_kwargs: Any) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(
            client=client, connector_type=ConnectorType.GOOGLE_GMAIL, preferred_name=None
        )

    return patch.object(mail_leaving, "open_tool_client", opened)


def _verdict(valid: bool = True) -> UrlValidationResult:
    return UrlValidationResult(
        valid=valid, url=PAGE, error=None if valid else "refused", resolved_ips=("93.184.216.34",)
    )


def _answering(status: int) -> tuple[Any, list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    @contextlib.asynccontextmanager
    async def stream(
        client: httpx.AsyncClient, method: str, verdict: UrlValidationResult, **kwargs: Any
    ) -> AsyncIterator[Any]:
        calls.append({"method": method, "verdict": verdict, **kwargs})
        yield httpx.Response(status)

    return patch.object(mail_leaving, "pinned_stream", stream), calls


class TestRead:
    async def test_says_what_the_message_names(self) -> None:
        with _door(Unsubscribe(web_url=PAGE, mail_to="leave@example.org", one_click=True)):
            ways = await mail_leaving.read_ways(USER, "m1")

        assert ways == MailUnsubscribe(web_url=PAGE, mail_to="leave@example.org", one_click=True)

    async def test_says_nothing_of_a_message_that_names_none(self) -> None:
        with _door(None):
            ways = await mail_leaving.read_ways(USER, "m1")

        assert ways == MailUnsubscribe(web_url=None, mail_to=None, one_click=False)


class TestLeave:
    async def test_posts_the_rfc_s_line_on_a_checked_address(self) -> None:
        answer, calls = _answering(200)
        check = AsyncMock(return_value=_verdict())
        with _door(ONE_CLICK), answer, patch.object(mail_leaving, "validate_url", check):
            await mail_leaving.leave(USER, "m1")

        check.assert_awaited_once_with(PAGE)
        assert calls[0]["method"] == "POST"
        assert calls[0]["content"] == b"List-Unsubscribe=One-Click"
        assert calls[0]["headers"] == {"Content-Type": "application/x-www-form-urlencoded"}

    async def test_refuses_a_message_that_promises_no_one_click(self) -> None:
        answer, calls = _answering(200)
        without = Unsubscribe(web_url=PAGE, mail_to=None, one_click=False)
        with _door(without), answer, pytest.raises(BaseAPIException) as refused:
            await mail_leaving.leave(USER, "m1")

        assert refusal_code_of(refused.value) == NOT_SUPPORTED_BY_PROVIDER
        assert calls == []

    async def test_refuses_an_address_the_check_refuses(self) -> None:
        answer, calls = _answering(200)
        check = AsyncMock(return_value=_verdict(valid=False))
        with (
            _door(ONE_CLICK),
            answer,
            patch.object(mail_leaving, "validate_url", check),
            pytest.raises(BaseAPIException) as refused,
        ):
            await mail_leaving.leave(USER, "m1")

        assert refusal_code_of(refused.value) == PROVIDER_REFUSED
        assert calls == []

    @pytest.mark.parametrize("status", [301, 302, 400, 403, 404, 500])
    async def test_only_a_success_counts(self, status: int) -> None:
        answer, _calls = _answering(status)
        check = AsyncMock(return_value=_verdict())
        with (
            _door(ONE_CLICK),
            answer,
            patch.object(mail_leaving, "validate_url", check),
            pytest.raises(BaseAPIException) as refused,
        ):
            await mail_leaving.leave(USER, "m1")

        assert refusal_code_of(refused.value) == PROVIDER_REFUSED

    async def test_a_lost_answer_is_an_outcome_nobody_knows(self) -> None:
        @contextlib.asynccontextmanager
        async def lost(*_args: Any, **_kwargs: Any) -> AsyncIterator[Any]:
            raise httpx.ReadTimeout("lost")
            yield

        check = AsyncMock(return_value=_verdict())
        with (
            _door(ONE_CLICK),
            patch.object(mail_leaving, "pinned_stream", lost),
            patch.object(mail_leaving, "validate_url", check),
            pytest.raises(BaseAPIException) as refused,
        ):
            await mail_leaving.leave(USER, "m1")

        assert refusal_code_of(refused.value) == "outcome_unknown"
