"""Offering SMS reads requires live consent without disabling settings that grant it."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.sms_manifests import SMS_ACTION_MANIFESTS
from src.domains.agents.sms import availability
from src.domains.agents.sms.catalogue_manifests import SMS_TOOL_MANIFESTS


@pytest.mark.asyncio
@pytest.mark.parametrize("allowed", [True, False])
async def test_catalogue_consent_is_shared_but_does_not_hide_management(monkeypatch, allowed):
    @asynccontextmanager
    async def context():
        yield object()

    check = AsyncMock(side_effect=None if allowed else AuthorizationError())
    monkeypatch.setattr(availability, "get_db_context", context)
    monkeypatch.setattr(availability, "require_read", check)
    manifests = [*SMS_TOOL_MANIFESTS, *SMS_ACTION_MANIFESTS]
    offered = await availability.without_unconsented_sms(manifests, uuid4())
    assert all(item in offered for item in SMS_ACTION_MANIFESTS)
    assert any(item.agent == "sms_agent" for item in offered) is allowed
    check.assert_awaited_once()
    assert check.await_args.kwargs == {"assistant": True}


@pytest.mark.asyncio
async def test_catalogue_without_sms_never_opens_a_source(monkeypatch):
    check = AsyncMock()
    monkeypatch.setattr(availability, "require_read", check)
    assert await availability.without_unconsented_sms(list(SMS_ACTION_MANIFESTS), uuid4()) == list(
        SMS_ACTION_MANIFESTS
    )
    check.assert_not_awaited()
