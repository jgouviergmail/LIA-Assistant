"""The template library service (ADR-259): built-ins read-only, user rows bounded, refs resolved."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.meetings.schemas import (
    MeetingTemplateCreate,
    MeetingTemplateUpdate,
    SectionKind,
    TemplateCategory,
    TemplateSection,
)
from src.domains.meetings.template_catalogue import BUILTIN_TEMPLATES
from src.domains.meetings.template_service import MeetingTemplateService

pytestmark = pytest.mark.unit

USER = uuid.uuid4()


def _row(**over):
    row = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=USER,
        name="Mon modèle",
        description="Pour mes points",
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
    svc = MeetingTemplateService(db)
    svc.repo = AsyncMock()
    svc.repo.list_for_user.return_value = []
    svc.repo.count_for_user.return_value = 0
    svc.repo.get_for_user.return_value = None
    svc.preference_repo = AsyncMock()
    return svc


def _code(exc: pytest.ExceptionInfo[BaseAPIException]) -> str:
    detail = exc.value.detail
    assert isinstance(detail, dict)
    return str(detail["code"])


async def test_the_library_lists_every_builtin_localized_then_the_user_rows(
    service: MeetingTemplateService,
) -> None:
    service.repo.list_for_user.return_value = [_row()]
    library = await service.library(USER, "fr")
    assert len(library.items) == len(BUILTIN_TEMPLATES) + 1
    builtins = [item for item in library.items if item.builtin]
    assert all(item.ref.startswith("builtin:") for item in builtins)
    assert any(item.name == "Compte rendu de réunion" for item in builtins)
    mine = library.items[-1]
    assert mine.builtin is False and mine.ref.startswith("user:") and mine.sections_count == 1
    assert mine.category is TemplateCategory.CUSTOM
    assert library.max_user_templates == settings.meetings_max_user_templates


async def test_get_answers_a_builtin_and_a_user_row(service: MeetingTemplateService) -> None:
    builtin = await service.get(USER, "builtin:bant_analysis", "en")
    assert builtin.builtin is True and builtin.id is None and builtin.sections
    row = _row()
    service.repo.get_for_user.return_value = row
    mine = await service.get(USER, f"user:{row.id}", "en")
    assert mine.builtin is False and mine.id == row.id and mine.name == "Mon modèle"
    service.repo.get_for_user.assert_awaited_with(row.id, USER)


async def test_get_refuses_a_foreign_row_and_an_unknown_builtin_the_same_way(
    service: MeetingTemplateService,
) -> None:
    with pytest.raises(BaseAPIException) as exc:
        await service.get(USER, f"user:{uuid.uuid4()}", "en")
    assert exc.value.status_code == 404 and _code(exc) == "template_not_found"
    with pytest.raises(BaseAPIException) as exc:
        await service.get(USER, "builtin:nope", "en")
    assert exc.value.status_code == 404 and _code(exc) == "template_not_found"


async def test_a_malformed_reference_is_a_422(service: MeetingTemplateService) -> None:
    with pytest.raises(BaseAPIException) as exc:
        await service.resolve(USER, "nope", "en")
    assert exc.value.status_code == 422 and _code(exc) == "template_ref_invalid"


async def test_create_from_sections_stores_the_category_and_answers_a_user_ref(
    service: MeetingTemplateService,
) -> None:
    created = _row(category="business", name="Découverte")
    service.repo.create.return_value = created
    request = MeetingTemplateCreate(
        name="Découverte",
        category=TemplateCategory.BUSINESS,
        sections=[
            TemplateSection(key="needs", label="Besoins", instruction="x", kind=SectionKind.BULLETS)
        ],
    )
    response = await service.create(USER, request, "fr")
    payload = service.repo.create.await_args.args[0]
    assert payload["user_id"] == USER and payload["category"] == "business"
    assert payload["sections"][0]["kind"] == "bullets" and payload["builtin_key"] is None
    assert response.ref == f"user:{created.id}" and response.builtin is False


async def test_create_by_duplicating_a_builtin_copies_its_sections_and_category(
    service: MeetingTemplateService,
) -> None:
    created = _row(category="business", builtin_key="bant_analysis", name="Analyse BANT")
    service.repo.create.return_value = created
    response = await service.create(
        USER, MeetingTemplateCreate(duplicate_of="builtin:bant_analysis"), "fr"
    )
    payload = service.repo.create.await_args.args[0]
    assert payload["builtin_key"] == "bant_analysis" and payload["category"] == "business"
    assert payload["name"] == "Analyse BANT"
    assert [s["key"] for s in payload["sections"]][:2] == ["budget", "authority"]
    assert payload["sections"][0]["label"] == "Budget"
    assert response.builtin_key == "bant_analysis"


async def test_create_by_duplicating_a_user_row_takes_its_content(
    service: MeetingTemplateService,
) -> None:
    source = _row(name="Source", category="custom")
    service.repo.get_for_user.return_value = source
    service.repo.create.return_value = _row(name="Copie")
    await service.create(
        USER, MeetingTemplateCreate(duplicate_of=f"user:{source.id}", name="Copie"), "fr"
    )
    payload = service.repo.create.await_args.args[0]
    assert payload["name"] == "Copie" and payload["sections"] == source.sections
    assert payload["builtin_key"] is None


async def test_the_user_cap_is_read_from_settings(
    service: MeetingTemplateService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "meetings_max_user_templates", 3)
    service.repo.count_for_user.return_value = 3
    with pytest.raises(BaseAPIException) as exc:
        await service.create(
            USER, MeetingTemplateCreate(duplicate_of="builtin:default_minutes"), "en"
        )
    assert exc.value.status_code == 409 and _code(exc) == "template_limit_reached"
    assert exc.value.detail["max"] == 3
    service.repo.create.assert_not_awaited()


async def test_builtins_are_read_only(service: MeetingTemplateService) -> None:
    update = MeetingTemplateUpdate(
        name="x",
        sections=[TemplateSection(key="a1", label="A", instruction="i", kind=SectionKind.BULLETS)],
    )
    with pytest.raises(BaseAPIException) as exc:
        await service.update(USER, "builtin:default_minutes", update)
    assert exc.value.status_code == 409 and _code(exc) == "template_readonly"
    with pytest.raises(BaseAPIException) as exc:
        await service.delete(USER, "builtin:default_minutes")
    assert exc.value.status_code == 409 and _code(exc) == "template_readonly"


async def test_update_replaces_the_row_content(service: MeetingTemplateService) -> None:
    row = _row()
    service.repo.get_for_user.return_value = row
    service.repo.update.return_value = _row(name="Renommé", category="learning")
    update = MeetingTemplateUpdate(
        name="Renommé",
        category=TemplateCategory.LEARNING,
        sections=[TemplateSection(key="a1", label="A", instruction="i", kind=SectionKind.BULLETS)],
    )
    response = await service.update(USER, f"user:{row.id}", update)
    payload = service.repo.update.await_args.args[1]
    assert payload["name"] == "Renommé" and payload["category"] == "learning"
    assert response.name == "Renommé" and response.category is TemplateCategory.LEARNING


async def test_delete_removes_the_row_and_resets_a_preference_pointing_at_it(
    service: MeetingTemplateService,
) -> None:
    row = _row()
    service.repo.get_for_user.return_value = row
    await service.delete(USER, f"user:{row.id}")
    service.repo.delete.assert_awaited_once_with(row)
    service.preference_repo.clear_default_template_if.assert_awaited_once_with(
        USER, f"user:{row.id}"
    )
    service.db.commit.assert_awaited()


async def test_resolve_returns_the_sections_of_either_kind(
    service: MeetingTemplateService,
) -> None:
    resolved = await service.resolve(USER, "builtin:daily_standup", "de")
    assert str(resolved.ref) == "builtin:daily_standup" and resolved.auto_selectable is True
    assert resolved.description and "Was erledigt" in resolved.description
    assert resolved.sections[0].label == "Was erledigt wurde"
    row = _row()
    service.repo.get_for_user.return_value = row
    resolved = await service.resolve(USER, f"user:{row.id}", "de")
    assert resolved.name == "Mon modèle" and resolved.sections[0].key == "summary"
    assert resolved.category is TemplateCategory.CUSTOM


async def test_candidates_exclude_transcript_builtins_and_include_user_rows(
    service: MeetingTemplateService,
) -> None:
    service.repo.list_for_user.return_value = [_row()]
    candidates = await service.candidates(USER, "en")
    refs = {str(c.ref) for c in candidates}
    assert "builtin:transcript_clean" not in refs and "builtin:default_minutes" in refs
    assert any(ref.startswith("user:") for ref in refs)
    assert all(c.auto_selectable for c in candidates)


async def test_create_by_duplicating_takes_a_numbered_name_when_the_name_is_already_owned(
    service: MeetingTemplateService,
) -> None:
    service.repo.list_for_user.return_value = [_row(name="Compte rendu de réunion")]
    service.repo.create.side_effect = lambda payload: _row(**payload)
    created = await service.create(
        USER, MeetingTemplateCreate(duplicate_of="builtin:default_minutes"), "fr"
    )
    assert created.name == "Compte rendu de réunion (2)"


async def test_clear_default_template_if_reports_whether_it_reset_anything() -> None:
    from src.domains.meetings.repository import MeetingPreferenceRepository

    db = MagicMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(rowcount=1))
    assert await MeetingPreferenceRepository(db).clear_default_template_if(USER, "user:x") is True
    db.execute = AsyncMock(return_value=SimpleNamespace(rowcount=0))
    assert await MeetingPreferenceRepository(db).clear_default_template_if(USER, "user:x") is False
