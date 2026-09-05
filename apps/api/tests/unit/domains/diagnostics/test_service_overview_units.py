"""The overview payload carries the unit of every check it reports.

The admin panel renders `value` next to a suffix chosen from `unit`. The unit
belongs to the CHECK registry, not to the measurement, so it is deliberately NOT
persisted in the snapshot's JSONB — which means the read path must join it in.
Without that join the panel receives no unit at all and renders bare numbers: a
regression that hid behind two green unit tests (the schema fills it, the
formatter reads it) while the only path the UI actually uses skipped both.
"""

from __future__ import annotations

import pytest

from src.domains.diagnostics.checks import ALL_CHECKS, unit_for, with_units


@pytest.mark.unit
class TestUnitsAreJoinedOnRead:
    def test_stored_rows_gain_their_unit(self) -> None:
        stored = [
            # Exactly what the JSONB column holds: no `unit` key.
            {"check_id": "api_latency_p95", "status": "ok", "value": 0.21},
            {"check_id": "platform_egress", "status": "ok", "value": 12.3},
        ]

        joined = with_units(stored)

        assert [row["unit"] for row in joined] == ["seconds", "milliseconds"]
        assert [row["value"] for row in joined] == [0.21, 12.3], "the measure is untouched"
        assert stored[0].get("unit") is None, "the input must not be mutated"

    def test_a_row_from_a_retired_check_gets_no_invented_unit(self) -> None:
        joined = with_units([{"check_id": "removed_long_ago", "value": 1.0}])
        assert joined[0]["unit"] == ""

    def test_a_row_without_a_check_id_is_not_a_crash(self) -> None:
        joined = with_units([{"value": 1.0}])
        assert joined[0]["unit"] == ""

    def test_the_join_covers_every_declared_check(self) -> None:
        for check in ALL_CHECKS:
            assert unit_for(check.check_id) == check.unit

    def test_the_overview_uses_the_join(self) -> None:
        """A helper nobody calls protects nothing — the UI reads this path."""
        import inspect

        from src.domains.diagnostics import service

        source = inspect.getsource(service.build_overview)
        assert "with_units(" in source, (
            "the overview must join the units in: the snapshot JSONB does not "
            "carry them, so the panel would render bare numbers"
        )


@pytest.mark.unit
class TestTheOverviewSaysHowManyRunbooksAreMounted:
    """A diagnosis without a runbook is a weaker diagnosis, and for weeks nothing
    on any surface said the mount was empty. The overview publishes the exact
    count so the admin panel can state it."""

    async def test_runbooks_available_is_the_counted_number(self, monkeypatch: object) -> None:
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock

        from src.domains.diagnostics import service

        repo = MagicMock()
        repo.latest_snapshot = AsyncMock(return_value=None)
        repo.list_incidents = AsyncMock(return_value=([], 0))
        monkeypatch.setattr(service, "DiagnosticsRepository", lambda _db: repo)  # type: ignore[attr-defined]
        alertmanager = MagicMock()
        alertmanager.active_alerts = AsyncMock(
            return_value=SimpleNamespace(status="unavailable", alerts=[])
        )
        monkeypatch.setattr(service, "AlertmanagerClient", lambda **_kw: alertmanager)  # type: ignore[attr-defined]
        monkeypatch.setattr(service, "get_active_degradations", AsyncMock(return_value=[]))  # type: ignore[attr-defined]
        monkeypatch.setattr(service, "count_runbooks", lambda: 40)  # type: ignore[attr-defined]

        overview = await service.build_overview(MagicMock())

        assert overview["runbooks_available"] == 40
