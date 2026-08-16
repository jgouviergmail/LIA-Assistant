"""Product analytics service seams (ADR-178) — guarded, best-effort, bounded.

What must hold:
- the feature flag OFF short-circuits before any DB access;
- a repository failure is swallowed (telemetry never breaks a user request);
- the locale goes through the normalize_language chokepoint (zh → zh-CN);
- feedback without a run_id is a silent no-op (legacy messages);
- a thumbs_up transition increments the E1 counter exactly per transition.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import src.domains.product.repository as repo_module
import src.infrastructure.database as db_module
from src.core.config import settings
from src.domains.product.service import (
    record_outcome_produced,
    record_response_feedback,
)


class _StubRepo:
    """Capture repository calls without a database."""

    last: _StubRepo | None = None

    def __init__(self, db: Any) -> None:
        self.db = db
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.feedback_transitions: list[tuple[str, str]] = [("answer", "unknown")]
        self.raise_on_upsert = False
        _StubRepo.last = self

    async def upsert_produced(self, **kwargs: Any) -> None:
        if self.raise_on_upsert:
            raise RuntimeError("db down")
        self.calls.append(("upsert_produced", kwargs))

    async def record_event(self, **kwargs: Any) -> None:
        self.calls.append(("record_event", kwargs))

    async def apply_feedback(self, **kwargs: Any) -> list[tuple[str, str]]:
        self.calls.append(("apply_feedback", kwargs))
        return self.feedback_transitions


@pytest.fixture
def stub_db(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch get_db_context + ProductRepository at their import sources."""
    session = MagicMock()
    session.commit = AsyncMock()

    @asynccontextmanager
    async def _fake_ctx():  # noqa: ANN202
        yield session

    monkeypatch.setattr(db_module, "get_db_context", _fake_ctx)
    monkeypatch.setattr(repo_module, "ProductRepository", _StubRepo)
    _StubRepo.last = None
    return session


@pytest.fixture
def flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "product_analytics_enabled", True, raising=False)


async def test_flag_off_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "product_analytics_enabled", False, raising=False)

    def _boom() -> None:  # get_db_context must never be entered
        raise AssertionError("DB touched with flag off")

    monkeypatch.setattr(db_module, "get_db_context", _boom)
    await record_outcome_produced(
        user_id=uuid4(),
        run_id="r1",
        session_id="s",
        intention=None,
        execution_mode="pipeline",
        user_language="fr",
        user_agent=None,
        latency_ms=10,
    )
    await record_response_feedback(user_id=uuid4(), run_id="r1", verdict="thumbs_up")


async def test_produced_records_outcome_and_event(stub_db: MagicMock, flag_on: None) -> None:
    await record_outcome_produced(
        user_id=uuid4(),
        run_id="run-42",
        session_id="web-session",
        # The router's actual vocabulary (INTENTION_ACTION) — "actionable" was
        # a value no producer ever emitted (2026-08-16 regression fix).
        intention="action",
        execution_mode="react",
        user_language="zh",
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
        latency_ms=1234,
    )
    repo = _StubRepo.last
    assert repo is not None
    names = [name for name, _ in repo.calls]
    assert names == ["upsert_produced", "record_event"]
    kwargs = repo.calls[0][1]
    assert kwargs["result_type"] == "action"
    assert kwargs["channel"] == "web"
    assert kwargs["device_class"] == "mobile"
    # normalize_language chokepoint: frontend 'zh' → backend-canonical 'zh-CN'
    assert kwargs["locale"] == "zh-CN"
    stub_db.commit.assert_awaited_once()


async def test_produced_passes_bounded_domain(stub_db: MagicMock, flag_on: None) -> None:
    """A DOMAIN_REGISTRY key reaches the row verbatim (seam closed)."""
    await record_outcome_produced(
        user_id=uuid4(),
        run_id="run-dom",
        session_id="web-session",
        intention="action",
        execution_mode="pipeline",
        user_language="fr",
        user_agent=None,
        latency_ms=5,
        domain="email",
    )
    repo = _StubRepo.last
    assert repo is not None
    assert repo.calls[0][1]["domain"] == "email"


async def test_produced_empty_domain_falls_back_to_unknown(
    stub_db: MagicMock, flag_on: None
) -> None:
    """Absence defaults to 'unknown'. The VOCABULARY invariant is enforced at
    the producer (the streaming capture filters against DOMAIN_REGISTRY —
    see test_streaming_service) because importing the registry here would
    create the agents<->product runtime cycle the coupling ratchet forbids."""
    await record_outcome_produced(
        user_id=uuid4(),
        run_id="run-dom-bad",
        session_id=None,
        intention=None,
        execution_mode="pipeline",
        user_language=None,
        user_agent=None,
        latency_ms=None,
        domain="",
    )
    repo = _StubRepo.last
    assert repo is not None
    assert repo.calls[0][1]["domain"] == "unknown"


async def test_produced_missing_domain_defaults_to_unknown(
    stub_db: MagicMock, flag_on: None
) -> None:
    """Callers that predate the seam closure keep the historical value."""
    await record_outcome_produced(
        user_id=uuid4(),
        run_id="run-dom-none",
        session_id=None,
        intention=None,
        execution_mode="pipeline",
        user_language=None,
        user_agent=None,
        latency_ms=None,
    )
    repo = _StubRepo.last
    assert repo is not None
    assert repo.calls[0][1]["domain"] == "unknown"


async def test_repository_failure_is_swallowed(stub_db: MagicMock, flag_on: None) -> None:
    # Force the failure path through a stub that raises on upsert.
    class _Boom(_StubRepo):
        def __init__(self, db: Any) -> None:
            super().__init__(db)
            self.raise_on_upsert = True

    import src.domains.product.repository as repo_mod

    repo_mod.ProductRepository = _Boom  # type: ignore[misc]
    await record_outcome_produced(
        user_id=uuid4(),
        run_id="run-err",
        session_id=None,
        intention=None,
        execution_mode="pipeline",
        user_language=None,
        user_agent=None,
        latency_ms=None,
    )  # must not raise
    stub_db.commit.assert_not_awaited()


async def test_feedback_without_run_id_is_noop(stub_db: MagicMock, flag_on: None) -> None:
    await record_response_feedback(user_id=uuid4(), run_id=None, verdict="thumbs_up")
    assert _StubRepo.last is None


async def test_feedback_thumbs_up_counts_transitions(stub_db: MagicMock, flag_on: None) -> None:
    from src.infrastructure.observability.metrics_product import product_outcomes_total

    before = product_outcomes_total.labels(
        result_type="answer", domain="unknown", evidence="E1"
    )._value.get()
    await record_response_feedback(user_id=uuid4(), run_id="run-7", verdict="thumbs_up")
    repo = _StubRepo.last
    assert repo is not None
    assert repo.calls[0][0] == "apply_feedback"
    assert repo.calls[1][0] == "record_event"
    after = product_outcomes_total.labels(
        result_type="answer", domain="unknown", evidence="E1"
    )._value.get()
    assert after == before + 1
