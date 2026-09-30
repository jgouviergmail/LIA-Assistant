"""The routes of a skill proposal's card (ADR-327).

- under the skills switch; bound to the AUTHENTICATED account; rate limited;
- a proposal id is 32 hex characters, anything else is refused before Redis;
- a refusal names itself in ``detail.code`` and is counted with its operation;
- the read carries the files while pending, never once installed.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.skills import proposal_router as router_module
from src.domains.skills import proposal_service
from src.domains.skills.proposal_errors import STALE, STATUSES, ProposalRefusal
from src.domains.skills.proposals import SkillProposal

pytestmark = pytest.mark.unit

USER_ID = uuid.UUID("00000000-0000-4000-8000-0000000000c2")
PROPOSAL_ID = "b" * 32


def _proposal(status: str = "pending") -> SkillProposal:
    proposal = SkillProposal(
        id=PROPOSAL_ID,
        owner_id=str(USER_ID),
        name="ma-skill",
        description="Useful.",
        files={"SKILL.md": "manifest"},
        sizes={"SKILL.md": 8},
        created_at="2026-09-30T10:00:00+00:00",
        expires_at="2026-10-01T10:00:00+00:00",
        replaces=None,
        changes=None,
    )
    return proposal.installed() if status == "installed" else proposal


def app_for(*, guarded: bool) -> FastAPI:
    app = FastAPI()
    app.include_router(router_module.router)
    app.dependency_overrides[get_current_active_session] = lambda: SimpleNamespace(id=USER_ID)
    app.dependency_overrides[get_db] = lambda: "db-session"
    app.dependency_overrides[router_module.rate_limit_proposals] = lambda: None
    if not guarded:
        for dependency in router_module.router.dependencies:
            assert dependency.dependency is not None
            app.dependency_overrides[dependency.dependency] = lambda: None
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app_for(guarded=False))


def _count(operation: str, outcome: str) -> float:
    value = REGISTRY.get_sample_value(
        "skill_proposals_total", {"operation": operation, "outcome": outcome}
    )
    return value or 0.0


def test_the_skills_switch_closes_the_card(monkeypatch: pytest.MonkeyPatch) -> None:
    async def enabled(capability: Any) -> bool:
        return str(getattr(capability, "value", capability)) != "skills"

    monkeypatch.setattr("src.domains.feature_switches.guard.is_capability_enabled", enabled)
    response = TestClient(app_for(guarded=True)).get(f"/skill-proposals/{PROPOSAL_ID}")

    assert response.status_code == 403


def test_every_route_is_rate_limited() -> None:
    for route in router_module.router.routes:
        dependencies = [d.call for d in route.dependant.dependencies]  # type: ignore[attr-defined]
        assert router_module.rate_limit_proposals in dependencies, route.path  # type: ignore[attr-defined]


@pytest.mark.parametrize("bad", ["x", "B" * 32, "b" * 31, "b" * 33, "../" + "b" * 29])
def test_an_id_that_is_no_id_is_refused_before_anything(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    async def never(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("reached the service")

    monkeypatch.setattr(proposal_service, "read", never)

    assert client.get(f"/skill-proposals/{bad}").status_code in {404, 422}


def test_the_read_is_the_callers_and_carries_the_files(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Any] = []

    async def read(owner_id: Any, proposal_id: str, **_: Any) -> SkillProposal:
        seen.append((owner_id, proposal_id))
        return _proposal()

    monkeypatch.setattr(proposal_service, "read", read)
    before = _count("read", "ok")

    response = client.get(f"/skill-proposals/{PROPOSAL_ID}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["files"] == [{"path": "SKILL.md", "size": 8, "content": "manifest"}]
    assert seen == [(USER_ID, PROPOSAL_ID)]
    assert _count("read", "ok") == before + 1


def test_an_installed_proposal_no_longer_carries_its_contents(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def read(*args: Any, **kwargs: Any) -> SkillProposal:
        return _proposal("installed")

    monkeypatch.setattr(proposal_service, "read", read)

    body = client.get(f"/skill-proposals/{PROPOSAL_ID}").json()

    assert body["status"] == "installed"
    assert body["files"] == [{"path": "SKILL.md", "size": 8, "content": None}]


def test_the_install_runs_on_the_route_session_for_the_caller(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Any] = []

    async def install(db: Any, owner_id: Any, proposal_id: str, **_: Any) -> SkillProposal:
        seen.append((db, owner_id, proposal_id))
        return _proposal("installed")

    monkeypatch.setattr(proposal_service, "install", install)
    before = _count("install", "ok")

    response = client.post(f"/skill-proposals/{PROPOSAL_ID}/install")

    assert response.status_code == 200
    assert response.json()["status"] == "installed"
    assert seen == [("db-session", USER_ID, PROPOSAL_ID)]
    assert _count("install", "ok") == before + 1


def test_a_refusal_is_named_and_counted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def install(*args: Any, **kwargs: Any) -> SkillProposal:
        raise ProposalRefusal(STALE)

    monkeypatch.setattr(proposal_service, "install", install)
    before = _count("install", STALE)

    response = client.post(f"/skill-proposals/{PROPOSAL_ID}/install")

    assert response.status_code == STATUSES[STALE]
    assert response.json()["detail"]["code"] == STALE
    assert _count("install", STALE) == before + 1
