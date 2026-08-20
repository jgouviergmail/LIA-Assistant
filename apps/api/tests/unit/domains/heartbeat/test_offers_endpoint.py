"""GET /heartbeat/offers — the open missed-routine proposals (Lot 5-C2).

An offer is a heartbeat notification carrying a ``habit_offer_id`` and no
decision yet (``user_feedback IS NULL``), inside a recency window. The
inbox is PULL-only: listing costs nothing to the user's attention, and
the decision rides the EXISTING feedback endpoint (ADR-214 Bayesian bump).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from src.core.session_dependencies import get_current_active_session
from src.domains.heartbeat.repository import HeartbeatNotificationRepository, open_offers_stmt
from src.domains.heartbeat.router import router

USER_ID = uuid.uuid4()


@pytest.mark.unit
class TestOpenOffersStatement:
    def test_statement_selects_undecided_offers_in_window(self):
        stmt = open_offers_stmt(USER_ID, since=datetime(2026, 8, 13, tzinfo=UTC), limit=10)
        sql = str(stmt.compile(dialect=postgresql.dialect())).lower()

        assert "habit_offer_id is not null" in sql
        assert "user_feedback is null" in sql
        assert "created_at >=" in sql
        assert "order by" in sql and "desc" in sql
        assert "limit" in sql


@pytest.mark.unit
class TestOffersEndpoint:
    def _client(self) -> TestClient:
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_active_session] = lambda: SimpleNamespace(id=USER_ID)
        from src.core.dependencies import get_db

        app.dependency_overrides[get_db] = lambda: MagicMock()
        return app and TestClient(app)

    def test_lists_open_offers_with_exact_total(self):
        row = SimpleNamespace(
            id=uuid.uuid4(),
            content="Tu prépares d'habitude ta revue le soir — je m'en occupe ?",
            created_at=datetime.now(UTC),
            priority="low",
            sources_used="[]",
            decision_reason=None,
            user_feedback=None,
            habit_offer_id=uuid.uuid4(),
        )
        with patch.object(
            HeartbeatNotificationRepository,
            "get_open_offers",
            new=AsyncMock(return_value=([row], 3)),
        ):
            resp = self._client().get("/heartbeat/offers")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["notifications"]) == 1
        assert body["notifications"][0]["content"].startswith("Tu prépares")
