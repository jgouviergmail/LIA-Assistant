"""The operator's charts, served through the real router (ADR-263).

Reported from the dev instance, 2026-09-05: « Les figures n'ont pas pu être
calculées » on the administrator's surface while a reader's charts drew fine.
The cause was not the aggregation — it was the authorisation:
``require_superuser`` is an IMPERATIVE helper ``(current_user, action=…)``, and
wiring it as ``Depends`` made FastAPI demand ``current_user`` as a query
parameter. Every well-formed request answered 422, and nothing was ever
checked.

So this file exercises the route the way the browser does — through the app,
with the session dependency overridden — because a handler test would have
passed throughout: the defect lived entirely in the wiring.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.effects.statistics import RegisterStatistics, Series, SeriesKind
from src.domains.agents.effects.statistics_router import admin_router, router

pytestmark = [pytest.mark.unit]


def _figures() -> RegisterStatistics:
    empty = Series(slices=[], total=0, kind=SeriesKind.COUNT)
    return RegisterStatistics(
        calls_by_model=empty,
        calls_by_node=empty,
        tokens_by_model=Series(slices=[], total=0, kind=SeriesKind.STACKED),
        consultations_by_domain=empty,
        consultation_latency_by_tool=Series(slices=[], total=0, kind=SeriesKind.AVERAGE),
        actions_by_status=empty,
        turns_by_outcome=empty,
        turns_by_mode=empty,
        integrity_by_kind=empty,
        activity_by_day=empty,
    )


def _client(*, superuser: bool) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    app.dependency_overrides[get_current_active_session] = lambda: SimpleNamespace(
        id=uuid.uuid4(), is_superuser=superuser, language="fr"
    )
    app.dependency_overrides[get_db] = lambda: SimpleNamespace()
    return TestClient(app, raise_server_exceptions=False)


def _served() -> Any:
    return patch(
        "src.domains.agents.effects.statistics_router.register_statistics",
        return_value=_figures(),
    )


class TestTheOperatorsChartsAreActuallyServed:
    def test_a_superuser_gets_the_figures_rather_than_a_422(self) -> None:
        with (
            _served(),
            patch(
                "src.domains.agents.effects.statistics_router.rate_limit_statistics",
                return_value=None,
            ),
        ):
            response = _client(superuser=True).get("/api/v1/admin/effects/statistics")

        assert response.status_code == 200, response.text
        assert set(response.json()) >= {"calls_by_model", "activity_by_day"}

    def test_an_ordinary_user_is_REFUSED_rather_than_asked_for_a_parameter(self) -> None:
        # 403 is the answer; 422 was the symptom of a guard that never ran.
        with _served():
            response = _client(superuser=False).get("/api/v1/admin/effects/statistics")

        assert response.status_code == 403, response.text

    def test_naming_accounts_is_accepted(self) -> None:
        with (
            _served() as served,
            patch(
                "src.domains.agents.effects.statistics_router.rate_limit_statistics",
                return_value=None,
            ),
        ):
            first, second = uuid.uuid4(), uuid.uuid4()
            response = _client(superuser=True).get(
                f"/api/v1/admin/effects/statistics?user_ids={first}&user_ids={second}"
            )

        assert response.status_code == 200, response.text
        assert served.call_args.kwargs["user_ids"] == [first, second]

    def test_the_reader_s_own_route_takes_no_account_parameter(self) -> None:
        # Their scope is their session; there must be nothing to pass.
        with (
            _served() as served,
            patch(
                "src.domains.agents.effects.statistics_router.rate_limit_statistics",
                return_value=None,
            ),
        ):
            response = _client(superuser=False).get(
                f"/api/v1/effects/statistics?user_ids={uuid.uuid4()}"
            )

        assert response.status_code == 200, response.text
        scope = served.call_args.kwargs["user_ids"]
        assert len(scope) == 1

    def test_the_series_kind_reaches_the_client(self) -> None:
        # A badge that cannot tell a mean from a total is the defect this
        # field exists to close; it must survive the serialisation.
        with (
            _served(),
            patch(
                "src.domains.agents.effects.statistics_router.rate_limit_statistics",
                return_value=None,
            ),
        ):
            payload = _client(superuser=True).get("/api/v1/admin/effects/statistics").json()

        assert payload["consultation_latency_by_tool"]["kind"] == "average"
        assert payload["tokens_by_model"]["kind"] == "stacked"
        assert payload["calls_by_model"]["kind"] == "count"
