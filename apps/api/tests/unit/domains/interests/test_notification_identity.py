"""The identity an interest notification carries, end to end.

An interest card in the chat offers 👍/👎/🚫. Pressing one calls
``POST /interests/{interest_id}/feedback`` and passes the card's metadata
``run_id`` so the verdict lands on the exact notification in the audit trail.

Until this contract was pinned, TWO unrelated ``run_id`` values existed for the
same notification:

- the archived card carried ``proactive_interest_<id[:12]>_<hex8>``, generated
  by the runner (``generate_proactive_run_id``) and injected into the result
  metadata before dispatch;
- the audit row was created with ``interest_<full uuid>_<hex8>``, generated
  independently inside ``on_notification_sent``.

``update_feedback_by_run_id`` therefore matched ZERO rows, forever and in
silence (the route logs ``audit_updated=False`` and the frontend deliberately
never toasts a feedback failure). Measured on the development database on
2026-08-03: 182 interest notifications, not one of them carrying a verdict —
while the interest itself was correctly updated, so nothing looked broken.

The heartbeat task already does the right thing (``result.metadata["run_id"]``);
the asymmetry between the two proactive tasks WAS the defect.

What the previous test suite checked — that the route forwards the run_id it is
given — was true and useless: nobody ever compared the two generators. The
first test below is that comparison.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.interests.proactive_task import InterestProactiveTask
from src.infrastructure.proactive.base import ContentSource, ProactiveTaskResult
from src.infrastructure.proactive.tracking import generate_proactive_run_id

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _fake_db_ctx():
    session = MagicMock()
    session.commit = AsyncMock()
    yield session


def _result(interest_id: uuid.UUID, *, run_id: str | None) -> ProactiveTaskResult:
    """What the runner hands to the hook, metadata already injected."""
    result = ProactiveTaskResult(
        success=True,
        content="something worth reading",
        target_id=str(interest_id),
        source=ContentSource.PERPLEXITY,
    )
    if run_id is not None:
        result.metadata["run_id"] = run_id
    return result


async def _capture_created_row(
    interest_id: uuid.UUID, result: ProactiveTaskResult
) -> dict[str, object]:
    """Run ``on_notification_sent`` and return the audit row it asked for."""
    target = MagicMock()
    target.id = interest_id
    captured: dict[str, object] = {}

    class _NotifRepo:
        def __init__(self, _db: object) -> None: ...

        async def create(self, **kwargs: object) -> MagicMock:
            captured.update(kwargs)
            return MagicMock()

    class _InterestRepo:
        def __init__(self, _db: object) -> None: ...

        async def get_by_id(self, _id: uuid.UUID) -> None:
            return None

    with (
        patch(
            "src.domains.interests.proactive_task.get_db_context",
            new=lambda: _fake_db_ctx(),
        ),
        patch(
            "src.domains.interests.proactive_task.InterestNotificationRepository",
            _NotifRepo,
        ),
        patch("src.domains.interests.proactive_task.InterestRepository", _InterestRepo),
        patch(
            "src.domains.interests.helpers.generate_interest_embedding",
            new=AsyncMock(return_value=None),
        ),
    ):
        await InterestProactiveTask().on_notification_sent(uuid.uuid4(), target, result)

    return captured


# ---------------------------------------------------------------------------
# The contract
# ---------------------------------------------------------------------------


class TestNotificationIdentity:
    async def test_the_audit_row_is_reachable_from_the_card(self) -> None:
        """The one comparison nobody made: card run_id == audit run_id.

        This is the whole defect. Both halves are produced by real code here —
        the runner's generator and the task's hook — so a future divergence
        fails this test instead of silently emptying the column again.
        """
        interest_id = uuid.uuid4()
        # Exactly what runner.py does before dispatch.
        card_run_id = generate_proactive_run_id("interest", str(interest_id))

        row = await _capture_created_row(interest_id, _result(interest_id, run_id=card_run_id))

        assert row["run_id"] == card_run_id

    async def test_a_missing_run_id_still_produces_a_unique_row(self) -> None:
        """`run_id` is UNIQUE: the fallback must stay unique too.

        A task run outside the runner (older callers, tests) has no injected
        run_id. Falling back to a constant would make the second such
        notification fail its INSERT.
        """
        interest_id = uuid.uuid4()

        first = await _capture_created_row(interest_id, _result(interest_id, run_id=None))
        second = await _capture_created_row(interest_id, _result(interest_id, run_id=None))

        assert first["run_id"]
        assert first["run_id"] != second["run_id"]

    async def test_the_stored_run_id_fits_the_column(self) -> None:
        """The column is varchar(100) — a longer value fails at the database."""
        interest_id = uuid.uuid4()
        card_run_id = generate_proactive_run_id("interest", str(interest_id))

        row = await _capture_created_row(interest_id, _result(interest_id, run_id=card_run_id))

        assert len(str(row["run_id"])) <= 100

    async def test_the_message_is_kept_alongside_the_identity(self) -> None:
        """Identity work must not drop what the history shows (ADR-200)."""
        interest_id = uuid.uuid4()

        row = await _capture_created_row(interest_id, _result(interest_id, run_id="r"))

        assert row["content"] == "something worth reading"
        assert row["interest_id"] == interest_id
