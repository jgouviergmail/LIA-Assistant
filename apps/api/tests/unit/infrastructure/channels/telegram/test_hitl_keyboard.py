"""Tests for HITL inline keyboard builders."""

from __future__ import annotations

from src.infrastructure.channels.telegram.hitl_keyboard import (
    HITL_BUTTON_LABELS,
    build_hitl_keyboard,
    get_button_label,
    parse_hitl_callback_data,
)

# =============================================================================
# get_button_label
# =============================================================================


class TestGetButtonLabel:
    """Tests for get_button_label."""

    def test_returns_french_label(self) -> None:
        assert get_button_label("approve", "fr") == "Approuver"

    def test_returns_english_label(self) -> None:
        assert get_button_label("reject", "en") == "Reject"

    def test_returns_spanish_label(self) -> None:
        assert get_button_label("confirm", "es") == "Confirmar"

    def test_returns_german_label(self) -> None:
        assert get_button_label("cancel", "de") == "Abbrechen"

    def test_returns_italian_label(self) -> None:
        assert get_button_label("continue", "it") == "Continuare"

    def test_returns_chinese_label(self) -> None:
        assert get_button_label("stop", "zh") == "停止"

    def test_falls_back_to_french(self) -> None:
        """Unknown language should fall back to French."""
        assert get_button_label("approve", "ja") == "Approuver"

    def test_unknown_action_returns_capitalized(self) -> None:
        """Unknown action should return action.capitalize()."""
        assert get_button_label("unknown_action", "fr") == "Unknown_action"

    def test_all_actions_have_six_languages(self) -> None:
        """Every action in HITL_BUTTON_LABELS must have all 6 languages."""
        expected_languages = {"fr", "en", "es", "de", "it", "zh"}
        for action, labels in HITL_BUTTON_LABELS.items():
            assert set(labels.keys()) == expected_languages, f"Missing languages for {action}"


# =============================================================================
# build_hitl_keyboard
# =============================================================================


class TestBuildHitlKeyboard:
    """Tests for build_hitl_keyboard."""

    def test_plan_approval_keyboard(self) -> None:
        """Plan approval → Approuver / Rejeter buttons."""
        kb = build_hitl_keyboard("plan_approval", "conv-123", "fr")
        assert "inline_keyboard" in kb
        buttons = kb["inline_keyboard"][0]
        assert len(buttons) == 2
        assert buttons[0]["text"] == "Approuver"
        assert buttons[1]["text"] == "Rejeter"

    def test_destructive_confirm_keyboard(self) -> None:
        """Destructive confirm → Confirmer / Annuler buttons."""
        kb = build_hitl_keyboard("destructive_confirm", "conv-456", "en")
        buttons = kb["inline_keyboard"][0]
        assert buttons[0]["text"] == "Confirm"
        assert buttons[1]["text"] == "Cancel"

    def test_for_each_confirm_keyboard(self) -> None:
        """FOR_EACH confirm → Continuer / Arrêter buttons."""
        kb = build_hitl_keyboard("for_each_confirm", "conv-789", "de")
        buttons = kb["inline_keyboard"][0]
        assert buttons[0]["text"] == "Fortfahren"
        assert buttons[1]["text"] == "Stoppen"

    def test_callback_data_format(self) -> None:
        """Callback data should follow hitl:{action}:{conversation_id} format."""
        kb = build_hitl_keyboard("plan_approval", "conv-abc", "fr")
        buttons = kb["inline_keyboard"][0]
        assert buttons[0]["callback_data"] == "hitl:approve:conv-abc"
        assert buttons[1]["callback_data"] == "hitl:reject:conv-abc"

    def test_text_based_hitl_returns_empty_dict(self) -> None:
        """Clarification, draft_critique, modifier_review → empty dict (no keyboard)."""
        assert build_hitl_keyboard("clarification", "conv-1", "fr") == {}
        assert build_hitl_keyboard("draft_critique", "conv-2", "fr") == {}
        assert build_hitl_keyboard("modifier_review", "conv-3", "fr") == {}

    def test_unknown_hitl_type_returns_empty_dict(self) -> None:
        """Unknown HITL types → empty dict."""
        assert build_hitl_keyboard("unknown_type", "conv-4", "fr") == {}


# =============================================================================
# parse_hitl_callback_data
# =============================================================================


class TestParseHitlCallbackData:
    """Tests for parse_hitl_callback_data."""

    def test_valid_callback_data(self) -> None:
        result = parse_hitl_callback_data("hitl:approve:conv-123")
        assert result == ("approve", "conv-123")

    def test_reject_callback(self) -> None:
        result = parse_hitl_callback_data("hitl:reject:conv-456")
        assert result == ("reject", "conv-456")

    def test_conversation_id_with_colons(self) -> None:
        """Conversation ID may contain colons (split max 2)."""
        result = parse_hitl_callback_data("hitl:confirm:some:complex:id")
        assert result == ("confirm", "some:complex:id")

    def test_empty_string_returns_none(self) -> None:
        assert parse_hitl_callback_data("") is None

    def test_none_returns_none(self) -> None:
        assert parse_hitl_callback_data(None) is None  # type: ignore[arg-type]

    def test_not_hitl_prefix_returns_none(self) -> None:
        assert parse_hitl_callback_data("other:approve:conv") is None

    def test_missing_parts_returns_none(self) -> None:
        assert parse_hitl_callback_data("hitl:approve") is None

    def test_empty_action_returns_none(self) -> None:
        assert parse_hitl_callback_data("hitl::conv-123") is None

    def test_empty_conversation_id_returns_none(self) -> None:
        assert parse_hitl_callback_data("hitl:approve:") is None
