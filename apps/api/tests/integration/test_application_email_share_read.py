"""Email options reuse the actual UI projection and recheck live authority after lookups."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.email_share_read import read_email_share_options
from src.domains.agents.application.email_share_read_schemas import EmailShareReadInput
from src.domains.email_share.service import ShareRoute

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario", ["relay", "mailbox", "unavailable", "revoked_during_read", "disabled"]
)
async def test_email_options_are_actual_and_never_send(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "email_share_enabled", True)
    route = ShareRoute.relay(test_user.email, max_file_bytes=1024)
    if scenario == "mailbox":
        from src.domains.connectors.models import ConnectorType

        route = ShareRoute.mailbox(ConnectorType.GOOGLE_GMAIL, max_file_bytes=1024)
    elif scenario == "unavailable":
        route = ShareRoute.unavailable()
    owner = test_user.id

    async def resolve(user):
        assert not async_session.in_transaction()
        assert user.id == owner
        if scenario == "revoked_during_read":
            test_user.is_active = False
            await async_session.commit()
        return route

    monkeypatch.setattr("src.domains.agents.application.email_share_read.resolve_route", resolve)
    monkeypatch.setattr(
        "src.domains.agents.application.email_share_read.suggestions_available",
        AsyncMock(return_value=True),
    )
    if scenario == "disabled":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    if scenario in {"revoked_during_read", "disabled"}:
        with pytest.raises(AuthorizationError):
            await read_email_share_options(async_session, owner, EmailShareReadInput())
    else:
        result = await read_email_share_options(async_session, owner, EmailShareReadInput())
        assert result.options.route == route.kind
        assert result.options.max_file_bytes == route.max_file_bytes
        assert result.options.own_address == route.own_address


@pytest.mark.parametrize("scenario", ["mailbox", "relay", "rate_limited"])
async def test_recipient_lookup_uses_original_shared_bound_and_never_runs_for_relay(
    async_session, test_user, monkeypatch, scenario
):
    from src.domains.connectors.models import ConnectorType
    from src.domains.email_share.recipients import RecipientSuggestions

    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "email_share_enabled", True)
    owner = test_user.id
    route = (
        ShareRoute.relay(test_user.email, max_file_bytes=1024)
        if scenario == "relay"
        else ShareRoute.mailbox(ConnectorType.GOOGLE_GMAIL, max_file_bytes=1024)
    )
    monkeypatch.setattr(
        "src.domains.agents.application.email_share_read.resolve_route",
        AsyncMock(return_value=route),
    )
    monkeypatch.setattr(
        "src.domains.agents.application.email_share_read.suggestions_available",
        AsyncMock(return_value=True),
    )
    lookup = AsyncMock(
        return_value=RecipientSuggestions(
            query="Cam",
            suggestions=[SimpleNamespace(name="Camille", email="cam@example.test")],
            truncated=True,
        )
    )
    limiter = AsyncMock()
    if scenario == "rate_limited":
        from src.core.exceptions import BaseAPIException

        limiter.side_effect = BaseAPIException(
            status_code=429, detail={"error_code": "RATE_LIMIT_EXCEEDED"}
        )
    monkeypatch.setattr("src.domains.agents.application.email_share_read.limit_recipients", limiter)
    monkeypatch.setattr(
        "src.domains.agents.application.email_share_read.suggest_recipients", lookup
    )
    if scenario == "rate_limited":
        with pytest.raises(BaseAPIException):
            await read_email_share_options(
                async_session, owner, EmailShareReadInput(recipient_query="Cam")
            )
        lookup.assert_not_awaited()
    else:
        result = await read_email_share_options(
            async_session, owner, EmailShareReadInput(recipient_query="Cam")
        )
        if scenario == "relay":
            limiter.assert_not_awaited()
            lookup.assert_not_awaited()
            assert result.recipients is None
        else:
            lookup.assert_awaited_once_with(owner, "Cam")
            assert (
                result.recipients.truncated
                and result.recipients.suggestions[0].email == "cam@example.test"
            )
