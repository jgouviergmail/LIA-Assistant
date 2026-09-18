"""The grants routes (ADR-298): the RECORD, open whatever the act's switch says."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.core.constants import PYTHON_SANDBOX_GRANTS_PAGE_MAX_LIMIT
from src.core.dependencies import get_db
from src.core.exceptions import BaseAPIException
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.python_sandbox.egress.hosts import ConnectorHost
from src.domains.agents.python_sandbox.egress.router import router

pytestmark = pytest.mark.unit

MODULE = "src.domains.agents.python_sandbox.egress.router"
USER_ID = uuid.uuid4()
NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def _grant(**overrides: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "id": uuid.uuid4(),
        "host": "api.example.org",
        "share_turn_data": True,
        "created_at": NOW,
        "last_used_at": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)

    @app.exception_handler(BaseAPIException)
    async def _api_error(request: Request, exc: BaseAPIException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    app.dependency_overrides[get_current_active_session] = lambda: SimpleNamespace(
        id=USER_ID, language="fr"
    )
    app.dependency_overrides[get_db] = lambda: MagicMock(commit=AsyncMock())
    return TestClient(app)


class TestListing:
    def test_publishes_the_page_the_exact_total_and_the_bounds(self, client: TestClient) -> None:
        with (
            patch(f"{MODULE}.EgressGrantRepository") as repo_cls,
            patch(
                f"{MODULE}.get_settings",
                return_value=SimpleNamespace(python_sandbox_max_grants_per_user=50),
            ),
        ):
            repo_cls.return_value.list_page = AsyncMock(return_value=([_grant()], 7))
            response = client.get("/sandbox/egress-grants?limit=1&offset=3")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 7 and len(body["items"]) == 1
        assert body["limit"] == 1 and body["offset"] == 3
        assert body["max_limit"] == PYTHON_SANDBOX_GRANTS_PAGE_MAX_LIMIT
        assert body["max_per_user"] == 50
        assert body["items"][0]["host"] == "api.example.org"
        repo_cls.return_value.list_page.assert_awaited_once_with(USER_ID, limit=1, offset=3)

    def test_limit_bounds_are_enforced(self, client: TestClient) -> None:
        assert client.get("/sandbox/egress-grants?limit=0").status_code == 422
        assert (
            client.get(
                f"/sandbox/egress-grants?limit={PYTHON_SANDBOX_GRANTS_PAGE_MAX_LIMIT + 1}"
            ).status_code
            == 422
        )


class TestReachable:
    def test_names_connector_hosts_then_the_operators(self, client: TestClient) -> None:
        brave = ConnectorHost(
            host="api.search.brave.com",
            connector="brave_search",
            auth_method="header",
            auth_name="X-Subscription-Token",
            auth_prefix="",
        )
        with (
            patch(
                f"{MODULE}.active_connector_hosts", new=AsyncMock(return_value={brave.host: brave})
            ),
            patch(f"{MODULE}.ConnectorService"),
            patch(
                f"{MODULE}.get_settings",
                return_value=SimpleNamespace(
                    python_sandbox_egress_hosts=["API.Example.org", "api.search.brave.com"],
                    python_sandbox_egress_ask_enabled=True,
                ),
            ),
        ):
            response = client.get("/sandbox/egress-grants/reachable")

        assert response.status_code == 200
        body = response.json()
        assert body["ask_enabled"] is True
        assert body["items"] == [
            {"host": "api.search.brave.com", "status": "connector", "connector": "brave_search"},
            {"host": "api.example.org", "status": "operator", "connector": None},
        ]


class TestChangingAndRevoking:
    def test_the_scope_is_updated_and_committed(self, client: TestClient) -> None:
        grant = _grant(share_turn_data=False)
        with patch(f"{MODULE}.EgressGrantRepository") as repo_cls:
            repo_cls.return_value.set_scope = AsyncMock(return_value=grant)
            response = client.patch(
                f"/sandbox/egress-grants/{grant.id}", json={"share_turn_data": False}
            )
        assert response.status_code == 200
        assert response.json()["share_turn_data"] is False
        repo_cls.return_value.set_scope.assert_awaited_once_with(
            USER_ID, grant.id, share_turn_data=False
        )

    def test_someone_elses_grant_is_a_404(self, client: TestClient) -> None:
        with patch(f"{MODULE}.EgressGrantRepository") as repo_cls:
            repo_cls.return_value.set_scope = AsyncMock(return_value=None)
            repo_cls.return_value.delete_for_user = AsyncMock(return_value=False)
            assert (
                client.patch(
                    f"/sandbox/egress-grants/{uuid.uuid4()}", json={"share_turn_data": True}
                ).status_code
                == 404
            )
            assert client.delete(f"/sandbox/egress-grants/{uuid.uuid4()}").status_code == 404

    def test_revoking_answers_204(self, client: TestClient) -> None:
        with patch(f"{MODULE}.EgressGrantRepository") as repo_cls:
            repo_cls.return_value.delete_for_user = AsyncMock(return_value=True)
            response = client.delete(f"/sandbox/egress-grants/{uuid.uuid4()}")
        assert response.status_code == 204


class TestTheRecordIsNotGuarded:
    def test_no_route_carries_a_capability_dependency(self) -> None:
        """ADR-280: a switch removes the ACT (the tool's network run), never the record."""
        for route in router.routes:
            names = [
                getattr(getattr(d, "dependency", None), "__name__", "")
                for d in getattr(route, "dependencies", [])
            ]
            assert not any(name.startswith("require_capability_") for name in names), route
