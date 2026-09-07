"""The key the briefing WRITES is the key the push invalidation DELETES.

That sentence was false for the length of one commit, and nothing said so: the
cache key gained a language segment in ``BriefingService`` while
``push_channels/cache_invalidation`` kept building the old shape by hand, and
``redis.delete`` on an absent key succeeds and returns 0. A Gmail or Calendar
push would have stopped invalidating anything at all, with the staleness it
exists to short-circuit bounded only by the TTL.

Two modules, two domains, one key — so the contract is asserted between them
rather than inside either.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.i18n import SUPPORTED_LANGUAGES
from src.domains.briefing.cache_keys import (
    last_good_key,
    section_cache_key,
    section_keys_every_language,
)
from src.domains.briefing.constants import (
    SECTION_AGENDA,
    SECTION_DOCUMENTS,
    SECTION_MAILS,
    SECTION_NAMES,
)
from src.domains.briefing.service import BriefingService
from src.domains.push_channels.cache_invalidation import (
    _PROVIDER_SECTIONS,
    invalidate_for_provider,
)
from src.infrastructure.cache.key_families import family_of, scope_of

pytestmark = [pytest.mark.unit]


def _service(language: str, user_id) -> BriefingService:
    return BriefingService(  # type: ignore[arg-type]
        SimpleNamespace(
            id=user_id,
            full_name="Jean",
            email="jean@example.com",
            language=language,
            timezone="Europe/Paris",
            health_metrics_agents_enabled=False,
            briefing_preferences=None,
        )
    )


class TestTheWriterAndTheInvalidatorAgree:
    async def test_a_push_deletes_the_key_the_service_wrote(self) -> None:
        """The whole point. Runs the real invalidation against a recording
        double and requires the service's own key to be among the victims."""
        user_id = uuid4()
        deleted: list[str] = []

        class Redis:
            async def delete(self, *keys: str) -> int:
                deleted.extend(keys)
                return len(keys)

            async def scan_iter(self, match: str):  # noqa: ANN202 - test double
                return
                yield  # pragma: no cover - makes this an async generator

        for provider, section in _PROVIDER_SECTIONS.items():
            for language in SUPPORTED_LANGUAGES:
                deleted.clear()
                written = _service(language, user_id)._cache_key(section)
                with patch(
                    "src.domains.push_channels.cache_invalidation.get_redis_cache",
                    AsyncMock(return_value=Redis()),
                ):
                    await invalidate_for_provider(provider, user_id)
                assert written in deleted, (
                    f"a {provider} push left the {language} {section} card cached: "
                    f"{written!r} was not among {deleted!r}"
                )

    def test_every_invalidated_section_is_a_real_section(self) -> None:
        assert set(_PROVIDER_SECTIONS.values()) <= set(SECTION_NAMES)
        assert set(_PROVIDER_SECTIONS.values()) == {
            SECTION_AGENDA,
            SECTION_DOCUMENTS,
            SECTION_MAILS,
        }


class TestTheKeysKeepTheirDeclaredScope:
    """ADR-260: a family declares who may delete it. Inserting the language
    segment must not move either key out of its family."""

    def test_the_section_key_stays_a_purgeable_user_cache(self) -> None:
        key = section_cache_key(user_id=uuid4(), language="fr", section=SECTION_MAILS)
        assert family_of(key) == "briefing:v2"
        assert scope_of(key) is not None and scope_of(key).value == "user_cache"

    def test_the_last_good_key_stays_learning_and_survives_a_reset(self) -> None:
        key = last_good_key(user_id=uuid4(), language="fr", section=SECTION_MAILS)
        assert family_of(key) == "briefing:v2:lastgood"
        assert scope_of(key) is not None and scope_of(key).value == "user_learning"

    def test_the_reset_scan_still_reaches_the_key(self) -> None:
        """The conversation reset finds keys by ``*:{user_id}:*``; a segment
        inserted after the id must not push the key out of that glob."""
        import fnmatch

        from src.infrastructure.cache.key_families import scan_patterns_for

        user_id = uuid4()
        key = section_cache_key(user_id=user_id, language="zh-CN", section=SECTION_MAILS)
        patterns = scan_patterns_for(str(user_id))
        assert any(fnmatch.fnmatch(key, pattern) for pattern in patterns)


class TestTheBuilderItself:
    def test_every_supported_language_is_covered(self) -> None:
        user_id = uuid4()
        keys = section_keys_every_language(user_id=user_id, section=SECTION_MAILS)
        assert len(keys) == len(SUPPORTED_LANGUAGES)
        assert len(set(keys)) == len(keys), "two languages collided on one key"

    def test_two_languages_never_share_a_key(self) -> None:
        user_id = uuid4()
        assert section_cache_key(
            user_id=user_id, language="fr", section=SECTION_MAILS
        ) != section_cache_key(user_id=user_id, language="de", section=SECTION_MAILS)

    def test_two_sections_never_share_a_key(self) -> None:
        user_id = uuid4()
        keys = {
            section_cache_key(user_id=user_id, language="fr", section=name)
            for name in SECTION_NAMES
        }
        assert len(keys) == len(SECTION_NAMES)

    def test_the_side_key_is_never_the_section_key(self) -> None:
        user_id = uuid4()
        assert section_cache_key(
            user_id=user_id, language="fr", section=SECTION_MAILS
        ) != last_good_key(user_id=user_id, language="fr", section=SECTION_MAILS)


class TestAnEmptyLanguageListCannotPassSilently:
    """``redis.delete()`` with no arguments is an error, and the invalidation
    swallows errors by doctrine — so an empty enumeration would be a silent
    no-op rather than a loud failure."""

    def test_the_module_refuses_to_load_without_languages(self) -> None:
        import importlib

        import src.domains.briefing.cache_keys as module

        # The guard runs at import, so the empty list is installed at the
        # SOURCE and the module reloaded under it.
        with (
            patch("src.core.i18n.SUPPORTED_LANGUAGES", []),
            pytest.raises(RuntimeError, match="SUPPORTED_LANGUAGES is empty"),
        ):
            importlib.reload(module)
        importlib.reload(module)  # restore the real module for the other tests
        assert module.SUPPORTED_LANGUAGES

    def test_the_enumeration_is_never_empty_in_practice(self) -> None:
        assert section_keys_every_language(user_id=uuid4(), section=SECTION_MAILS)
