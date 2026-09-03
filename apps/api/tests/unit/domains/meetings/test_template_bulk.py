"""Template batches (ADR-259 follow-up): duplicate several built-ins into « My templates »,
delete several user rows — each ref reported done or skipped with a stable reason, the user
cap respected per item, and a preference that pointed at a deleted row reset AND reported so
the UI can say it.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.config import settings
from src.domains.meetings import template_bulk
from src.domains.meetings.template_service import MeetingTemplateService

pytestmark = pytest.mark.unit

USER = uuid.uuid4()


def _row(**over):
    row = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=USER,
        name="Mon modèle",
        description=None,
        category="custom",
        builtin_key=None,
        sections=[
            {"key": "summary", "label": "Résumé", "instruction": "Prose.", "kind": "paragraph"}
        ],
    )
    for key, value in over.items():
        setattr(row, key, value)
    return row


@pytest.fixture
def service() -> MeetingTemplateService:
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    svc = MeetingTemplateService(db)
    svc.repo = AsyncMock()
    svc.repo.list_for_user.return_value = []
    svc.repo.count_for_user.return_value = 0
    svc.repo.get_for_user.return_value = None
    svc.repo.create.side_effect = lambda payload: _row(**payload)
    svc.preference_repo = AsyncMock()
    svc.preference_repo.clear_default_template_if.return_value = False
    return svc


# ---------------------------------------------------------------- duplicate


async def test_bulk_duplicate_creates_one_row_per_builtin_and_deduplicates_refs(
    service: MeetingTemplateService,
) -> None:
    result = await template_bulk.bulk_duplicate(
        service,
        USER,
        ["builtin:default_minutes", "builtin:daily_standup", "builtin:default_minutes"],
        "fr",
    )
    assert [c.category for c in result.created] == ["meeting", "meeting"]
    assert all(c.ref.startswith("user:") for c in result.created)
    assert result.skipped == []
    assert service.repo.create.await_count == 2
    service.db.commit.assert_awaited()


async def test_bulk_duplicate_reports_unknown_and_malformed_refs_and_goes_on(
    service: MeetingTemplateService,
) -> None:
    result = await template_bulk.bulk_duplicate(
        service, USER, ["builtin:nope", "garbage", "builtin:daily_standup"], "fr"
    )
    assert [c.category for c in result.created] == ["meeting"]
    assert [(s.ref, s.code) for s in result.skipped] == [
        ("builtin:nope", "template_not_found"),
        ("garbage", "template_ref_invalid"),
    ]


async def test_bulk_duplicate_stops_at_the_cap_and_reports_the_rest(
    service: MeetingTemplateService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "meetings_max_user_templates", 2)
    # The count follows the rows created so far, as the real repository would.
    service.repo.count_for_user.side_effect = lambda uid: 1 + service.repo.create.await_count
    result = await template_bulk.bulk_duplicate(
        service, USER, ["builtin:default_minutes", "builtin:daily_standup"], "fr"
    )
    assert len(result.created) == 1
    assert [(s.ref, s.code) for s in result.skipped] == [
        ("builtin:daily_standup", "template_limit_reached")
    ]


async def test_a_duplicate_of_a_name_already_owned_gets_a_numbered_name(
    service: MeetingTemplateService,
) -> None:
    service.repo.list_for_user.return_value = [
        _row(name="Compte rendu de réunion"),
        _row(name="Compte rendu de réunion (2)"),
    ]
    result = await template_bulk.bulk_duplicate(service, USER, ["builtin:default_minutes"], "fr")
    assert result.created[0].name == "Compte rendu de réunion (3)"


# ------------------------------------------------------------------- delete


async def test_bulk_delete_removes_user_rows_and_reports_foreign_builtin_and_malformed(
    service: MeetingTemplateService,
) -> None:
    mine = _row()
    service.repo.get_for_user.side_effect = lambda tid, uid: mine if tid == mine.id else None
    foreign = uuid.uuid4()
    result = await template_bulk.bulk_delete(
        service, USER, [f"user:{mine.id}", f"user:{foreign}", "builtin:default_minutes", "x"]
    )
    assert result.deleted == [f"user:{mine.id}"]
    assert [(s.ref, s.code) for s in result.skipped] == [
        (f"user:{foreign}", "template_not_found"),
        ("builtin:default_minutes", "template_readonly"),
        ("x", "template_ref_invalid"),
    ]
    assert result.preference_reset is False
    service.repo.delete.assert_awaited_once_with(mine)
    service.db.commit.assert_awaited()


async def test_bulk_delete_says_when_the_default_preference_was_reset(
    service: MeetingTemplateService,
) -> None:
    mine = _row()
    service.repo.get_for_user.return_value = mine
    service.preference_repo.clear_default_template_if.return_value = True
    result = await template_bulk.bulk_delete(service, USER, [f"user:{mine.id}"])
    assert result.preference_reset is True
    service.preference_repo.clear_default_template_if.assert_awaited_once_with(
        USER, f"user:{mine.id}"
    )


async def test_bulk_delete_reports_a_failed_row_and_keeps_going(
    service: MeetingTemplateService,
) -> None:
    first, second = _row(name="A"), _row(name="B")
    service.repo.get_for_user.side_effect = lambda tid, uid: {first.id: first, second.id: second}[
        tid
    ]

    async def delete(row):
        if row is first:
            raise RuntimeError("disk")

    service.repo.delete.side_effect = delete
    result = await template_bulk.bulk_delete(
        service, USER, [f"user:{first.id}", f"user:{second.id}"]
    )
    assert result.deleted == [f"user:{second.id}"]
    assert [(s.ref, s.code) for s in result.skipped] == [(f"user:{first.id}", "delete_failed")]
