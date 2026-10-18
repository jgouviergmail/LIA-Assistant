"""Closing an alert incident whose resolution was lost, on a real PostgreSQL.

Production, 2026-10-18: one ``ContainerMemoryNearLimit`` incident had stayed
open for 28 days — its « resolved » webhook delivery never arrived, and no
other path could close an alert-sourced incident. The repair is ONE statement
(filter, status, timestamp, audit append, RETURNING); a unit test that mocks the
repository never executes it, so it is proven here, against the real schema.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.diagnostics.models import (
    INCIDENT_SOURCE_ALERT,
    INCIDENT_SOURCE_SELF_CHECK,
    INCIDENT_STATUS_OPEN,
    INCIDENT_STATUS_RESOLVED,
    Incident,
)
from src.domains.diagnostics.repository import DiagnosticsRepository

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 18, 8, 0, tzinfo=UTC)
SILENT_SINCE = NOW - timedelta(hours=1)


def _incident(
    key: str,
    *,
    last_seen: datetime,
    source: str = INCIDENT_SOURCE_ALERT,
    status: str = INCIDENT_STATUS_OPEN,
) -> Incident:
    return Incident(
        correlation_key=key,
        source=source,
        alertname=key,
        severity="warning",
        status=status,
        title=f"{key} title",
        evidence={},
        action_log=[{"action": "earlier", "actor": "test"}],
        opened_at=last_seen,
        last_seen_at=last_seen,
    )


async def _by_key(session: AsyncSession) -> dict[str, Incident]:
    rows = (
        await session.execute(select(Incident).execution_options(populate_existing=True))
    ).scalars()
    return {row.correlation_key: row for row in rows}


class TestAnIncidentWhoseAlertStoppedFiringIsClosed:
    async def test_only_a_silent_alert_incident_absent_from_alertmanager_is_closed(
        self, async_session: AsyncSession
    ) -> None:
        async_session.add_all(
            [
                _incident("ContainerMemoryNearLimit", last_seen=NOW - timedelta(days=28)),
                _incident("SSELatencyP95High", last_seen=NOW - timedelta(hours=2)),
                _incident("PublicEndpointDown", last_seen=NOW - timedelta(minutes=10)),
                _incident(
                    "scheduler_tick",
                    last_seen=NOW - timedelta(days=2),
                    source=INCIDENT_SOURCE_SELF_CHECK,
                ),
            ]
        )
        await async_session.commit()

        resolved = await DiagnosticsRepository(async_session).resolve_silent_alert_incidents(
            firing_alertnames={"SSELatencyP95High"}, silent_since=SILENT_SINCE, now=NOW
        )
        await async_session.commit()

        assert resolved == ["ContainerMemoryNearLimit"]
        rows = await _by_key(async_session)
        closed = rows["ContainerMemoryNearLimit"]
        assert closed.status == INCIDENT_STATUS_RESOLVED
        assert closed.resolved_at == NOW
        # The audit entry is APPENDED: the earlier entries survive.
        assert closed.action_log == [
            {"action": "earlier", "actor": "test"},
            {
                "action": "auto_resolved",
                "actor": "self_check",
                "ts": NOW.isoformat(),
                "outcome": "alert_no_longer_firing",
            },
        ]
        # Still firing, too recent, or owned by the self-check: untouched.
        for key in ("SSELatencyP95High", "PublicEndpointDown", "scheduler_tick"):
            assert rows[key].status == INCIDENT_STATUS_OPEN, key
            assert rows[key].resolved_at is None, key

    async def test_nothing_firing_closes_every_silent_alert_incident(
        self, async_session: AsyncSession
    ) -> None:
        """An empty firing set must render as « no exclusion », not as no match."""
        async_session.add_all(
            [
                _incident("A", last_seen=NOW - timedelta(hours=3)),
                _incident("B", last_seen=NOW - timedelta(hours=3)),
            ]
        )
        await async_session.commit()

        resolved = await DiagnosticsRepository(async_session).resolve_silent_alert_incidents(
            firing_alertnames=set(), silent_since=SILENT_SINCE, now=NOW
        )

        assert sorted(resolved) == ["A", "B"]

    async def test_a_resolved_incident_is_left_as_it_was(self, async_session: AsyncSession) -> None:
        earlier = NOW - timedelta(days=3)
        incident = _incident(
            "ServiceDown", last_seen=NOW - timedelta(days=3), status=INCIDENT_STATUS_RESOLVED
        )
        incident.resolved_at = earlier
        async_session.add(incident)
        await async_session.commit()

        resolved = await DiagnosticsRepository(async_session).resolve_silent_alert_incidents(
            firing_alertnames=set(), silent_since=SILENT_SINCE, now=NOW
        )

        assert resolved == []
        assert (await _by_key(async_session))["ServiceDown"].resolved_at == earlier


class TestTheAuditLogIsAppendedServerSide:
    async def test_append_action_keeps_the_earlier_entries(
        self, async_session: AsyncSession
    ) -> None:
        """Same JSONB binding as the reconciliation: an untyped list was refused."""
        incident = _incident("RedisDown", last_seen=NOW)
        async_session.add(incident)
        await async_session.commit()

        await DiagnosticsRepository(async_session).append_action(
            incident.id, {"action": "noted", "actor": "test"}
        )
        await async_session.commit()

        assert (await _by_key(async_session))["RedisDown"].action_log == [
            {"action": "earlier", "actor": "test"},
            {"action": "noted", "actor": "test"},
        ]
