"""The interest notifications this account actually received.

The proactivity panel gained a history in v1.27.8: someone tuning frequency and
sources could otherwise never see what LIA had chosen to say, nor judge whether
it was worth being interrupted for. Interest notifications had exactly the same
blind spot and the same settings page — with one difference that shapes this
module.

**The audit table never kept the text.** `interest_notifications` was built for
deduplication: it stores a SHA-256 hash and an embedding, not the message. The
content exists at write time (`result.content` in the proactive task) and was
simply dropped. A `content` column now keeps it, so rows written from this
version on can be read back; older rows carry NULL and the card renders without
its paragraph rather than inventing one.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.interests.repository import InterestNotificationRepository

pytestmark = pytest.mark.unit


def _repo(rows: list[object], total: int) -> tuple[InterestNotificationRepository, MagicMock]:
    db = MagicMock()
    count_result = MagicMock()
    count_result.scalar.return_value = total
    page_result = MagicMock()
    page_result.scalars.return_value.all.return_value = rows
    db.execute = AsyncMock(side_effect=[count_result, page_result])
    return InterestNotificationRepository(db), db


class TestHistory:
    async def test_returns_the_page_and_the_exact_total(self) -> None:
        """A count shown to the reader is exact or it does not exist (ADR-185)."""
        rows = [object(), object()]
        repo, _ = _repo(rows, total=57)

        page, total = await repo.get_history(user_id=uuid.uuid4(), limit=10, offset=0)

        assert page == rows
        # NOT len(page): the page is capped, the claim is about the whole set.
        assert total == 57

    async def test_an_empty_history_is_zero_not_none(self) -> None:
        repo, _ = _repo([], total=0)

        page, total = await repo.get_history(user_id=uuid.uuid4())

        assert page == []
        assert total == 0

    async def test_every_read_is_scoped_to_the_caller(self) -> None:
        repo, db = _repo([], total=0)
        user_id = uuid.uuid4()

        await repo.get_history(user_id=user_id)

        for call in db.execute.await_args_list:
            assert "user_id" in str(call.args[0])

    async def test_the_interest_is_loaded_with_the_page(self) -> None:
        """The route reads `notification.interest.topic`.

        `interest` is a lazy relationship: under asyncio, touching it after the
        query has returned raises `MissingGreenlet` — a 500 on a page that
        looks perfectly fine in a mocked unit test. Eager-loading it is what
        makes the topic readable at all.
        """
        repo, db = _repo([], total=0)

        await repo.get_history(user_id=uuid.uuid4())

        page_sql = str(db.execute.await_args_list[1].args[0])
        # `selectinload` shows up as a loader option rather than in the SQL, so
        # the statement's own option list is the honest oracle.
        options = db.execute.await_args_list[1].args[0]._with_options
        assert options, f"no loader option on the page query: {page_sql[:120]}"

    async def test_the_newest_notification_comes_first(self) -> None:
        repo, db = _repo([], total=0)

        await repo.get_history(user_id=uuid.uuid4())

        page_sql = str(db.execute.await_args_list[1].args[0])
        assert "ORDER BY" in page_sql.upper()
        assert "created_at DESC" in page_sql


class TestContentIsKept:
    async def test_create_stores_the_message_it_was_given(self) -> None:
        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        repo = InterestNotificationRepository(db)

        await repo.create(
            user_id=uuid.uuid4(),
            interest_id=uuid.uuid4(),
            run_id="interest_x_deadbeef",
            content_hash="a" * 64,
            source="perplexity",
            content="Trois articles sur la fusion nucléaire cette semaine.",
        )

        stored = db.add.call_args.args[0]
        assert stored.content == "Trois articles sur la fusion nucléaire cette semaine."

    async def test_content_stays_optional_for_callers_that_have_none(self) -> None:
        """The column is nullable: a caller predating it must still work."""
        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        repo = InterestNotificationRepository(db)

        await repo.create(
            user_id=uuid.uuid4(),
            interest_id=uuid.uuid4(),
            run_id="interest_y_cafe0000",
            content_hash="b" * 64,
            source="brave",
        )

        assert db.add.call_args.args[0].content is None
