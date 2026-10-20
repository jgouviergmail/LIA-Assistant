"""Arbitrary phone sender names survive HTTP routing without cache or log copies."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.session_dependencies import get_current_active_session
from src.domains.relations import router as routes
from src.domains.relations.schemas import IdentityConfidence, RelationDetail
from src.infrastructure.observability.pii_filter import sanitize_dict


@pytest.mark.parametrize("name", ["Vendor/UK", "overview-scope", "Jean / Famille"])
async def test_lookup_query_preserves_arbitrary_sender_name_without_route_shadowing(
    name, monkeypatch
):
    detail = RelationDetail(
        display_name=name,
        identity_confidence=IdentityConfidence.EXACT,
        open_loops=[],
        recent_calls=[],
        memories=[],
    )
    service = SimpleNamespace(build_detail=AsyncMock(return_value=detail))
    monkeypatch.setattr(routes, "RelationsService", Mock(return_value=service))
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    app.dependency_overrides[get_current_active_session] = lambda: SimpleNamespace(id=uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/relations/lookup/person", params={"name": name})
    assert response.status_code == 200
    assert response.json()["display_name"] == name
    assert response.headers["cache-control"] == "no-store"
    service.build_detail.assert_awaited_once_with(name)


async def test_legacy_relation_sms_read_also_prohibits_http_caching(monkeypatch):
    detail = RelationDetail(
        display_name="Alice",
        identity_confidence=IdentityConfidence.EXACT,
        open_loops=[],
        recent_calls=[],
        memories=[],
    )
    monkeypatch.setattr(
        routes,
        "RelationsService",
        Mock(return_value=SimpleNamespace(build_detail=AsyncMock(return_value=detail))),
    )
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    app.dependency_overrides[get_current_active_session] = lambda: SimpleNamespace(id=uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/relations/Alice")
    assert response.status_code == 200 and response.headers.get("cache-control") == "no-store"


@pytest.mark.parametrize(
    "path,name_query",
    [
        ("/api/v1/relations/Alice/debrief", {}),
        ("/api/v1/relations/lookup/person/debrief", {"name": "Vendor/UK"}),
    ],
)
async def test_every_debrief_build_entry_point_rejects_an_exhausted_daily_budget(
    path, name_query, monkeypatch
):
    from src.core.exceptions import RateLimitError
    from src.domains.relations.debrief.schemas import DebriefStatus, RelationDebriefRead

    budget = AsyncMock(side_effect=RateLimitError(limit=1, window_seconds=86400, retry_after=60))

    async def exhausted_budget():
        await budget()

    service = SimpleNamespace(
        build=AsyncMock(
            return_value=RelationDebriefRead(status=DebriefStatus.EMPTY, person="Vendor/UK")
        )
    )
    monkeypatch.setattr(routes, "RelationDebriefService", Mock(return_value=service))
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    app.dependency_overrides[get_current_active_session] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[routes.rate_limit_relation_debrief] = exhausted_budget
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, params={**name_query, "force": "true"})
    assert response.status_code == 429
    assert response.headers["cache-control"] == "no-store"
    budget.assert_awaited_once()
    service.build.assert_not_awaited()


@pytest.mark.parametrize("private", ["06 12 34 56 78", "Vendor/UK", "Jean%20Famille"])
def test_relative_request_paths_never_log_private_relation_labels_above_debug(private):
    path = "/api/v1/relations/" + private + "/context"
    result = sanitize_dict({"path": path}, redact_content=True)
    assert private not in result["path"]
    assert result["path"].startswith("/api/v1/relations/")
    assert sanitize_dict({"path": path}, redact_content=False)["path"] == path
