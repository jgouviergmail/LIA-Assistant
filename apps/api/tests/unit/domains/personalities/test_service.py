"""
Unit tests for PersonalityService.

Coverage target: 85%+

This test suite covers:
- CRUD operations (create, read, update, delete)
- Default personality handling
- User preference lookup
- Prompt instruction retrieval
- Translation management
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.exceptions import UnprocessableEntityError
from src.core.i18n import language_scope
from src.core.i18n_api_messages import APIMessages
from src.domains.personalities.constants import default_personality_prompt
from src.domains.personalities.models import Personality, PersonalityTranslation
from src.domains.personalities.schemas import (
    PersonalityListItem,
    PersonalityTranslationCreate,
    PersonalityUpdate,
)
from src.domains.personalities.service import PersonalityService

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db():
    """Create a mock AsyncSession."""
    mock = AsyncMock()
    mock.execute = AsyncMock()
    mock.commit = AsyncMock()
    mock.refresh = AsyncMock()
    mock.flush = AsyncMock()
    mock.add = MagicMock()
    mock.delete = AsyncMock()
    return mock


@pytest.fixture
def service(mock_db):
    """Create PersonalityService with mock database."""
    return PersonalityService(mock_db)


@pytest.fixture
def sample_personality():
    """Create a sample personality for testing."""
    p = Personality(
        id=uuid4(),
        code="enthusiastic",
        emoji="🎉",
        is_default=False,
        is_active=True,
        sort_order=1,
        prompt_instruction="Be enthusiastic and energetic!",
    )
    # Add translations
    p.translations = [
        PersonalityTranslation(
            id=uuid4(),
            personality_id=p.id,
            language_code="fr",
            title="Enthousiaste",
            description="Un assistant plein d'énergie",
            is_auto_translated=False,
        ),
        PersonalityTranslation(
            id=uuid4(),
            personality_id=p.id,
            language_code="en",
            title="Enthusiastic",
            description="An energetic assistant",
            is_auto_translated=True,
        ),
    ]
    return p


@pytest.fixture
def default_personality():
    """Create a default personality for testing."""
    p = Personality(
        id=uuid4(),
        code="normal",
        emoji="⚖️",
        is_default=True,
        is_active=True,
        sort_order=0,
        prompt_instruction="Be balanced and professional.",
    )
    p.translations = [
        PersonalityTranslation(
            id=uuid4(),
            personality_id=p.id,
            language_code="fr",
            title="Normal",
            description="Un assistant équilibré",
            is_auto_translated=False,
        ),
    ]
    return p


# ============================================================================
# Read Operations Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetById:
    """Tests for get_by_id method."""

    async def test_get_by_id_success(self, service, mock_db, sample_personality):
        """Test successful personality retrieval."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_personality
        mock_db.execute.return_value = mock_result

        result = await service.get_by_id(sample_personality.id)

        assert result == sample_personality
        mock_db.execute.assert_called_once()

    async def test_get_by_id_not_found(self, service, mock_db):
        """Test personality not found raises exception."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(Exception):  # HTTPException
            await service.get_by_id(uuid4())


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetByCode:
    """Tests for get_by_code method."""

    async def test_get_by_code_success(self, service, mock_db, sample_personality):
        """Test successful code lookup."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_personality
        mock_db.execute.return_value = mock_result

        result = await service.get_by_code("enthusiastic")

        assert result == sample_personality

    async def test_get_by_code_not_found(self, service, mock_db):
        """Test code not found returns None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get_by_code("nonexistent")

        assert result is None


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetDefault:
    """Tests for get_default method."""

    async def test_get_default_success(self, service, mock_db, default_personality):
        """Test successful default retrieval."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = default_personality
        mock_db.execute.return_value = mock_result

        result = await service.get_default()

        assert result == default_personality
        assert result.is_default is True

    async def test_get_default_none(self, service, mock_db):
        """Test no default returns None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get_default()

        assert result is None


@pytest.mark.asyncio
@pytest.mark.unit
class TestListActive:
    """Tests for list_active method."""

    async def test_list_active_with_translations(
        self, service, mock_db, sample_personality, default_personality
    ):
        """Test listing active personalities with localized titles."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            default_personality,
            sample_personality,
        ]
        mock_db.execute.return_value = mock_result

        result = await service.list_active(user_language="fr")

        assert result.total == 2
        assert len(result.personalities) == 2
        assert result.personalities[0].code == "normal"
        assert result.personalities[0].title == "Normal"

    async def test_list_active_empty(self, service, mock_db):
        """Test empty list when no active personalities."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await service.list_active()

        assert result.total == 0
        assert len(result.personalities) == 0


# ============================================================================
# Prompt Instruction Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetPromptInstruction:
    """Tests for prompt instruction methods."""

    async def test_get_prompt_instruction_with_id(self, service, mock_db, sample_personality):
        """Test getting instruction with valid personality ID."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_personality
        mock_db.execute.return_value = mock_result

        result = await service.get_prompt_instruction(sample_personality.id)

        assert result == sample_personality.prompt_instruction

    async def test_get_prompt_instruction_none_uses_default(
        self, service, mock_db, default_personality
    ):
        """Test None ID uses default personality."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = default_personality
        mock_db.execute.return_value = mock_result

        result = await service.get_prompt_instruction(None)

        assert result == default_personality.prompt_instruction

    async def test_get_prompt_instruction_fallback(self, service, mock_db):
        """Test fallback when no personality found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get_prompt_instruction(None)

        assert result == default_personality_prompt()


# ============================================================================
# User Personality Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetUserPersonality:
    """Tests for get_user_personality method."""

    async def test_get_user_personality_with_id(self, service, mock_db, sample_personality):
        """Test getting user personality with valid ID."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_personality
        mock_db.execute.return_value = mock_result

        result = await service.get_user_personality(sample_personality.id, user_language="fr")

        assert result is not None
        assert isinstance(result, PersonalityListItem)
        assert result.code == "enthusiastic"
        assert result.title == "Enthousiaste"
        assert result.emoji == "🎉"

    async def test_get_user_personality_none_uses_default(
        self, service, mock_db, default_personality
    ):
        """Test None ID uses default."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = default_personality
        mock_db.execute.return_value = mock_result

        result = await service.get_user_personality(None, user_language="fr")

        assert result is not None
        assert result.is_default is True


# ============================================================================
# Write Operations Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestUpdate:
    """Tests for update method."""

    async def test_update_personality(self, service, mock_db, sample_personality):
        """Test updating personality fields."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_personality
        mock_db.execute.return_value = mock_result

        update_data = PersonalityUpdate(emoji="🌟", sort_order=5)
        result = await service.update(sample_personality.id, update_data)

        assert result.emoji == "🌟"
        assert result.sort_order == 5
        mock_db.commit.assert_called_once()

    async def test_update_sets_default(self, service, mock_db, sample_personality):
        """Test setting personality as default clears other defaults."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_personality
        mock_db.execute.return_value = mock_result

        update_data = PersonalityUpdate(is_default=True)
        result = await service.update(sample_personality.id, update_data)

        assert result.is_default is True
        # verify _clear_default was called (execute called twice)
        assert mock_db.execute.call_count >= 2


@pytest.mark.asyncio
@pytest.mark.unit
class TestDelete:
    """Tests for delete method."""

    async def test_delete_personality(self, service, mock_db, sample_personality):
        """Test deleting non-default personality."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_personality
        mock_db.execute.return_value = mock_result

        await service.delete(sample_personality.id)

        mock_db.delete.assert_called_once_with(sample_personality)
        mock_db.commit.assert_called_once()

    async def test_delete_default_raises_error(self, service, mock_db, default_personality):
        """Test deleting default personality raises error."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = default_personality
        mock_db.execute.return_value = mock_result

        with pytest.raises(Exception):  # HTTPException conflict
            await service.delete(default_personality.id)


# ============================================================================
# Translation Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestAddTranslation:
    """Tests for add_translation method."""

    async def test_add_new_translation(self, service, mock_db, sample_personality):
        """Test adding a new translation."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_personality
        mock_db.execute.return_value = mock_result

        translation = PersonalityTranslationCreate(
            language_code="de",
            title="Begeistert",
            description="Ein energiegeladener Assistent",
        )

        await service.add_translation(sample_personality.id, translation)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_update_existing_translation(self, service, mock_db, sample_personality):
        """Test updating an existing translation."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_personality
        mock_db.execute.return_value = mock_result

        translation = PersonalityTranslationCreate(
            language_code="fr",
            title="Super Enthousiaste",
            description="Un assistant super énergique",
        )

        await service.add_translation(sample_personality.id, translation)

        # Should update existing, not add new
        mock_db.add.assert_not_called()


# ============================================================================
# Model Translation Helper Tests
# ============================================================================


@pytest.mark.unit
class TestPersonalityGetTranslation:
    """Tests for Personality.get_translation method."""

    def test_get_translation_exact_match(self, sample_personality):
        """Test getting exact language match."""
        trans = sample_personality.get_translation("fr")

        assert trans is not None
        assert trans.language_code == "fr"
        assert trans.title == "Enthousiaste"

    def test_get_translation_falls_back_to_the_instance_default(self, sample_personality):
        """A missing language falls back to the instance's default — pinned to
        Spanish here, so neither a French nor an English fallback can pass."""
        spanish = PersonalityTranslation(
            id=uuid4(),
            personality_id=sample_personality.id,
            language_code="es",
            title="Entusiasta",
            description="Un asistente lleno de energía",
            is_auto_translated=False,
        )
        sample_personality.translations = [*sample_personality.translations, spanish]

        with patch.object(settings, "default_language", "es"):
            trans = sample_personality.get_translation("de")

        assert trans is spanish

    def test_get_translation_fallback_to_first(self, sample_personality):
        """Neither the asked language nor the instance's: the first written wins,
        never a language the code prefers."""
        with patch.object(settings, "default_language", "it"):
            trans = sample_personality.get_translation("de")

        assert trans is sample_personality.translations[0]
        assert trans.language_code == "fr"

    def test_get_translation_empty_list(self, sample_personality):
        """Test empty translations list returns None."""
        sample_personality.translations = []

        trans = sample_personality.get_translation("fr")

        assert trans is None


# ============================================================================
# Auto-translation source (ADR-323)
# ============================================================================


class TestAutoTranslationSource:
    """Without a source language, the admin button starts from the text an
    administrator WROTE — never from a machine translation, and not blindly from
    one language: the button used to require the instance default's text, and a
    personality without it answered a 500."""

    @staticmethod
    def _personality(*translations: tuple[str, bool]) -> Personality:
        personality = Personality(
            id=uuid4(),
            code="calm",
            emoji="🙂",
            is_default=False,
            is_active=True,
            sort_order=1,
            prompt_instruction="Be calm.",
        )
        written = datetime(2026, 1, 1, tzinfo=UTC)
        personality.translations = [
            PersonalityTranslation(
                id=uuid4(),
                personality_id=personality.id,
                language_code=code,
                title=f"title-{code}",
                description=f"description-{code}",
                is_auto_translated=auto,
                created_at=written + timedelta(minutes=index),
            )
            for index, (code, auto) in enumerate(translations)
        ]
        return personality

    @staticmethod
    async def _source_of(
        service: PersonalityService, personality: Personality, requested: str | None
    ) -> str:
        translate = AsyncMock(return_value=4)
        with (
            patch.object(service, "get_by_id", AsyncMock(return_value=personality)),
            patch.object(service, "_auto_translate_missing", translate),
        ):
            await service.trigger_auto_translation(personality.id, requested)

        assert translate.await_args is not None
        source: str = translate.await_args.args[3]
        return source

    async def test_an_admin_whose_language_was_never_filled_starts_from_the_original(self, service):
        personality = self._personality(("fr", False))
        with language_scope("de"):
            assert await self._source_of(service, personality, None) == "fr"

    async def test_a_machine_translation_in_the_admin_s_language_is_not_the_source(self, service):
        personality = self._personality(("fr", False), ("en", True))
        with language_scope("en"):
            assert await self._source_of(service, personality, None) == "fr"

    async def test_the_admin_s_own_written_text_wins_among_the_written(self, service):
        personality = self._personality(("fr", False), ("de", False))
        with language_scope("de"):
            assert await self._source_of(service, personality, None) == "de"

    async def test_an_explicit_source_is_honoured_in_any_spelling(self, service):
        personality = self._personality(("fr", False), ("zh-CN", False))
        assert await self._source_of(service, personality, "zh") == "zh-CN"

    async def test_an_explicit_machine_translation_is_no_source(self, service):
        """Named explicitly, a machine translation is still not translated again."""
        personality = self._personality(("fr", False), ("zh-CN", True))

        with (
            patch.object(service, "get_by_id", AsyncMock(return_value=personality)),
            language_scope("en"),
            pytest.raises(UnprocessableEntityError) as refused,
        ):
            await service.trigger_auto_translation(personality.id, "zh")

        assert refused.value.detail == APIMessages.personality_translation_source_missing(
            "zh", "en"
        )

    async def test_the_source_used_is_reported(self, service):
        personality = self._personality(("fr", False), ("zh-CN", False))
        with (
            patch.object(service, "get_by_id", AsyncMock(return_value=personality)),
            patch.object(service, "_auto_translate_missing", AsyncMock(return_value=4)),
        ):
            assert await service.trigger_auto_translation(personality.id, "zh") == (4, "zh-CN")

    async def test_only_machine_translations_are_no_source(self, service):
        """A machine translation is never translated again (ADR-323)."""
        personality = self._personality(("fr", True), ("en", True))

        with (
            patch.object(service, "get_by_id", AsyncMock(return_value=personality)),
            language_scope("en"),
            pytest.raises(UnprocessableEntityError) as refused,
        ):
            await service.trigger_auto_translation(personality.id, None)

        assert refused.value.detail == APIMessages.personality_translation_source_missing(
            None, "en"
        )

    async def test_the_route_reports_the_source_it_used(self):
        from src.domains.personalities import router as personalities_router

        service = MagicMock()
        service.trigger_auto_translation = AsyncMock(return_value=(4, "fr"))
        with patch.object(personalities_router, "PersonalityService", return_value=service):
            body = await personalities_router.trigger_auto_translation(
                personality_id=uuid4(), source_language=None, user=MagicMock(), db=MagicMock()
            )

        assert body == {"translations_created": 4, "source_language": "fr"}

    @pytest.mark.parametrize("requested", ["it", "pt"])
    async def test_a_source_the_personality_lacks_is_refused_as_unprocessable(
        self, service, requested
    ):
        personality = self._personality(("fr", False))

        with (
            patch.object(service, "get_by_id", AsyncMock(return_value=personality)),
            pytest.raises(UnprocessableEntityError),
        ):
            await service.trigger_auto_translation(personality.id, requested)


# ============================================================================
# No transaction open across a model call (ADR-304)
# ============================================================================

_TRANSLATE = (
    "src.domains.personalities.translation_service."
    "PersonalityTranslationService.translate_personality"
)


class _UniqueViolation(Exception):
    """What asyncpg raises on a unique violation: its SQLSTATE and constraint."""

    sqlstate = "23505"

    def __init__(self, constraint_name: str) -> None:
        super().__init__("duplicate key value violates unique constraint")
        self.constraint_name = constraint_name


def _recording_db(steps: list[str]) -> AsyncMock:
    """A session that records what reaches the database, in order."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=lambda *_a, **_k: steps.append("sql"))
    db.flush = AsyncMock(side_effect=lambda *_a, **_k: steps.append("flush"))
    db.commit = AsyncMock(side_effect=lambda: steps.append("commit"))
    db.refresh = AsyncMock()
    db.add = MagicMock(side_effect=lambda *_a: steps.append("add"))
    return db


def _model(steps: list[str]):
    async def _translate(**kwargs):
        steps.append("model")
        return {"title": "t", "description": "d"}

    return _translate


@pytest.mark.unit
class TestNoTransactionAcrossAModelCall:
    """The model answers while no transaction is open: every read is committed
    before the first call, and nothing is written until the last one returned."""

    @staticmethod
    def _assert_models_run_outside_a_transaction(steps: list[str]) -> None:
        models = [index for index, step in enumerate(steps) if step == "model"]
        assert models, steps
        before = steps[: models[0]]
        # The last statement before the first model call is a commit…
        assert before[-1] == "commit", steps
        # …and nothing reaches the database between two model calls.
        assert set(steps[models[0] : models[-1] + 1]) == {"model"}, steps

    async def test_creating_a_personality(self) -> None:
        from src.domains.personalities.schemas import PersonalityCreate

        steps: list[str] = []
        service = PersonalityService(_recording_db(steps))
        data = PersonalityCreate(
            code="calm",
            emoji="🙂",
            is_default=True,
            prompt_instruction="Be calm and kind.",
            title="Calme",
            description="Un assistant calme",
            source_language="fr",
        )

        with (
            patch.object(
                service, "get_by_code", AsyncMock(side_effect=lambda _c: steps.append("sql"))
            ),
            patch(_TRANSLATE, new=AsyncMock(side_effect=_model(steps))),
        ):
            await service.create(data)

        self._assert_models_run_outside_a_transaction(steps)
        # The row — and the default it takes over — is written after the model.
        assert steps.index("add") > max(i for i, s in enumerate(steps) if s == "model")
        assert steps[-2:] == ["flush", "commit"]

    async def test_a_code_taken_while_the_model_translated_is_a_conflict(self) -> None:
        """The uniqueness read no longer spans the model calls: the unique
        index decides, and its refusal is a 409 — never a 500."""
        from sqlalchemy.exc import IntegrityError

        from src.core.exceptions import ResourceConflictError
        from src.domains.personalities.schemas import PersonalityCreate

        steps: list[str] = []
        db = _recording_db(steps)
        db.flush = AsyncMock(
            side_effect=IntegrityError("INSERT", {}, _UniqueViolation("ix_personalities_code"))
        )
        db.rollback = AsyncMock(side_effect=lambda: steps.append("rollback"))
        service = PersonalityService(db)
        data = PersonalityCreate(
            code="calm",
            emoji="🙂",
            is_default=True,
            prompt_instruction="Be calm and kind.",
            title="Calme",
            description="Un assistant calme",
            source_language="fr",
        )

        with (
            patch.object(service, "get_by_code", AsyncMock(return_value=None)),
            patch(_TRANSLATE, new=AsyncMock(side_effect=_model(steps))),
            pytest.raises(ResourceConflictError) as refused,
        ):
            await service.create(data)

        assert refused.value.status_code == 409
        # The default the new row would have taken over is given back: nothing
        # was committed after the last model call, and the rollback came last.
        assert steps[-1] == "rollback"
        last_model = max(i for i, step in enumerate(steps) if step == "model")
        assert "commit" not in steps[last_model:]

    async def test_another_constraint_is_not_a_code_conflict(self) -> None:
        """Only the code's own index means « taken »; anything else stays an error."""
        from sqlalchemy.exc import IntegrityError

        from src.domains.personalities.schemas import PersonalityCreate

        steps: list[str] = []
        db = _recording_db(steps)
        db.flush = AsyncMock(
            side_effect=IntegrityError(
                "INSERT", {}, _UniqueViolation("uq_personality_translation_lang")
            )
        )
        db.rollback = AsyncMock(side_effect=lambda: steps.append("rollback"))
        service = PersonalityService(db)
        data = PersonalityCreate(
            code="calm",
            emoji="🙂",
            prompt_instruction="Be calm and kind.",
            title="Calme",
            description="Un assistant calme",
            source_language="fr",
        )

        with (
            patch.object(service, "get_by_code", AsyncMock(return_value=None)),
            patch(_TRANSLATE, new=AsyncMock(side_effect=_model(steps))),
            pytest.raises(IntegrityError),
        ):
            await service.create(data)

        assert steps[-1] == "rollback"

    async def test_translating_a_personality_on_demand(self) -> None:
        steps: list[str] = []
        service = PersonalityService(_recording_db(steps))
        personality = TestAutoTranslationSource._personality(("fr", False))

        async def _read(_id):
            steps.append("sql")
            return personality

        with (
            patch.object(service, "get_by_id", AsyncMock(side_effect=_read)),
            patch(_TRANSLATE, new=AsyncMock(side_effect=_model(steps))),
        ):
            await service.trigger_auto_translation(personality.id, None)

        self._assert_models_run_outside_a_transaction(steps)
        assert steps[-1] == "commit"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("constraint", "refusal"),
    [("ix_personalities_code", "conflict"), ("uq_personality_translation_lang", "error")],
)
async def test_a_rename_racing_on_the_code_is_a_conflict_on_another_constraint_an_error(
    constraint: str, refusal: str
) -> None:
    """The uniqueness read runs before the write: a concurrent rename to the
    same code used to answer a 500 — the fix only covered a create."""
    from sqlalchemy.exc import IntegrityError

    from src.core.exceptions import ResourceConflictError
    from src.domains.personalities.schemas import PersonalityUpdate

    steps: list[str] = []
    db = _recording_db(steps)
    db.commit = AsyncMock(side_effect=IntegrityError("UPDATE", {}, _UniqueViolation(constraint)))
    db.rollback = AsyncMock(side_effect=lambda: steps.append("rollback"))
    service = PersonalityService(db)
    current = MagicMock(code="calm", is_default=False)
    expected = ResourceConflictError if refusal == "conflict" else IntegrityError

    with (
        patch.object(service, "get_by_id", AsyncMock(return_value=current)),
        patch.object(service, "get_by_code", AsyncMock(return_value=None)),
        pytest.raises(expected),
    ):
        await service.update(uuid4(), PersonalityUpdate(code="serene"))

    assert steps[-1] == "rollback"


@pytest.mark.unit
def test_one_language_twice_is_refused_before_anything_runs() -> None:
    """Two translations in one language are refused by the schema, before any
    model call or write — the unique constraint would refuse them after both."""
    from pydantic import ValidationError

    from src.domains.personalities.schemas import PersonalityCreate

    with pytest.raises(ValidationError):
        PersonalityCreate(
            code="calm",
            emoji="🙂",
            prompt_instruction="Be calm and kind.",
            translations=[
                PersonalityTranslationCreate(language_code="fr", title="A", description="B"),
                PersonalityTranslationCreate(language_code="fr", title="C", description="D"),
            ],
        )


@pytest.mark.unit
def test_the_translations_come_back_in_the_order_they_were_written() -> None:
    """``get_translation``'s last fallback is the first written: the collection is
    ordered by creation, an administrator's text first among rows written together."""
    order = [str(column) for column in Personality.translations.property.order_by]

    assert order == [
        "personality_translations.created_at",
        "personality_translations.is_auto_translated",
        "personality_translations.language_code",
    ]
