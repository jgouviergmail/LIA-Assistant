"""The declared language (ADR-323): what a sentence nobody passed a language to is written in.

Order of resolution, from ``core.i18n.resolve_language``: the caller's explicit
language (normalised), else the language DECLARED for the current request, turn
or job, else the instance's ``DEFAULT_LANGUAGE``. The declarations happen where
the person becomes known: the Accept-Language of a request and the
authenticated account are proved here; the person a background run serves is
proved beside each runner (``test_runner.py``, ``test_out_of_turn_run.py``,
``test_voice_lookup.py``, ``channels/test_language_paths.py``).

A test that declares a language runs it in a copied context: a declaration is
meant to last until its task ends, and a synchronous test shares the thread's
context with the next one.
"""

from __future__ import annotations

import asyncio
import contextvars
import uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from pydantic import ValidationError

import src.core.i18n as i18n_module
from src.core.config import settings
from src.core.config.advanced import AdvancedSettings
from src.core.i18n import (
    declare_language,
    get_locale_for_language,
    language_from_header,
    language_scope,
    normalize_language,
    resolve_language,
)
from src.core.i18n_types import LANGUAGE_NAMES, canonical_language
from src.core.middleware import RequestLanguageMiddleware
from src.core.session_dependencies import _authenticate, get_optional_session
from src.domains.users.models import User
from src.infrastructure.cache.session_store import UserSession

pytestmark = pytest.mark.unit


#: Every language the tables hold. A test that needs a language OFFERED
#: offers the six itself: SUPPORTED_LANGUAGES is a deployment setting.
_EVERY_LANGUAGE: list[str] = list(LANGUAGE_NAMES)


@pytest.fixture
def _every_language_offered() -> Iterator[None]:
    """The six languages offered, whatever the deployment narrowed them to."""
    with patch.object(i18n_module, "SUPPORTED_LANGUAGES", _EVERY_LANGUAGE):
        yield


def _other_than_default(*candidates: str) -> str:
    """A supported language that is NOT the instance default, so a test can
    tell a declared language from the fallback whatever the deployment sets."""
    return next(code for code in candidates if code != settings.default_language)


class TestCanonicalLanguage:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("fr", "fr"),
            ("FR", "fr"),
            ("fr-FR", "fr"),
            ("en_US", "en"),
            (" de ", "de"),
            ("it-IT", "it"),
            ("es-MX", "es"),
            ("zh", "zh-CN"),
            ("zh_CN", "zh-CN"),
            ("zh-TW", "zh-CN"),
            ("ZH-hans", "zh-CN"),
        ],
    )
    def test_every_spelling_names_its_canonical_code(self, raw: str, expected: str) -> None:
        assert canonical_language(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "   ", "pt", "pt-BR", "ja", "klingon"])
    def test_a_code_naming_no_supported_language_names_nothing(self, raw: str | None) -> None:
        assert canonical_language(raw) is None

    def test_a_test_double_s_attribute_names_nothing(self) -> None:
        """A mock's attribute is truthy and its ``startswith`` answers truthy:
        read as a code, every mocked account used to speak Chinese."""
        assert canonical_language(MagicMock(spec=User).language) is None


class TestNormalizeLanguage:
    """A GIVEN language: a person's stored one, a payload's field."""

    @pytest.mark.parametrize("raw", [None, "", "pt-BR"])
    def test_an_absent_or_unsupported_language_reads_as_the_instance_default(
        self, raw: str | None
    ) -> None:
        other = _other_than_default("de", "it")

        def run() -> str:
            # A declaration never reaches a GIVEN language: normalize ignores it.
            declare_language(other)
            return normalize_language(raw)

        assert contextvars.copy_context().run(run) == settings.default_language


class TestResolveLanguage:
    def test_nothing_declared_reads_the_instance_default(self) -> None:
        assert contextvars.copy_context().run(resolve_language) == settings.default_language

    def test_an_absent_language_is_the_declared_one(self) -> None:
        declared = _other_than_default("de", "es")
        with language_scope(declared):
            assert resolve_language() == declared
            assert resolve_language(None) == declared
            assert resolve_language("") == declared

    def test_an_explicit_language_wins_and_is_normalised(self) -> None:
        with language_scope(_other_than_default("de", "es")):
            assert resolve_language("zh") == "zh-CN"
            assert resolve_language("it-IT") == "it"

    def test_the_display_locale_follows_the_declared_language(self) -> None:
        with language_scope("zh-CN"):
            assert get_locale_for_language(None) == "zh-CN"
        with language_scope("en"):
            assert get_locale_for_language(None) == "en-US"


class TestLanguageScope:
    def test_a_scope_declares_for_its_block_and_restores_after(self) -> None:
        outer, inner = _other_than_default("de", "es"), _other_than_default("it", "en")

        def run() -> list[str]:
            seen: list[str] = [resolve_language()]
            with language_scope(outer):
                seen.append(resolve_language())
                with language_scope(inner):
                    seen.append(resolve_language())
                seen.append(resolve_language())
            seen.append(resolve_language())
            return seen

        default = settings.default_language
        assert contextvars.copy_context().run(run) == [default, outer, inner, outer, default]

    def test_an_empty_language_keeps_the_current_one(self) -> None:
        declared = _other_than_default("de", "es")
        with language_scope(declared), language_scope(None), language_scope(""):
            assert resolve_language() == declared

    def test_a_scope_restores_after_an_exception(self) -> None:
        def run() -> str:
            with pytest.raises(RuntimeError), language_scope(_other_than_default("de", "es")):
                raise RuntimeError("boom")
            return resolve_language()

        assert contextvars.copy_context().run(run) == settings.default_language


class TestDeclareLanguage:
    def test_a_declaration_lasts_until_the_task_ends_and_empty_declares_nothing(self) -> None:
        declared = _other_than_default("de", "es")

        def run() -> tuple[str, str]:
            declare_language(declared)
            first = resolve_language()
            declare_language(None)
            declare_language("")
            return first, resolve_language()

        assert contextvars.copy_context().run(run) == (declared, declared)

    async def test_two_concurrent_tasks_never_see_each_others_language(self) -> None:
        async def serve(language: str) -> str:
            declare_language(language)
            await asyncio.sleep(0)  # the other task declares in between
            return resolve_language()

        first, second = await asyncio.gather(serve("de"), serve("zh"))

        assert (first, second) == ("de", "zh-CN")
        assert resolve_language() == settings.default_language


@pytest.mark.usefixtures("_every_language_offered")
class TestAcceptLanguageHeader:
    @pytest.mark.parametrize(
        ("header", "expected"),
        [
            ("fr-FR,fr;q=0.9,en;q=0.8", "fr"),
            ("en-US,en;q=0.9", "en"),
            ("zh-TW,zh;q=0.9", "zh-CN"),
            ("zh", "zh-CN"),
            ("ja,de;q=0.5", "de"),
            ("pt-BR,pt;q=0.9", None),
            # Ranked by weight, not by position: the client prefers English.
            ("fr;q=0.4,en;q=0.8", "en"),
            # A tie keeps the order the client wrote.
            ("de;q=0.7,it;q=0.7", "de"),
            # q=0 is a language the client REFUSES.
            ("fr;q=0, en", "en"),
            ("fr;q=0", None),
            # A malformed weight drops its entry, never the header.
            ("fr;q=high, it;q=0.2", "it"),
            # A qvalue outside [0, 1] is malformed too (RFC 9110).
            ("en;q=nan, fr;q=0.9", "fr"),
            ("es;q=2, fr", "fr"),
            ("de;q=inf, it;q=0.5", "it"),
            ("", None),
            (None, None),
        ],
    )
    def test_the_preferred_supported_entry_is_the_request_language(
        self, header: str | None, expected: str | None
    ) -> None:
        assert language_from_header(header) == expected

    def test_a_language_the_operator_narrowed_away_is_not_named(self) -> None:
        with patch.object(i18n_module, "SUPPORTED_LANGUAGES", ["fr", "en"]):
            assert language_from_header("de-DE,en;q=0.5") == "en"
            assert language_from_header("de-DE") is None


def _language_app() -> FastAPI:
    """An app whose routes answer the language a sentence would be written in."""
    app = FastAPI()
    app.add_middleware(RequestLanguageMiddleware)

    @app.get("/language")
    async def language() -> dict[str, str]:
        return {"language": resolve_language()}

    @app.websocket("/ws")
    async def websocket(ws: WebSocket) -> None:
        await ws.accept()
        await ws.send_text(resolve_language())
        await ws.close()

    return app


@pytest.mark.usefixtures("_every_language_offered")
class TestRequestLanguageMiddleware:
    def test_a_request_speaks_its_accept_language(self) -> None:
        declared = _other_than_default("de", "es")
        with TestClient(_language_app()) as client:
            response = client.get("/language", headers={"Accept-Language": f"{declared},en;q=0.5"})

        assert response.json() == {"language": declared}

    @pytest.mark.parametrize("headers", [{}, {"Accept-Language": "pt-BR,ja;q=0.8"}])
    def test_a_request_naming_nothing_declares_nothing(self, headers: dict[str, str]) -> None:
        with TestClient(_language_app()) as client:
            response = client.get("/language", headers=headers)

        assert response.json() == {"language": settings.default_language}

    def test_one_request_leaves_nothing_to_the_next(self) -> None:
        declared = _other_than_default("de", "es")
        with TestClient(_language_app()) as client:
            client.get("/language", headers={"Accept-Language": declared})
            response = client.get("/language")

        assert response.json() == {"language": settings.default_language}

    def test_a_websocket_speaks_its_handshake_language(self) -> None:
        declared = _other_than_default("it", "de")
        with (
            TestClient(_language_app()) as client,
            client.websocket_connect("/ws", headers={"Accept-Language": declared}) as ws,
        ):
            assert ws.receive_text() == declared


def _user(language: str) -> User:
    fields: dict[str, Any] = {
        "id": uuid.uuid4(),
        "email": "user@example.com",
        "hashed_password": "hashed",
        "is_active": True,
        "is_verified": True,
        "is_superuser": False,
        "language": language,
    }
    return User(**fields)


class TestAuthenticationDeclaresTheAccountLanguage:
    async def test_the_authenticated_account_s_language_replaces_the_header_s(self) -> None:
        account = _other_than_default("it", "de")
        user = _user(account)
        store = AsyncMock()
        store.get_session = AsyncMock(
            return_value=UserSession(session_id="s1", user_id=str(user.id))
        )
        store.touch_last_seen = AsyncMock()
        repo = AsyncMock()
        repo.get_user_minimal_for_session = AsyncMock(return_value=user)

        with (
            language_scope(_other_than_default("es", "en")),  # what the header declared
            patch("src.core.session_dependencies.UserRepository", return_value=repo),
        ):
            authenticated = await _authenticate("s1", store, AsyncMock())
            assert resolve_language() == account

        assert authenticated is user

    async def test_an_optional_session_that_recognises_the_account_declares_it_too(
        self,
    ) -> None:
        account = _other_than_default("it", "de")
        user = _user(account)
        store = AsyncMock()
        store.get_session = AsyncMock(
            return_value=UserSession(session_id="s1", user_id=str(user.id))
        )
        repo = AsyncMock()
        repo.get_user_minimal_for_session = AsyncMock(return_value=user)

        with (
            language_scope(_other_than_default("es", "en")),  # what the header declared
            patch("src.core.session_dependencies.UserRepository", return_value=repo),
        ):
            recognised = await get_optional_session("s1", store, AsyncMock())
            assert resolve_language() == account

        assert recognised is user


class TestDefaultLanguageSetting:
    @pytest.mark.parametrize(
        ("configured", "expected"),
        [("fr", "fr"), ("EN", "en"), ("fr-FR", "fr"), ("zh", "zh-CN"), ("zh_CN", "zh-CN")],
    )
    def test_the_setting_is_stored_canonical(self, configured: str, expected: str) -> None:
        advanced = AdvancedSettings(
            _env_file=None, default_language=configured, supported_languages=_EVERY_LANGUAGE
        )

        assert advanced.default_language == expected

    @pytest.mark.parametrize("configured", ["pt", "", "klingon"])
    def test_a_default_naming_no_supported_language_stops_the_boot(self, configured: str) -> None:
        with pytest.raises(ValidationError, match="DEFAULT_LANGUAGE must name one of"):
            AdvancedSettings(
                _env_file=None, default_language=configured, supported_languages=_EVERY_LANGUAGE
            )


class TestSupportedLanguagesSetting:
    @pytest.mark.parametrize(
        ("configured", "expected"),
        [
            ("fr,zh,en", ["fr", "zh-CN", "en"]),
            (" fr , EN ,", ["fr", "en"]),
            (["fr", "zh_CN", "fr-FR"], ["fr", "zh-CN"]),
        ],
    )
    def test_the_list_is_stored_canonical_in_its_order(
        self, configured: str | list[str], expected: list[str]
    ) -> None:
        advanced = AdvancedSettings(
            _env_file=None, default_language="fr", supported_languages=configured
        )

        assert advanced.supported_languages == expected

    def test_an_entry_naming_no_supported_language_stops_the_boot(self) -> None:
        with pytest.raises(ValidationError, match="SUPPORTED_LANGUAGES entries must each name"):
            AdvancedSettings(_env_file=None, default_language="fr", supported_languages="fr,pt")

    def test_a_default_the_instance_does_not_offer_stops_the_boot(self) -> None:
        with pytest.raises(ValidationError, match="must be one of SUPPORTED_LANGUAGES"):
            AdvancedSettings(_env_file=None, default_language="de", supported_languages="fr,en")
