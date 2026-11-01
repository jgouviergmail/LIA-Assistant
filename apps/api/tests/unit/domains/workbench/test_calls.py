"""Every provider call of the workbench goes through one seam (ADR-369).

``provider_call`` times the call, turns a client failure into the workbench's
refusal (structurally, knowing whether the call was an act) and counts the
outcome under closed labels. ``open_tool_client`` opens the tool's provider
through the ADR-304 door and refuses with the right code when it cannot.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.core.exceptions import BaseAPIException, ConnectorAPIError, ExternalServiceError
from src.domains.connectors.active_client import ActiveClient, ClientUnavailable
from src.domains.connectors.models import ConnectorStatus, ConnectorType
from src.domains.workbench import calls, clients
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.features import WorkbenchTool

pytestmark = pytest.mark.unit

USER = uuid.uuid4()
_REQUEST = httpx.Request("POST", "https://provider.example/x")


@pytest.fixture
def counted() -> Any:
    with patch.object(calls, "workbench_requests_total") as counter:
        yield counter


async def test_a_success_is_counted_ok(counted: Any) -> None:
    async with provider_call(WorkbenchTool.TASKS, "list", act=False):
        pass
    counted.labels.assert_called_once_with(tool="tasks", operation="list", outcome="ok")


async def test_a_client_failure_becomes_the_refusal_it_amounts_to(counted: Any) -> None:
    with pytest.raises(BaseAPIException) as raised:
        async with provider_call(WorkbenchTool.TASKS, "update", act=True):
            raise ConnectorAPIError(connector_type="google_tasks", status_code=404, detail="x")
    assert raised.value.detail == {"code": "item_gone"}
    assert isinstance(raised.value.__cause__, ConnectorAPIError)
    counted.labels.assert_called_once_with(tool="tasks", operation="update", outcome="item_gone")


async def test_a_lost_answer_to_an_act_is_counted_unknown(counted: Any) -> None:
    with pytest.raises(BaseAPIException) as raised:
        async with provider_call(WorkbenchTool.MAIL, "send", act=True):
            try:
                raise httpx.ReadTimeout("lost", request=_REQUEST)
            except httpx.ReadTimeout as timeout:
                raise ExternalServiceError(service_name="google_gmail") from timeout
    assert raised.value.detail == {"code": "outcome_unknown"}


async def test_a_refusal_raised_inside_is_kept_and_counted(counted: Any) -> None:
    from src.domains.workbench.errors import NOT_SUPPORTED_BY_PROVIDER, refuse

    with pytest.raises(BaseAPIException) as raised:
        async with provider_call(WorkbenchTool.MAIL, "labels", act=False):
            refuse(NOT_SUPPORTED_BY_PROVIDER)
    assert raised.value.detail == {"code": "not_supported_by_provider"}
    counted.labels.assert_called_once_with(
        tool="mail", operation="labels", outcome="not_supported_by_provider"
    )


@contextlib.asynccontextmanager
async def _door(opened: Any) -> AsyncIterator[Any]:
    yield opened


def _statuses(rows: dict[ConnectorType, ConnectorStatus]) -> Any:
    service = MagicMock()
    service.get_user_connectors = AsyncMock(
        return_value=MagicMock(
            connectors=[MagicMock(connector_type=t, status=s) for t, s in rows.items()]
        )
    )

    class _Units:
        @contextlib.asynccontextmanager
        async def unit_of_work(self) -> AsyncIterator[Any]:
            yield service

    return _Units()


async def test_a_category_tool_opens_through_the_category_door() -> None:
    client = ActiveClient(
        client=object(), connector_type=ConnectorType.GOOGLE_TASKS, preferred_name=None
    )
    with patch.object(clients, "open_active_client", return_value=_door(client)) as door:
        async with open_tool_client(WorkbenchTool.TASKS, USER) as opened:
            assert opened is client
    door.assert_called_once_with("tasks", USER)


async def test_drive_opens_through_the_type_door() -> None:
    client = ActiveClient(
        client=object(), connector_type=ConnectorType.GOOGLE_DRIVE, preferred_name=None
    )
    with patch.object(clients, "open_client_by_type", return_value=_door(client)) as door:
        async with open_tool_client(WorkbenchTool.FILES, USER) as opened:
            assert opened is client
    door.assert_called_once_with(ConnectorType.GOOGLE_DRIVE, USER)


async def test_no_provider_is_refused_as_not_connected() -> None:
    with (
        patch.object(
            clients, "open_active_client", return_value=_door(ClientUnavailable.NO_CONNECTOR)
        ),
        patch.object(clients, "DetachedConnectorService", return_value=_statuses({})),
    ):
        with pytest.raises(BaseAPIException) as raised:
            async with open_tool_client(WorkbenchTool.CALENDAR, USER):
                pass
    assert raised.value.detail == {"code": "not_connected"}


async def test_a_broken_provider_is_refused_as_reconnect_required() -> None:
    rows = {ConnectorType.GOOGLE_CALENDAR: ConnectorStatus.ERROR}
    with (
        patch.object(
            clients, "open_active_client", return_value=_door(ClientUnavailable.NO_CONNECTOR)
        ),
        patch.object(clients, "DetachedConnectorService", return_value=_statuses(rows)),
    ):
        with pytest.raises(BaseAPIException) as raised:
            async with open_tool_client(WorkbenchTool.CALENDAR, USER):
                pass
    assert raised.value.detail == {"code": "reconnect_required"}
