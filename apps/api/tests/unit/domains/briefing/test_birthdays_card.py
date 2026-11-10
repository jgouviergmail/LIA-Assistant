"""Birthdays card: the neutral birthdays outcome translated into the card's statuses.

The book is the ACTIVE contacts provider's (``connectors/birthdays``, tested
there); this wrapper only says what each outcome means on the dashboard:
no provider hides the card, a failure asks for the right gesture.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest

from src.core.exceptions import MaxRetriesExceededError
from src.domains.briefing.constants import (
    ERROR_CODE_CONNECTOR_NETWORK,
    ERROR_CODE_CONNECTOR_OAUTH_EXPIRED,
    ERROR_CODE_CONNECTOR_RATE_LIMIT,
)
from src.domains.briefing.exceptions import ConnectorAccessError, ConnectorNotConfiguredError
from src.domains.briefing.fetchers import fetch_birthdays
from src.domains.connectors.birthdays import BirthdayFetchError, BirthdayItem

PARIS = ZoneInfo("Europe/Paris")


def _status(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://contacts.example/people")
    return httpx.HTTPStatusError(
        "refused", request=request, response=httpx.Response(code, request=request)
    )


def _failure(reason: str, cause: Exception | None = None) -> BirthdayFetchError:
    """A typed failure, raised the way the shared module raises it."""
    try:
        if cause is None:
            raise BirthdayFetchError(reason, "detail")
        raise BirthdayFetchError(reason, "detail") from cause
    except BirthdayFetchError as error:
        return error


async def _card(outcome: object):
    fetch = (
        AsyncMock(side_effect=outcome)
        if isinstance(outcome, Exception)
        else AsyncMock(return_value=outcome)
    )
    with patch("src.domains.connectors.birthdays.fetch_upcoming_birthdays", fetch):
        return await fetch_birthdays(user=SimpleNamespace(id=uuid4()), user_tz=PARIS)


@pytest.mark.unit
class TestBirthdaysCard:
    async def test_no_contacts_provider_hides_the_card(self):
        with pytest.raises(ConnectorNotConfiguredError) as raised:
            await _card(None)

        assert raised.value.source == "contacts"

    async def test_the_items_are_shown_as_computed(self):
        item = BirthdayItem(contact_name="Zoé", date_iso="--07-23", days_until=1)

        data = await _card([item])

        assert data.items == [item]

    @pytest.mark.parametrize(
        ("failure", "code"),
        [
            # An active provider whose credentials cannot be read: reconnect it.
            (_failure("no_credentials"), ERROR_CODE_CONNECTOR_OAUTH_EXPIRED),
            (_failure("http_error", _status(401)), ERROR_CODE_CONNECTOR_OAUTH_EXPIRED),
            (_failure("http_error", httpx.ConnectError("down")), ERROR_CODE_CONNECTOR_NETWORK),
            # Exhausted retries are classified on what they last met.
            (
                _failure(
                    "retries_exhausted",
                    MaxRetriesExceededError("list_email_directory", 3, _status(429)),
                ),
                ERROR_CODE_CONNECTOR_RATE_LIMIT,
            ),
        ],
    )
    async def test_a_failure_asks_for_the_right_gesture(self, failure, code):
        with pytest.raises(ConnectorAccessError) as raised:
            await _card(failure)

        assert (raised.value.source, raised.value.error_code) == ("contacts", code)
