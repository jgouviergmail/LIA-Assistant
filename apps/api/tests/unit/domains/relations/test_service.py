"""RelationsService (N-09) — aggregation, identity resolution, honesty.

What must hold:
- open loops and calls fold into ONE relationship when their names match after
  accent/case folding, and the confidence reflects whether the raw spellings
  agreed (EXACT) or only folded (NORMALIZED);
- the overview ranks by most-recent interaction and honors the cap;
- the detail view gathers a person's loops + calls + name-matching memories;
- blank counterparties/callees are dropped, never a phantom relationship.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.relations.schemas import IdentityConfidence
from src.domains.relations.service import RelationsService, _normalize_name

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def _loop(counterparty, subject="dossier", *, days_ago=1, direction="user_owes"):
    return SimpleNamespace(
        id=uuid4(),
        counterparty=counterparty,
        subject=subject,
        direction=direction,
        due_hint=None,
        created_at=NOW - timedelta(days=days_ago),
    )


def _call(callee, objective="réserver", *, days_ago=0, outcome=None, summary=None):
    return SimpleNamespace(
        id=uuid4(),
        callee_display=callee,
        objective=objective,
        outcome=outcome,
        summary=summary,
        created_at=NOW - timedelta(days=days_ago),
    )


def _memory(content):
    return SimpleNamespace(id=uuid4(), content=content)


def _patch_sources(*, loops=(), calls=(), memories=()):
    """Patch the three repositories the service reads through."""
    return (
        patch(
            "src.domains.relations.service.OpenLoopRepository",
            return_value=SimpleNamespace(list_open_for_user=AsyncMock(return_value=list(loops))),
        ),
        patch(
            "src.domains.relations.service.TelephonyRepository",
            return_value=SimpleNamespace(list_recent_for_user=AsyncMock(return_value=list(calls))),
        ),
        patch(
            "src.domains.memories.repository.MemoryRepository",
            return_value=SimpleNamespace(get_all_for_user=AsyncMock(return_value=list(memories))),
        ),
    )


def _patch_db():
    import contextlib

    @contextlib.asynccontextmanager
    async def _ctx():
        yield SimpleNamespace()

    return patch("src.domains.relations.service.get_db_context", _ctx)


@pytest.mark.unit
def test_normalize_name_folds_accents_and_case() -> None:
    assert _normalize_name("Gérard") == _normalize_name("gerard")
    assert _normalize_name("  Marie  ") == "marie"
    assert _normalize_name("") == ""


@pytest.mark.unit
async def test_overview_folds_matching_names_into_one_relationship() -> None:
    svc = RelationsService(uuid4())
    p_loop, p_call, p_db = _patch_sources(
        loops=[_loop("Gérard Dupont", days_ago=3)],
        calls=[_call("gerard dupont", days_ago=1)],
    )
    with _patch_db(), p_loop, p_call, p_db, patch("src.domains.relations.service.datetime") as dt:
        dt.now.return_value = NOW
        dt.min = datetime.min
        overview = await svc.build_overview()

    assert len(overview.relations) == 1
    relation = overview.relations[0]
    assert relation.open_loops_count == 1
    assert relation.calls_count == 1
    # Raw spellings differ ("Gérard Dupont" vs "gerard dupont") ⇒ NORMALIZED.
    assert relation.identity_confidence is IdentityConfidence.NORMALIZED
    # Display prefers the fullest spelling.
    assert relation.display_name == "Gérard Dupont"


@pytest.mark.unit
async def test_overview_ranks_by_recent_interaction_and_caps() -> None:
    svc = RelationsService(uuid4())
    loops = [
        _loop("Alice", days_ago=10),
        _loop("Bob", days_ago=1),
    ]
    p_loop, p_call, p_db = _patch_sources(loops=loops)
    with _patch_db(), p_loop, p_call, p_db, patch("src.domains.relations.service.datetime") as dt:
        dt.now.return_value = NOW
        dt.min = datetime.min
        with patch("src.domains.relations.service.settings") as cfg:
            cfg.relations_max_items = 1
            cfg.relations_max_items_per_section = 10
            overview = await svc.build_overview()

    # Cap honored, and Bob (1 day ago) outranks Alice (10 days ago).
    assert len(overview.relations) == 1
    assert overview.relations[0].display_name == "Bob"


@pytest.mark.unit
async def test_overview_drops_blank_names() -> None:
    svc = RelationsService(uuid4())
    p_loop, p_call, p_db = _patch_sources(loops=[_loop(None), _loop("   ")], calls=[_call("")])
    with _patch_db(), p_loop, p_call, p_db, patch("src.domains.relations.service.datetime") as dt:
        dt.now.return_value = NOW
        dt.min = datetime.min
        overview = await svc.build_overview()

    assert overview.relations == []


@pytest.mark.unit
async def test_detail_gathers_loops_calls_and_matching_memories() -> None:
    svc = RelationsService(uuid4())
    p_loop, p_call, p_db = _patch_sources(
        loops=[_loop("Gérard", subject="prêt perceuse")],
        calls=[_call("gérard", objective="anniversaire")],
        memories=[
            _memory("Gérard adore la randonnée"),
            _memory("Note sans rapport"),
        ],
    )
    with _patch_db(), p_loop, p_call, p_db, patch("src.domains.relations.service.datetime") as dt:
        dt.now.return_value = NOW
        dt.min = datetime.min
        detail = await svc.build_detail("Gérard")

    assert len(detail.open_loops) == 1
    assert len(detail.recent_calls) == 1
    # Only the name-matching memory is attached.
    assert len(detail.memories) == 1
    assert "randonnée" in detail.memories[0].content
