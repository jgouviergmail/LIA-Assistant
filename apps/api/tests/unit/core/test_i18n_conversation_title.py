"""Default conversation title — localized in all 6 languages (W6).

Regression context: ``ConversationService._generate_title`` returned a
hard-coded French string (``f"Conversation du {DD/MM/YYYY}"``) and its own
docstring admitted it ("French default"). The title travels to the client in
``ConversationResponse.title``, so it is a user-facing string and falls under
the systemic rule "backend user-visible strings go through the central i18n
mechanisms — never inline French in Python".

These tests pin the contract of the new table AND the service helper that
consumes it. The all-languages-present check itself is covered generically by
``test_i18n_parity`` (it scans every ``core.i18n_*`` table).
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest

from src.core.i18n import SUPPORTED_LANGUAGES
from src.core.i18n_api_messages import APIMessages

pytestmark = [pytest.mark.unit]

SRC_ROOT = Path(__file__).resolve().parents[3] / "src"

# A date whose day and month are NOT interchangeable, so an inverted
# day/month format is caught rather than silently passing.
SAMPLE = date(2026, 7, 26)


class TestConversationDefaultTitle:
    """The localized default title table."""

    @pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
    def test_returns_a_non_empty_title_for_every_supported_language(self, language: str) -> None:
        title = APIMessages.conversation_default_title(SAMPLE, language)
        assert title, f"empty title for {language}"
        assert title.strip() == title

    @pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
    def test_every_language_carries_the_date(self, language: str) -> None:
        """The date must appear whatever the locale's date convention is."""
        title = APIMessages.conversation_default_title(SAMPLE, language)
        assert "2026" in title
        assert "26" in title

    def test_languages_produce_distinct_wording(self) -> None:
        """A copy-paste of the French value into every slot would pass the
        parity guard but defeat the purpose — the wordings must differ."""
        titles = {
            lang: APIMessages.conversation_default_title(SAMPLE, lang)
            for lang in SUPPORTED_LANGUAGES
        }
        assert len(set(titles.values())) == len(SUPPORTED_LANGUAGES), titles

    def test_french_keeps_the_historical_wording(self) -> None:
        """The pre-existing French title is preserved verbatim (no churn for
        the existing rows / no visible change for French users)."""
        assert APIMessages.conversation_default_title(SAMPLE, "fr") == (
            "Conversation du 26/07/2026"
        )

    def test_unknown_language_falls_back_to_english(self) -> None:
        assert APIMessages.conversation_default_title(
            SAMPLE, "pt"
        ) == APIMessages.conversation_default_title(SAMPLE, "en")

    def test_table_is_keyed_on_the_backend_canonical_chinese_code(self) -> None:
        """Backend canonical is ``zh-CN``. This table follows the module's
        convention (plain ``.get(language, en)``, no normalization) — routing a
        raw locale through ``normalize_language`` is the CALLER's job, and is
        pinned on the service below. A table keyed on ``zh`` would break the
        nominal path, so the canonical code must resolve."""
        assert APIMessages.conversation_default_title(
            SAMPLE, "zh-CN"
        ) != APIMessages.conversation_default_title(SAMPLE, "en")

    def test_no_language_defaults_to_french(self) -> None:
        """Callers that cannot resolve a language keep today's behaviour."""
        assert APIMessages.conversation_default_title(SAMPLE) == (
            APIMessages.conversation_default_title(SAMPLE, "fr")
        )


class TestServiceGeneratesLocalizedTitle:
    """``ConversationService._generate_title`` consumes the table.

    The helper reads "today" internally, so the assertions are on STRUCTURE
    (locale-specific wording, distinct per language) rather than on an exact
    string: pinning a value computed from a second ``today()`` call would flake
    at midnight, and the date content itself is already pinned above on a fixed
    date.
    """

    def test_generates_a_distinct_wording_per_language(self) -> None:
        from src.domains.conversations.service import ConversationService

        service = ConversationService()
        titles = {lang: service._generate_title(lang) for lang in SUPPORTED_LANGUAGES}
        assert len(set(titles.values())) == len(SUPPORTED_LANGUAGES), titles

    @pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
    def test_matches_the_table_wording_for_that_language(self, language: str) -> None:
        """Same wording and same date SHAPE as the table — only the digits differ.

        Compared on the digit-stripped skeleton rather than on a leading prefix:
        the Chinese title starts with the date (``{date}的对话``), so a
        prefix-based check would compare the empty string and assert nothing at
        all for the one locale whose format differs most.
        """
        from src.domains.conversations.service import ConversationService

        def skeleton(title: str) -> str:
            return "".join("#" if ch.isdigit() else ch for ch in title)

        reference = APIMessages.conversation_default_title(SAMPLE, language)
        generated = ConversationService()._generate_title(language)
        assert skeleton(generated) == skeleton(reference)

    def test_defaults_to_french_when_no_language_is_given(self) -> None:
        from src.domains.conversations.service import ConversationService

        service = ConversationService()
        assert service._generate_title() == service._generate_title("fr")

    def test_normalizes_a_raw_locale_before_lookup(self) -> None:
        """The service is the chokepoint: a raw frontend locale (``zh``,
        ``fr-FR``) must be routed through ``normalize_language`` so it lands on
        the backend-canonical entry instead of silently falling back to
        English."""
        from src.domains.conversations.service import ConversationService

        service = ConversationService()
        assert service._generate_title("zh") == service._generate_title("zh-CN")
        assert service._generate_title("fr-FR") == service._generate_title("fr")


class TestEveryCallSitePassesTheLanguage:
    """No caller may silently fall back to French.

    The localized table and the localized helper are useless if the callers
    keep invoking ``get_or_create_conversation(user_id, db)``. That is exactly
    what happened when this work first landed: the table shipped, the service
    shipped, and only ONE of the four call sites was updated — the least
    travelled one. The nominal chat path (``ConversationOrchestrator``) kept
    producing a French title for every account in every language, and no test
    could see it because each piece was correct in isolation.

    This scan is therefore on the CALL SITES, which is where the defect lived.
    Shrink-only in spirit: a new caller must state its language, even if that
    statement is an explicit ``language=None``.
    """

    @staticmethod
    def _call_sites() -> list[tuple[str, int, ast.Call]]:
        found: list[tuple[str, int, ast.Call]] = []
        for path in SRC_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get_or_create_conversation"
                ):
                    found.append((str(path.relative_to(SRC_ROOT)), node.lineno, node))
        return found

    def test_the_scan_still_finds_the_call_sites(self) -> None:
        """Guard against the guard rotting into a no-op."""
        assert len(self._call_sites()) >= 4

    def test_no_call_site_omits_the_language(self) -> None:
        offenders = [
            f"{rel}:{line}"
            for rel, line, call in self._call_sites()
            if not any(kw.arg == "language" for kw in call.keywords)
        ]
        assert offenders == [], (
            "these callers create a conversation without stating a language, so "
            "its user-facing default title falls back to French: " + ", ".join(offenders)
        )
