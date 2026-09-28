"""
Personality service containing business logic for personality management.
"""

from collections.abc import Awaitable, Callable
from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.core.exceptions import (
    ResourceConflictError,
    ResourceNotFoundError,
    raise_unprocessable_entity,
)
from src.core.i18n import resolve_language
from src.core.i18n_api_messages import APIMessages
from src.core.i18n_types import canonical_language
from src.domains.personalities.constants import default_personality_prompt
from src.domains.personalities.models import Personality, PersonalityTranslation
from src.domains.personalities.schemas import (
    PersonalityCreate,
    PersonalityListItem,
    PersonalityListResponse,
    PersonalityResponse,
    PersonalityTranslationCreate,
    PersonalityUpdate,
)
from src.infrastructure.database.errors import database_error_fields

logger = structlog.get_logger(__name__)

#: The unique index a personality's code answers to (migration add_personalities).
_CODE_INDEX = "ix_personalities_code"


class PersonalityService:
    """Service for personality management business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # =========================================================================
    # Read Operations
    # =========================================================================

    async def get_by_id(self, personality_id: UUID) -> Personality:
        """
        Get personality by ID with translations.

        Args:
            personality_id: Personality UUID

        Returns:
            Personality with translations loaded

        Raises:
            HTTPException: If not found
        """
        stmt = (
            select(Personality)
            .options(selectinload(Personality.translations))
            .where(Personality.id == personality_id)
        )
        result = await self.db.execute(stmt)
        personality = result.scalar_one_or_none()

        if not personality:
            raise ResourceNotFoundError("personality", personality_id)

        return personality

    async def get_by_code(self, code: str) -> Personality | None:
        """
        Get personality by code.

        Args:
            code: Personality code (e.g., 'enthusiastic')

        Returns:
            Personality or None
        """
        stmt = (
            select(Personality)
            .options(selectinload(Personality.translations))
            .where(Personality.code == code)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_default(self) -> Personality | None:
        """
        Get the default personality.

        Returns:
            Default personality or None
        """
        stmt = (
            select(Personality)
            .options(selectinload(Personality.translations))
            .where(Personality.is_default == True)  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active(self, user_language: str | None = None) -> PersonalityListResponse:
        """
        List all active personalities with localized titles/descriptions.

        Args:
            user_language: User's language for localization

        Returns:
            PersonalityListResponse with localized personalities
        """
        stmt = (
            select(Personality)
            .options(selectinload(Personality.translations))
            .where(Personality.is_active == True)  # noqa: E712
            .order_by(Personality.sort_order, Personality.code)
        )
        result = await self.db.execute(stmt)
        personalities = result.scalars().all()

        items = []
        for p in personalities:
            trans = p.get_translation(resolve_language(user_language))
            if trans:
                items.append(
                    PersonalityListItem(
                        id=p.id,
                        code=p.code,
                        emoji=p.emoji,
                        is_default=p.is_default,
                        title=trans.title,
                        description=trans.description,
                    )
                )

        return PersonalityListResponse(personalities=items, total=len(items))

    async def list_all(self) -> list[PersonalityResponse]:
        """
        List all personalities (admin view).

        Returns:
            List of PersonalityResponse with all translations
        """
        stmt = (
            select(Personality)
            .options(selectinload(Personality.translations))
            .order_by(Personality.sort_order, Personality.code)
        )
        result = await self.db.execute(stmt)
        personalities = result.scalars().all()

        return [PersonalityResponse.model_validate(p) for p in personalities]

    # =========================================================================
    # Write Operations
    # =========================================================================

    async def create(
        self,
        data: PersonalityCreate,
        auto_translate: bool = True,
    ) -> Personality:
        """
        Create a new personality with translations.

        The missing languages are translated while NO transaction is open
        (ADR-304): the uniqueness read is committed first, and the row — with
        its unique ``code`` — is written only once every model call returned.

        Args:
            data: Personality creation data
            auto_translate: Whether to auto-translate missing languages

        Returns:
            Created personality

        Raises:
            ResourceConflictError: If the code already exists — read
                first, or taken by a concurrent create while the model
                translated (the unique index decides then).
        """
        # Check uniqueness
        existing = await self.get_by_code(data.code)
        if existing:
            raise ResourceConflictError(
                "personality", APIMessages.personality_code_taken(data.code)
            )
        # End the read before the model is asked anything (ADR-304).
        await self.db.commit()

        # Create personality
        personality = Personality(
            code=data.code,
            emoji=data.emoji,
            is_default=data.is_default,
            is_active=data.is_active,
            sort_order=data.sort_order,
            prompt_instruction=data.prompt_instruction,
        )

        # Get translations (supports both simplified and full format)
        translations = data.get_translations()

        # Add provided translations
        provided_langs = set()
        for t in translations:
            personality.translations.append(
                PersonalityTranslation(
                    language_code=t.language_code,
                    title=t.title,
                    description=t.description,
                    is_auto_translated=False,
                )
            )
            provided_langs.add(t.language_code)

        # Auto-translate missing languages — on the row still outside the
        # session, so nothing is written while the model answers.
        if auto_translate and provided_langs:
            source = translations[0]
            await self._auto_translate_missing(
                personality,
                source.title,
                source.description,
                source.language_code,
                provided_langs,
            )

        # Clear default if setting new default
        if data.is_default:
            await self._clear_default()

        self.db.add(personality)
        # The uniqueness read was committed before the model calls, so a
        # concurrent create may have taken the code meanwhile; the default
        # cleared above is rolled back with the row.
        await self._write_or_code_conflict(self.db.flush, data.code)
        await self.db.commit()
        await self.db.refresh(personality)

        logger.info(
            "personality_created",
            personality_id=str(personality.id),
            code=personality.code,
            translations=len(personality.translations),
        )

        return personality

    async def update(
        self,
        personality_id: UUID,
        data: PersonalityUpdate,
        propagate_translations: bool = True,
    ) -> Personality:
        """
        Update an existing personality.

        Args:
            personality_id: Personality UUID
            data: Update data
            propagate_translations: If True, auto-translate to all languages when
                                    title/description change

        Returns:
            Updated personality

        Raises:
            ResourceConflictError: If the new code already exists — read first,
                or taken by a concurrent create or rename (the unique index
                decides then).
        """
        personality = await self.get_by_id(personality_id)

        # Handle code change with uniqueness check
        if data.code is not None and data.code != personality.code:
            existing = await self.get_by_code(data.code)
            if existing and existing.id != personality_id:
                raise ResourceConflictError(
                    "personality",
                    APIMessages.personality_code_taken(data.code),
                )

        # Handle default flag change
        if data.is_default and not personality.is_default:
            await self._clear_default()

        # Extract translation fields from update data
        update_dict = data.model_dump(exclude_unset=True)
        translation_fields = {"title", "description", "source_language"}
        translation_data = {k: update_dict.pop(k) for k in translation_fields if k in update_dict}

        # Update personality entity fields (code, emoji, is_default, etc.)
        for field, value in update_dict.items():
            setattr(personality, field, value)

        # Handle translation updates
        needs_propagation = False
        source_language = resolve_language(translation_data.get("source_language"))

        if "title" in translation_data or "description" in translation_data:
            needs_propagation = await self._update_source_translation(
                personality,
                translation_data.get("title"),
                translation_data.get("description"),
                source_language,
            )

        # A concurrent rename may take the code between the read and the write.
        await self._write_or_code_conflict(self.db.commit, data.code)

        # Auto-propagate translations if content changed
        if needs_propagation and propagate_translations:
            propagated_count = await self._propagate_translations(
                personality,
                source_language,
            )
            await self.db.commit()
            logger.info(
                "translations_propagated",
                personality_id=str(personality_id),
                count=propagated_count,
                source_language=source_language,
            )

        await self.db.refresh(personality)

        logger.info(
            "personality_updated",
            personality_id=str(personality_id),
            fields=list(data.model_dump(exclude_unset=True).keys()),
            propagated=needs_propagation and propagate_translations,
        )

        return personality

    async def _write_or_code_conflict(
        self, write: Callable[[], Awaitable[None]], code: str | None
    ) -> None:
        """Write, answering a code another personality took meanwhile as a 409.

        The uniqueness read runs before the write, so a concurrent create or
        rename may take the code in between: the unique index decides, and the
        transaction is rolled back. Any other constraint is not a code
        conflict, and stays an error.

        Args:
            write: The flush or commit that sends the row.
            code: The code the row claims, when it claims one.

        Raises:
            ResourceConflictError: The code's unique index refused the row.
            IntegrityError: Any other constraint refused it.
        """
        try:
            await write()
        except IntegrityError as exc:
            await self.db.rollback()
            if code is None or database_error_fields(exc).get("constraint") != _CODE_INDEX:
                raise
            raise ResourceConflictError(
                "personality", APIMessages.personality_code_taken(code)
            ) from exc

    async def delete(self, personality_id: UUID) -> None:
        """
        Delete a personality (cannot delete default).

        Args:
            personality_id: Personality UUID

        Raises:
            HTTPException: If personality is default or not found
        """
        personality = await self.get_by_id(personality_id)

        if personality.is_default:
            raise ResourceConflictError(
                "personality", APIMessages.personality_default_not_deletable()
            )

        await self.db.delete(personality)
        await self.db.commit()

        logger.info(
            "personality_deleted",
            personality_id=str(personality_id),
            code=personality.code,
        )

    async def add_translation(
        self,
        personality_id: UUID,
        translation: PersonalityTranslationCreate,
    ) -> PersonalityTranslation:
        """
        Add or update a translation for a personality.

        Args:
            personality_id: Personality UUID
            translation: Translation data

        Returns:
            Created/updated translation
        """
        personality = await self.get_by_id(personality_id)

        # Check if translation exists
        existing = None
        for t in personality.translations:
            if t.language_code == translation.language_code:
                existing = t
                break

        if existing:
            # Update existing
            existing.title = translation.title
            existing.description = translation.description
            existing.is_auto_translated = False
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        else:
            # Create new
            new_translation = PersonalityTranslation(
                personality_id=personality_id,
                language_code=translation.language_code,
                title=translation.title,
                description=translation.description,
                is_auto_translated=False,
            )
            self.db.add(new_translation)
            await self.db.commit()
            await self.db.refresh(new_translation)
            return new_translation

    # =========================================================================
    # User Preference Methods
    # =========================================================================

    async def get_prompt_instruction(
        self,
        user_personality_id: UUID | None,
    ) -> str:
        """
        Get prompt instruction for {personnalite} injection.

        Args:
            user_personality_id: User's preferred personality ID (or None for default)

        Returns:
            Prompt instruction text
        """
        personality = None

        if user_personality_id:
            try:
                personality = await self.get_by_id(user_personality_id)
            except Exception:
                # Fallback to default if user's personality not found
                personality = await self.get_default()
        else:
            personality = await self.get_default()

        if personality:
            return personality.prompt_instruction

        # Ultimate fallback
        return default_personality_prompt()

    async def get_prompt_instruction_for_user(
        self,
        user_id: UUID,
    ) -> str:
        """
        Get prompt instruction for a user by looking up their personality preference.

        Args:
            user_id: User's UUID

        Returns:
            Prompt instruction text (default if user has no preference)
        """
        from src.domains.users.models import User

        # Query user to get their personality_id
        result = await self.db.execute(select(User.personality_id).where(User.id == user_id))
        row = result.first()
        user_personality_id = row[0] if row else None

        return await self.get_prompt_instruction(user_personality_id)

    async def get_user_personality(
        self,
        user_personality_id: UUID | None,
        user_language: str | None = None,
    ) -> PersonalityListItem | None:
        """
        Get user's current personality for display.

        Args:
            user_personality_id: User's personality_id (or None)
            user_language: User's language for localization

        Returns:
            PersonalityListItem or None
        """
        personality = None

        if user_personality_id:
            try:
                personality = await self.get_by_id(user_personality_id)
            except Exception:
                personality = await self.get_default()
        else:
            personality = await self.get_default()

        if not personality:
            return None

        trans = personality.get_translation(resolve_language(user_language))
        if not trans:
            return None

        return PersonalityListItem(
            id=personality.id,
            code=personality.code,
            emoji=personality.emoji,
            is_default=personality.is_default,
            title=trans.title,
            description=trans.description,
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _clear_default(self) -> None:
        """Clear the is_default flag from all personalities."""
        stmt = (
            update(Personality)
            .where(Personality.is_default == True)  # noqa: E712
            .values(is_default=False)
        )
        await self.db.execute(stmt)

    async def _update_source_translation(
        self,
        personality: Personality,
        title: str | None,
        description: str | None,
        source_language: str,
    ) -> bool:
        """
        Update or create the source language translation.

        Args:
            personality: Personality to update
            title: New title (or None to keep existing)
            description: New description (or None to keep existing)
            source_language: Language code for the translation

        Returns:
            True if content actually changed (needs propagation), False otherwise
        """
        # Find existing translation for source language
        existing_trans = next(
            (t for t in personality.translations if t.language_code == source_language),
            None,
        )

        if existing_trans:
            # Check if content actually changed
            title_changed = title is not None and title != existing_trans.title
            desc_changed = description is not None and description != existing_trans.description

            if title_changed or desc_changed:
                if title is not None:
                    existing_trans.title = title
                if description is not None:
                    existing_trans.description = description
                existing_trans.is_auto_translated = False  # Manual update
                return True
            return False
        else:
            # Create new translation for source language
            if title is None or description is None:
                raise ValueError(
                    f"Both title and description required when creating "
                    f"translation for new language: {source_language}"
                )

            new_trans = PersonalityTranslation(
                personality_id=personality.id,
                language_code=source_language,
                title=title,
                description=description,
                is_auto_translated=False,
            )
            personality.translations.append(new_trans)
            return True

    async def _propagate_translations(
        self,
        personality: Personality,
        source_language: str,
    ) -> int:
        """
        Re-translate ALL non-source languages (update existing + create missing).

        IMPORTANT: Different from _auto_translate_missing which only creates missing ones.

        Args:
            personality: Personality with updated source translation
            source_language: Language code of the source translation

        Returns:
            Number of translations updated/created
        """
        from src.domains.personalities.translation_service import (
            PersonalityTranslationService,
        )

        # Invalidate cache for this personality (cache key doesn't change when content changes)
        self._invalidate_translation_cache(personality.code)

        # Get source translation
        source_trans = next(
            (t for t in personality.translations if t.language_code == source_language),
            None,
        )

        if not source_trans:
            logger.warning(
                "propagate_no_source",
                personality_id=str(personality.id),
                source_language=source_language,
            )
            return 0

        count = 0
        for lang in settings.supported_languages:
            if lang == source_language:
                continue

            try:
                translated = await PersonalityTranslationService.translate_personality(
                    source_title=source_trans.title,
                    source_description=source_trans.description,
                    source_language=source_language,
                    target_language=lang,
                    personality_code=personality.code,
                )

                # Find existing translation OR create new
                existing = next(
                    (t for t in personality.translations if t.language_code == lang),
                    None,
                )

                if existing:
                    # UPDATE existing
                    existing.title = translated["title"]
                    existing.description = translated["description"]
                    existing.is_auto_translated = True
                else:
                    # CREATE new
                    personality.translations.append(
                        PersonalityTranslation(
                            personality_id=personality.id,
                            language_code=lang,
                            title=translated["title"],
                            description=translated["description"],
                            is_auto_translated=True,
                        )
                    )
                count += 1

            except Exception as e:
                logger.warning(
                    "propagate_translation_failed",
                    personality_code=personality.code,
                    target_language=lang,
                    error=str(e),
                )

        return count

    def _invalidate_translation_cache(self, personality_code: str) -> None:
        """
        Invalidate translation cache for a personality.

        The cache uses key format {code}_{source}_{target}, so we need to
        clear all entries starting with this personality's code.
        """
        from src.domains.personalities.translation_service import _translation_cache

        # Remove all entries that start with this code
        keys_to_remove = [k for k in _translation_cache if k.startswith(f"{personality_code}_")]
        for key in keys_to_remove:
            del _translation_cache[key]

        if keys_to_remove:
            logger.debug(
                "translation_cache_invalidated",
                personality_code=personality_code,
                keys_removed=len(keys_to_remove),
            )

    async def _auto_translate_missing(
        self,
        personality: Personality,
        source_title: str,
        source_description: str,
        source_language: str,
        existing_langs: set[str],
    ) -> int:
        """
        Auto-translate missing language translations.

        Args:
            personality: Personality to add translations to
            source_title: Source title for translation
            source_description: Source description for translation
            source_language: Source language code
            existing_langs: Already existing language codes

        Returns:
            Number of translations created
        """
        from src.domains.personalities.translation_service import (
            PersonalityTranslationService,
        )

        missing_langs = set(settings.supported_languages) - existing_langs
        count = 0

        for lang in missing_langs:
            try:
                translated = await PersonalityTranslationService.translate_personality(
                    source_title=source_title,
                    source_description=source_description,
                    source_language=source_language,
                    target_language=lang,
                    personality_code=personality.code,
                )
                personality.translations.append(
                    PersonalityTranslation(
                        language_code=lang,
                        title=translated["title"],
                        description=translated["description"],
                        is_auto_translated=True,
                    )
                )
                count += 1
            except Exception as e:
                logger.warning(
                    "auto_translate_failed",
                    personality_code=personality.code,
                    target_language=lang,
                    error=str(e),
                )

        return count

    async def trigger_auto_translation(
        self,
        personality_id: UUID,
        source_language: str | None = None,
    ) -> tuple[int, str]:
        """
        Trigger auto-translation for a personality.

        Args:
            personality_id: Personality UUID
            source_language: Source language to translate from — its text must
                be one an administrator wrote; when absent, the written text
                ``_translation_source`` chooses.

        Returns:
            ``(created, source)`` — the number of translations created and the
            canonical code of the text they were made from.

        Raises:
            UnprocessableEntityError: The personality has no WRITTEN text in
                the requested source language (a machine translation is no
                source), the code names no language, or no text was written by
                an administrator.
        """
        personality = await self.get_by_id(personality_id)
        source_trans = _translation_source(personality.translations, source_language)
        if source_trans is None:
            raise_unprocessable_entity(
                APIMessages.personality_translation_source_missing(source_language),
                personality_id=str(personality_id),
            )
        source_language = source_trans.language_code

        # Get existing languages
        existing_langs = {t.language_code for t in personality.translations}

        # End the read before the model calls (ADR-304): the session keeps its
        # rows readable after a commit, and the new translations are written by
        # the commit below.
        await self.db.commit()

        # Auto-translate
        count = await self._auto_translate_missing(
            personality,
            source_trans.title,
            source_trans.description,
            source_language,
            existing_langs,
        )

        await self.db.commit()

        logger.info(
            "auto_translation_triggered",
            personality_id=str(personality_id),
            translations_created=count,
        )

        return count, source_language


def _translation_source(
    translations: list[PersonalityTranslation], requested: str | None
) -> PersonalityTranslation | None:
    """The translation an auto-translation starts from.

    The source is what an administrator WROTE, never a machine translation —
    the admin section authors one language and fills the others by machine, and
    translating a translation compounds its errors. An explicit language names
    its written translation (None when the personality has none written there,
    or when the code names no language). Without one, the declared (acting
    administrator's) language wins among the written ones, else the oldest;
    None when nothing was written (ADR-323).

    Args:
        translations: The personality's translations.
        requested: The explicit source language, or None.

    Returns:
        The source translation, or None when there is none to start from.
    """
    authored = sorted(
        (t for t in translations if not t.is_auto_translated), key=lambda t: t.created_at
    )
    if requested:
        code = canonical_language(requested)
        return next((t for t in authored if t.language_code == code), None)
    declared = resolve_language()
    return next(
        (t for t in authored if t.language_code == declared),
        authored[0] if authored else None,
    )
