"""The keyless-connectors migration (ADR-307), executed on a real PostgreSQL.

Its whole behaviour is two statements over the ``connectors`` table, whose
``connector_type`` and ``status`` columns store enum NAMES — a detail a unit
test cannot see: an earlier connector migration matched lower-case VALUES
(``'google_places'``, ``'active'``), which no row the ORM writes carries. The
statements are module
constants, so this test runs the SAME SQL the revision runs, then reads the
rows back through the ORM, which is what proves the stored values are ones
the application can load.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.connectors.models import (
    Connector,
    ConnectorGlobalConfig,
    ConnectorStatus,
    ConnectorType,
)
from src.domains.users.models import User

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "2026_09_23_2200-b2e6d0f4a8c1_keyless_connectors_instance_owned.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("keyless_connectors_instance_owned", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load_migration()
KEYLESS = ConnectorType.get_keyless_types()


async def _account(session: AsyncSession, *, deleted: bool = False) -> UUID:
    user = User(
        email=f"keyless_{uuid4().hex}@example.com",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    session.add(user)
    await session.flush()
    if deleted:
        user.deleted_at = datetime.now(UTC)
        await session.flush()
    return UUID(str(user.id))


def _row(user_id: UUID, connector_type: ConnectorType, status: ConnectorStatus) -> Connector:
    return Connector(
        user_id=user_id,
        connector_type=connector_type,
        status=status,
        scopes=[],
        credentials_encrypted="{}",
        connector_metadata={},
    )


async def _rows(session: AsyncSession, user_id: UUID) -> dict[ConnectorType, Connector]:
    result = await session.execute(select(Connector).where(Connector.user_id == user_id))
    return {row.connector_type: row for row in result.scalars()}


async def _disable_globally(session: AsyncSession, connector_type: ConnectorType) -> None:
    existing = (
        await session.execute(
            select(ConnectorGlobalConfig).where(
                ConnectorGlobalConfig.connector_type == connector_type
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(ConnectorGlobalConfig(connector_type=connector_type, is_enabled=False))
    else:
        existing.is_enabled = False
    await session.flush()


def test_the_frozen_list_is_the_keyless_declaration_of_today() -> None:
    # The revision freezes the stored names; at the time it was written they
    # were exactly the keyless types, platform-key ones flagged as such.
    assert set(MIGRATION.KEYLESS_STORED_TYPES) == {t.name for t in KEYLESS}
    assert set(MIGRATION.PLATFORM_KEY_STORED_TYPES) == {
        t.name for t in KEYLESS if t.uses_global_api_key
    }


@pytest.mark.asyncio
async def test_upgrade_removes_every_keyless_row_whatever_its_status_and_nothing_else(
    async_session: AsyncSession,
) -> None:
    user_id = await _account(async_session)
    async_session.add_all(
        [
            _row(user_id, ConnectorType.GOOGLE_PLACES, ConnectorStatus.INACTIVE),
            _row(user_id, ConnectorType.GOOGLE_WEATHER, ConnectorStatus.REVOKED),
            _row(user_id, ConnectorType.WIKIPEDIA, ConnectorStatus.ACTIVE),
            _row(user_id, ConnectorType.OPENWEATHERMAP, ConnectorStatus.ACTIVE),
            _row(user_id, ConnectorType.BRAVE_SEARCH, ConnectorStatus.INACTIVE),
        ]
    )
    await async_session.flush()

    await async_session.execute(MIGRATION.DELETE_KEYLESS_ROWS, MIGRATION.statement_params())
    async_session.expire_all()

    assert set(await _rows(async_session, user_id)) == {
        ConnectorType.OPENWEATHERMAP,
        ConnectorType.BRAVE_SEARCH,
    }


@pytest.mark.asyncio
async def test_downgrade_recreates_active_rows_the_previous_code_can_read(
    async_session: AsyncSession,
) -> None:
    live = await _account(async_session)
    gone = await _account(async_session, deleted=True)
    await _disable_globally(async_session, ConnectorType.BROWSER)
    # An account that still holds a row keeps it and gets no duplicate.
    async_session.add(_row(live, ConnectorType.WIKIPEDIA, ConnectorStatus.INACTIVE))
    await async_session.flush()

    await async_session.execute(MIGRATION.RECREATE_KEYLESS_ROWS, MIGRATION.statement_params())
    async_session.expire_all()

    rows = await _rows(async_session, live)
    assert set(rows) == KEYLESS - {ConnectorType.BROWSER}
    assert rows[ConnectorType.WIKIPEDIA].status is ConnectorStatus.INACTIVE
    for connector_type in KEYLESS - {ConnectorType.BROWSER, ConnectorType.WIKIPEDIA}:
        row = rows[connector_type]
        assert row.status is ConnectorStatus.ACTIVE
        expected_auth = "global_api_key" if connector_type.uses_global_api_key else "none"
        assert row.connector_metadata["auth_type"] == expected_auth
    assert await _rows(async_session, gone) == {}
