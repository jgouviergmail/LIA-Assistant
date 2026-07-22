"""Detection of an ERROR-status connector at provider resolution (ADR-134 V2).

When a connector breaks, the run that broke it shows the "Reconnect" banner —
but on every later run the connector sits in ``status=ERROR``, is no longer
resolved as the active provider, and the tool only reports "no connector".
``find_error_connector_type`` closes that gap: it tells the raise/emission
sites whether the "missing" provider is in fact a broken one, so the same
actionable banner can be emitted.

``REVOKED`` is deliberately NOT eligible: a user who disconnected a provider
on purpose must not be nagged to reconnect it (arbitration 2026-07-21).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from src.domains.agents.tools.exceptions import ConnectorNotEnabledError
from src.domains.connectors.models import ConnectorStatus, ConnectorType
from src.domains.connectors.provider_resolver import (
    build_connector_not_enabled_error,
    find_error_connector_type,
)


def _connector(connector_type: ConnectorType, status: ConnectorStatus) -> SimpleNamespace:
    return SimpleNamespace(connector_type=connector_type, status=status)


class _FakeConnectorService:
    def __init__(self, connectors: list[SimpleNamespace]) -> None:
        self._connectors = connectors

    async def get_user_connectors(self, user_id: Any) -> SimpleNamespace:
        return SimpleNamespace(connectors=self._connectors)


class _ExplodingConnectorService:
    async def get_user_connectors(self, user_id: Any) -> SimpleNamespace:
        raise RuntimeError("redis down")


class TestFindErrorConnectorType:
    async def test_returns_the_error_status_connector_of_the_category(self) -> None:
        service = _FakeConnectorService(
            [
                _connector(ConnectorType.GOOGLE_CALENDAR, ConnectorStatus.ACTIVE),
                _connector(ConnectorType.GOOGLE_GMAIL, ConnectorStatus.ERROR),
            ]
        )

        result = await find_error_connector_type(uuid4(), "email", service)

        assert result == ConnectorType.GOOGLE_GMAIL.value

    async def test_returns_none_when_no_connector_is_in_error(self) -> None:
        service = _FakeConnectorService(
            [_connector(ConnectorType.GOOGLE_GMAIL, ConnectorStatus.INACTIVE)]
        )

        assert await find_error_connector_type(uuid4(), "email", service) is None

    async def test_revoked_is_deliberately_not_eligible(self) -> None:
        service = _FakeConnectorService(
            [_connector(ConnectorType.GOOGLE_GMAIL, ConnectorStatus.REVOKED)]
        )

        assert await find_error_connector_type(uuid4(), "email", service) is None

    async def test_error_connector_of_another_category_is_ignored(self) -> None:
        service = _FakeConnectorService(
            [_connector(ConnectorType.GOOGLE_CALENDAR, ConnectorStatus.ERROR)]
        )

        assert await find_error_connector_type(uuid4(), "email", service) is None

    async def test_legacy_gmail_alias_resolves_to_canonical_type(self) -> None:
        service = _FakeConnectorService([_connector(ConnectorType.GMAIL, ConnectorStatus.ERROR)])

        result = await find_error_connector_type(uuid4(), "email", service)

        assert result == ConnectorType.GOOGLE_GMAIL.value

    async def test_unknown_category_returns_none(self) -> None:
        service = _FakeConnectorService(
            [_connector(ConnectorType.GOOGLE_GMAIL, ConnectorStatus.ERROR)]
        )

        assert await find_error_connector_type(uuid4(), "martian", service) is None


class TestBuildConnectorNotEnabledError:
    async def test_enriches_the_error_with_the_broken_connector(self) -> None:
        service = _FakeConnectorService(
            [_connector(ConnectorType.GOOGLE_TASKS, ConnectorStatus.ERROR)]
        )

        exc = await build_connector_not_enabled_error(
            "No Tasks service is enabled.",
            connector_name="Tasks",
            functional_category="tasks",
            user_id=uuid4(),
            connector_service=service,
        )

        assert isinstance(exc, ConnectorNotEnabledError)
        assert exc.connector_name == "Tasks"
        assert exc.functional_category == "tasks"
        assert exc.error_connector_type == ConnectorType.GOOGLE_TASKS.value
        assert str(exc) == "No Tasks service is enabled."

    async def test_no_broken_connector_leaves_the_error_unenriched(self) -> None:
        service = _FakeConnectorService([])

        exc = await build_connector_not_enabled_error(
            "No Tasks service is enabled.",
            connector_name="Tasks",
            functional_category="tasks",
            user_id=uuid4(),
            connector_service=service,
        )

        assert exc.error_connector_type is None

    async def test_lookup_failure_never_masks_the_original_error(self) -> None:
        exc = await build_connector_not_enabled_error(
            "No Tasks service is enabled.",
            connector_name="Tasks",
            functional_category="tasks",
            user_id=uuid4(),
            connector_service=_ExplodingConnectorService(),
        )

        assert isinstance(exc, ConnectorNotEnabledError)
        assert exc.error_connector_type is None
