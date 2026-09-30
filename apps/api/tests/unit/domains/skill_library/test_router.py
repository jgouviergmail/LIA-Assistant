"""The skill library's routes (ADR-327): guarded twice, bound to the caller, coded refusals.

- every route sits under the skills switch AND the library's own;
- every call is bound to the AUTHENTICATED account, read on a session of its
  own — no route holds a request session while it waits on the network;
- every route reaches a portal or GitHub, so every route is rate limited;
- a refusal names itself in ``detail.code`` with its facts, and is counted
  with its operation.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.skill_library import router as router_module
from src.domains.skill_library import service
from src.domains.skill_library.errors import AUDIT_BLOCKED, STATUSES, LibraryRefusal
from src.domains.skill_library.router import router
from src.domains.skill_library.schemas import (
    LibraryInstalledResponse,
    LibraryInstallResponse,
    LibrarySearchResponse,
)

pytestmark = pytest.mark.unit

USER_ID = uuid.UUID("00000000-0000-4000-8000-0000000000c1")
SHA = "a" * 40


def app_for(*, guarded: bool) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_active_session_for_stream] = lambda: SimpleNamespace(
        id=USER_ID, language="fr"
    )
    app.dependency_overrides[router_module.rate_limit_library] = lambda: None
    if not guarded:
        for dependency in router.dependencies:
            assert dependency.dependency is not None
            app.dependency_overrides[dependency.dependency] = lambda: None
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app_for(guarded=False))


def _count(operation: str, outcome: str) -> float:
    value = REGISTRY.get_sample_value(
        "skill_library_operations_total", {"operation": operation, "outcome": outcome}
    )
    return value or 0.0


class TestTheSwitches:
    @pytest.mark.parametrize("closed", ["skills", "skill_library"])
    def test_either_switch_off_refuses_every_route(
        self, monkeypatch: pytest.MonkeyPatch, closed: str
    ) -> None:
        async def enabled(capability: Any) -> bool:
            return str(getattr(capability, "value", capability)) != closed

        monkeypatch.setattr("src.domains.feature_switches.guard.is_capability_enabled", enabled)
        response = TestClient(app_for(guarded=True)).get("/skill-library/installed")

        assert response.status_code == 403
        assert response.json()["detail"]["capability"] == closed


class TestTheRoutes:
    def test_every_route_is_rate_limited_and_holds_no_request_session(self) -> None:
        for route in router.routes:
            assert isinstance(route, APIRoute)
            dependencies = {d.call for d in route.dependant.dependencies}
            assert router_module.rate_limit_library in dependencies, route.path
            assert get_db not in dependencies, route.path

    def test_a_search_is_the_caller_s(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[tuple[uuid.UUID, str, str | None]] = []

        async def search(user_id: uuid.UUID, q: str, portal: str | None) -> LibrarySearchResponse:
            seen.append((user_id, q, portal))
            return LibrarySearchResponse(portal="skills_sh", items=[])

        monkeypatch.setattr(service, "search", search)
        before = _count("search", "ok")
        response = client.get("/skill-library/search", params={"q": "pdf"})

        assert response.status_code == 200
        assert seen == [(USER_ID, "pdf", None)]
        assert _count("search", "ok") == before + 1

    def test_an_install_answers_201(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def install(user_id: uuid.UUID, request: Any) -> LibraryInstallResponse:
            assert (user_id, request.commit_sha) == (USER_ID, SHA)
            return LibraryInstallResponse(skill_id=uuid.uuid4(), name="pdf", commit_sha=SHA)

        monkeypatch.setattr(service, "install", install)
        response = client.post(
            "/skill-library/install", json={"repository": "acme/skills", "commit_sha": SHA}
        )
        assert response.status_code == 201

    def test_a_commit_that_is_not_one_is_refused_before_the_service(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/skill-library/install", json={"repository": "acme/skills", "commit_sha": "HEAD"}
        )
        assert response.status_code == 422


class TestARefusal:
    def test_names_itself_with_its_facts_and_is_counted(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def installed(_user_id: uuid.UUID) -> LibraryInstalledResponse:
            raise LibraryRefusal(AUDIT_BLOCKED, risk="critical")

        monkeypatch.setattr(service, "installed", installed)
        before = _count("installed", AUDIT_BLOCKED)
        response = client.get("/skill-library/installed")

        assert response.status_code == STATUSES[AUDIT_BLOCKED]
        assert response.json()["detail"] == {"code": AUDIT_BLOCKED, "risk": "critical"}
        assert _count("installed", AUDIT_BLOCKED) == before + 1
