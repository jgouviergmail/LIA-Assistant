"""
Unit tests for HITL disambiguation i18n messages.

Tests the formatting functions for entity disambiguation questions.
"""

import pytest

from src.core.config import settings
from src.core.i18n_hitl import HitlMessages, HitlMessageType


class TestDisambiguationMessages:
    """Tests for disambiguation message formatting."""

    # =========================================================================
    # Test: Fallback messages
    # =========================================================================

    def test_get_fallback_french(self):
        """Should return French fallback message."""
        msg = HitlMessages.get_fallback(HitlMessageType.ENTITY_DISAMBIGUATION, "fr")
        assert "plusieurs correspondances" in msg.lower()

    def test_get_fallback_english(self):
        """Should return English fallback message."""
        msg = HitlMessages.get_fallback(HitlMessageType.ENTITY_DISAMBIGUATION, "en")
        assert "multiple matches" in msg.lower()

    def test_get_fallback_unknown_language(self):
        """An unknown language reads the instance's configured default."""
        msg = HitlMessages.get_fallback(HitlMessageType.ENTITY_DISAMBIGUATION, "xyz")
        assert msg == HitlMessages.get_fallback(
            HitlMessageType.ENTITY_DISAMBIGUATION, settings.default_language
        )

    # =========================================================================
    # Test: Multiple entities disambiguation
    # =========================================================================

    def test_format_multiple_entities_french(self):
        """Should format multiple entities question in French."""
        candidates = [
            {"index": 1, "name": "Jean Dupont", "email": "jean.d@example.com"},
            {"index": 2, "name": "Jean-Pierre Dupont", "email": "jp@example.com"},
        ]

        result = HitlMessages.format_disambiguation_question(
            disambiguation_type="multiple_entities",
            domain="contacts",
            original_query="Jean",
            intended_action="send_email",
            candidates=candidates,
            target_field="email",
            language="fr",
        )

        assert "Jean" in result
        assert "Jean Dupont" in result
        assert "Jean-Pierre Dupont" in result
        assert "1." in result or "**1.**" in result
        assert "2." in result or "**2.**" in result
        assert "jean.d@example.com" in result

    def test_format_multiple_entities_english(self):
        """Should format multiple entities question in English."""
        candidates = [
            {"index": 1, "name": "John Smith", "email": "john@example.com"},
            {"index": 2, "name": "John Doe", "email": "jdoe@example.com"},
        ]

        result = HitlMessages.format_disambiguation_question(
            disambiguation_type="multiple_entities",
            domain="contacts",
            original_query="John",
            intended_action="send_email",
            candidates=candidates,
            target_field="email",
            language="en",
        )

        assert "John" in result
        assert "John Smith" in result
        assert "John Doe" in result
        assert "choice" in result.lower() or "indicate" in result.lower()

    # =========================================================================
    # Test: Multiple fields disambiguation
    # =========================================================================

    def test_format_multiple_fields_french(self):
        """Should format multiple fields question in French."""
        candidates = [
            {"index": 1, "value": "jean@work.com", "label": "work", "parent_name": "Jean Dupont"},
            {"index": 2, "value": "jean@home.com", "label": "home", "parent_name": "Jean Dupont"},
        ]

        result = HitlMessages.format_disambiguation_question(
            disambiguation_type="multiple_fields",
            domain="contacts",
            original_query="Jean Dupont",
            intended_action="send_email",
            candidates=candidates,
            target_field="email",
            language="fr",
        )

        assert "Jean Dupont" in result
        assert "jean@work.com" in result
        assert "jean@home.com" in result
        assert "email" in result.lower()

    def test_format_multiple_fields_phone(self):
        """Should format multiple phone numbers question."""
        candidates = [
            {"index": 1, "value": "0123456789", "label": "mobile", "parent_name": "Jean Dupont"},
            {"index": 2, "value": "0987654321", "label": "work", "parent_name": "Jean Dupont"},
        ]

        result = HitlMessages.format_disambiguation_question(
            disambiguation_type="multiple_fields",
            domain="contacts",
            original_query="Jean Dupont",
            intended_action="call",
            candidates=candidates,
            target_field="phone",
            language="fr",
        )

        assert "0123456789" in result
        assert "0987654321" in result
        assert "téléphone" in result.lower() or "phone" in result.lower()

    @pytest.mark.parametrize(
        ("field", "language", "sentence"),
        [
            ("email", "en", "Jean Dupont has several email addresses."),
            ("email", "de", "Jean Dupont hat mehrere E-Mail-Adressen."),
            ("phone", "de", "Jean Dupont hat mehrere Telefonnummern."),
            ("email", "fr", "Jean Dupont a plusieurs adresses email. Laquelle"),
            ("phone", "fr", "Jean Dupont a plusieurs numéros de téléphone. Lequel"),
            ("email", "es", "Jean Dupont tiene varias direcciones de correo."),
            ("phone", "it", "Jean Dupont ha più numeri di telefono."),
            ("phoneNumber", "en", "Jean Dupont has several possible values."),
        ],
    )
    def test_the_field_is_named_in_a_whole_sentence(
        self, field: str, language: str, sentence: str
    ) -> None:
        """A label pluralised by appending « s » read « email addresss »,
        « Telefonnummers », « varios dirección de correos »; a field no sentence
        names is said without its raw key."""
        candidates = [
            {"index": 1, "value": "a", "parent_name": "Jean Dupont"},
            {"index": 2, "value": "b", "parent_name": "Jean Dupont"},
        ]

        result = HitlMessages.format_disambiguation_question(
            disambiguation_type="multiple_fields",
            domain="contacts",
            original_query="Jean Dupont",
            intended_action="call",
            candidates=candidates,
            target_field=field,
            language=language,
        )

        assert result.startswith(sentence)

    # =========================================================================
    # Test: Empty candidates
    # =========================================================================

    def test_format_empty_candidates(self):
        """Should return fallback for empty candidates."""
        result = HitlMessages.format_disambiguation_question(
            disambiguation_type="multiple_entities",
            domain="contacts",
            original_query="Nobody",
            intended_action="send_email",
            candidates=[],
            target_field="email",
            language="fr",
        )

        # Should return fallback message
        assert result == HitlMessages.get_fallback(HitlMessageType.ENTITY_DISAMBIGUATION, "fr")

    # =========================================================================
    # Test: All supported languages
    # =========================================================================

    @pytest.mark.parametrize("language", ["fr", "en", "es", "de", "it", "zh-CN"])
    def test_format_all_languages(self, language):
        """Should format disambiguation for all supported languages."""
        candidates = [
            {"index": 1, "name": "Test User 1", "email": "test1@example.com"},
            {"index": 2, "name": "Test User 2", "email": "test2@example.com"},
        ]

        result = HitlMessages.format_disambiguation_question(
            disambiguation_type="multiple_entities",
            domain="contacts",
            original_query="Test",
            intended_action="send_email",
            candidates=candidates,
            target_field="email",
            language=language,
        )

        # Should contain candidate names
        assert "Test User 1" in result
        assert "Test User 2" in result
        # Should have numbered options
        assert "1" in result
        assert "2" in result
