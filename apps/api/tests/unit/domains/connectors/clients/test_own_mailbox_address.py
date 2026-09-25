"""The connected mailbox's own address, asked of its provider (ADR-314).

``send_email_to_me_tool`` writes to the person's OWN mailbox and never takes a
recipient: the address comes from the provider itself, on the three email
clients alike (the parity contract holds the signature). An address the
provider cannot vouch for is None — the tool then refuses rather than guess.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.schemas import AppleCredentials, ConnectorCredentials

pytestmark = pytest.mark.unit


def _gmail(response: dict) -> tuple[GoogleGmailClient, AsyncMock]:
    client = GoogleGmailClient.__new__(GoogleGmailClient)
    client.user_id = uuid4()
    spy = AsyncMock(return_value=response)
    client._make_request = spy  # type: ignore[method-assign]
    return client, spy


def _outlook(response: dict) -> tuple[MicrosoftOutlookClient, AsyncMock]:
    client = MicrosoftOutlookClient(
        user_id=uuid4(),
        credentials=ConnectorCredentials(
            access_token="token",
            refresh_token="refresh",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            token_type="Bearer",
        ),
        connector_service=MagicMock(),
    )
    spy = AsyncMock(return_value=response)
    client._make_request = spy  # type: ignore[method-assign]
    return client, spy


class TestGmail:
    async def test_the_profile_names_the_mailbox(self) -> None:
        client, spy = _gmail({"emailAddress": "me@gmail.com", "historyId": "1"})

        assert await client.get_own_address() == "me@gmail.com"
        assert spy.call_args.args[:2] == ("GET", "/users/me/profile")

    async def test_a_profile_without_an_address_vouches_for_nothing(self) -> None:
        client, _spy = _gmail({"historyId": "1"})

        assert await client.get_own_address() is None


class TestOutlook:
    async def test_the_mail_attribute_wins(self) -> None:
        client, spy = _outlook({"mail": "me@contoso.com", "userPrincipalName": "me@tenant.test"})

        assert await client.get_own_address() == "me@contoso.com"
        assert spy.call_args.args[:2] == ("GET", "/me")
        assert spy.call_args.kwargs["params"] == {"$select": "mail,userPrincipalName"}

    async def test_a_personal_account_answers_with_its_sign_in_address(self) -> None:
        """Personal Microsoft accounts leave ``mail`` null (measured on Graph)."""
        client, _spy = _outlook({"mail": None, "userPrincipalName": "me@outlook.com"})

        assert await client.get_own_address() == "me@outlook.com"

    async def test_a_principal_name_that_is_not_an_address_is_refused(self) -> None:
        client, _spy = _outlook({"mail": None, "userPrincipalName": "service-principal"})

        assert await client.get_own_address() is None


class TestApple:
    async def test_the_apple_id_is_the_mailbox(self) -> None:
        client = AppleEmailClient(
            user_id=uuid4(),
            credentials=AppleCredentials(apple_id="jane@icloud.com", app_password="x-y-z-w"),
            connector_service=MagicMock(),
        )

        assert await client.get_own_address() == "jane@icloud.com"
