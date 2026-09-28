"""Tests for HITL inline keyboard builders."""

from __future__ import annotations

import re
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.i18n import language_scope
from src.infrastructure.channels.telegram.hitl_keyboard import (
    _HITL_TYPE_BUTTONS,
    HITL_BUTTON_LABELS,
    TELEGRAM_CALLBACK_DATA_MAX_BYTES,
    HitlPress,
    build_hitl_keyboard,
    get_button_label,
    parse_hitl_callback_data,
    question_fingerprint,
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

    def test_an_unknown_language_reads_as_the_instance_default(self) -> None:
        """An unsupported code reads as the instance default (ADR-323)."""
        assert (
            get_button_label("approve", "ja")
            == HITL_BUTTON_LABELS["approve"][settings.default_language]
        )

    def test_an_absent_language_is_the_declared_one(self) -> None:
        # Not the instance default, or the test could pass by falling back.
        declared = next(code for code in ("de", "it") if code != settings.default_language)
        with language_scope(declared):
            assert get_button_label("approve") == HITL_BUTTON_LABELS["approve"][declared]

    def test_unknown_action_returns_capitalized(self) -> None:
        """Unknown action should return action.capitalize()."""
        assert get_button_label("unknown_action", "fr") == "Unknown_action"

    def test_all_actions_have_six_languages(self) -> None:
        """Every action in HITL_BUTTON_LABELS must have all 6 languages."""
        expected_languages = {"fr", "en", "es", "de", "it", "zh-CN"}
        for action, labels in HITL_BUTTON_LABELS.items():
            assert set(labels.keys()) == expected_languages, f"Missing languages for {action}"


# =============================================================================
# build_hitl_keyboard
# =============================================================================

#: A question's message id, as the engine writes it.
_QUESTION = "hitl_conv-1_interrupt-1"


class TestBuildHitlKeyboard:
    """Tests for build_hitl_keyboard."""

    def test_plan_approval_keyboard(self) -> None:
        """Plan approval → Approuver / Rejeter buttons."""
        kb = build_hitl_keyboard("plan_approval", "conv-123", _QUESTION, "fr")
        assert "inline_keyboard" in kb
        buttons = kb["inline_keyboard"][0]
        assert len(buttons) == 2
        assert buttons[0]["text"] == "Approuver"
        assert buttons[1]["text"] == "Rejeter"

    def test_destructive_confirm_keyboard(self) -> None:
        """Destructive confirm → Confirmer / Annuler buttons."""
        kb = build_hitl_keyboard("destructive_confirm", "conv-456", _QUESTION, "en")
        buttons = kb["inline_keyboard"][0]
        assert buttons[0]["text"] == "Confirm"
        assert buttons[1]["text"] == "Cancel"

    def test_for_each_confirm_keyboard(self) -> None:
        """FOR_EACH confirm → Continuer / Arrêter buttons, under the type the
        interaction writes (``for_each_confirmation``; the key this test froze,
        ``for_each_confirm``, no interaction wrote)."""
        kb = build_hitl_keyboard("for_each_confirmation", "conv-789", _QUESTION, "de")
        buttons = kb["inline_keyboard"][0]
        assert buttons[0]["text"] == "Fortfahren"
        assert buttons[1]["text"] == "Stoppen"

    def test_callback_data_names_the_conversation_and_the_question(self) -> None:
        """``hitl:{action}:{conversation_id}:{fingerprint}``: a press says which
        question it answers, so a button left under an earlier one cannot
        answer the question now waiting."""
        kb = build_hitl_keyboard("plan_approval", "conv-abc", _QUESTION, "fr")
        buttons = kb["inline_keyboard"][0]
        mark = question_fingerprint(_QUESTION)
        assert buttons[0]["callback_data"] == f"hitl:approve:conv-abc:{mark}"
        assert buttons[1]["callback_data"] == f"hitl:reject:conv-abc:{mark}"

    def test_the_callback_data_fits_telegram_s_bound(self) -> None:
        """The longest action beside a real conversation id stays within the
        Bot API's 64 bytes, or Telegram refuses the whole keyboard."""
        longest = max(
            (pair for pair in _HITL_TYPE_BUTTONS.values() if pair),
            key=lambda pair: max(len(action) for action in pair),
        )
        kind = next(kind for kind, pair in _HITL_TYPE_BUTTONS.items() if pair == longest)
        keyboard = build_hitl_keyboard(kind, str(uuid4()), f"hitl_{uuid4()}_{'f' * 32}", "fr")

        sizes = [len(b["callback_data"].encode("utf-8")) for b in keyboard["inline_keyboard"][0]]

        assert max(sizes) <= TELEGRAM_CALLBACK_DATA_MAX_BYTES

    @pytest.mark.parametrize(
        ("hitl_type", "actions"),
        [
            ("plan_approval", ("approve", "reject")),
            ("destructive_confirm", ("confirm", "cancel")),
            ("for_each_confirmation", ("continue", "stop")),
            ("draft_critique", ("confirm", "cancel")),
            ("tool_confirmation", ("confirm", "cancel")),
            ("clarification", None),
            ("entity_disambiguation", None),
            ("edit_confirmation", None),
        ],
    )
    def test_each_interaction_is_answered_as_declared(
        self, hitl_type: str, actions: tuple[str, str] | None
    ) -> None:
        """Buttons where the answer is a choice the chat's card offers too, words
        where it needs them — a decision per type, never a fallback."""
        keyboard = build_hitl_keyboard(hitl_type, "conv-1", _QUESTION, "fr")

        if actions is None:
            assert keyboard == {}
        else:
            mark = question_fingerprint(_QUESTION)
            drawn = [b["callback_data"] for b in keyboard["inline_keyboard"][0]]
            assert drawn == [f"hitl:{action}:conv-1:{mark}" for action in actions]

    def test_unknown_hitl_type_returns_empty_dict(self) -> None:
        """Unknown HITL types → empty dict."""
        assert build_hitl_keyboard("unknown_type", "conv-4", _QUESTION, "fr") == {}


# =============================================================================
# question_fingerprint
# =============================================================================


class TestQuestionFingerprint:
    """The mark a button carries of its question."""

    def test_it_is_eight_lowercase_hex_digits(self) -> None:
        assert re.fullmatch(r"[0-9a-f]{8}", question_fingerprint(_QUESTION))

    def test_the_same_question_has_the_same_mark(self) -> None:
        assert question_fingerprint(_QUESTION) == question_fingerprint(str(_QUESTION))

    def test_two_questions_of_one_conversation_have_two_marks(self) -> None:
        """The next question of the same conversation: a button of the first
        must not answer it."""
        assert question_fingerprint("hitl_conv-1_interrupt-1") != question_fingerprint(
            "hitl_conv-1_interrupt-2"
        )


# =============================================================================
# parse_hitl_callback_data
# =============================================================================


class TestParseHitlCallbackData:
    """Tests for parse_hitl_callback_data."""

    def test_valid_callback_data(self) -> None:
        result = parse_hitl_callback_data("hitl:approve:conv-123:0a1b2c3d")
        assert result == HitlPress("approve", "conv-123", "0a1b2c3d")

    def test_reject_callback(self) -> None:
        result = parse_hitl_callback_data("hitl:reject:conv-456:0a1b2c3d")
        assert result == HitlPress("reject", "conv-456", "0a1b2c3d")

    def test_a_button_drawn_before_the_fingerprint_names_no_question(self) -> None:
        """A keyboard still in a chat's history: parsed, with a fingerprint no
        waiting question has — the door answers it « expired »."""
        result = parse_hitl_callback_data("hitl:confirm:conv-123")
        assert result == HitlPress("confirm", "conv-123", "")

    def test_a_conversation_id_holding_a_colon_is_refused(self) -> None:
        """No keyboard draws one: a conversation id is a UUID."""
        assert parse_hitl_callback_data("hitl:confirm:some:complex:id") is None

    @pytest.mark.parametrize("mark", ["0A1B2C3D", "0a1b2c3", "0a1b2c3d4", "0a1b2c3g"])
    def test_a_malformed_fingerprint_is_refused(self, mark: str) -> None:
        assert parse_hitl_callback_data(f"hitl:confirm:conv-123:{mark}") is None

    def test_empty_string_returns_none(self) -> None:
        assert parse_hitl_callback_data("") is None

    def test_none_returns_none(self) -> None:
        assert parse_hitl_callback_data(None) is None

    def test_not_hitl_prefix_returns_none(self) -> None:
        assert parse_hitl_callback_data("other:approve:conv:0a1b2c3d") is None

    def test_missing_parts_returns_none(self) -> None:
        assert parse_hitl_callback_data("hitl:approve") is None

    def test_empty_action_returns_none(self) -> None:
        assert parse_hitl_callback_data("hitl::conv-123:0a1b2c3d") is None

    @pytest.mark.parametrize(
        "hitl_type",
        [
            "plan_approval",
            "destructive_confirm",
            "for_each_confirmation",
            "draft_critique",
            "tool_confirmation",
        ],
    )
    def test_every_drawn_button_parses_back(self, hitl_type: str) -> None:
        """The parser's vocabulary is what the keyboards draw: a button whose
        action the parser refused was dropped with a warning and no answer."""
        keyboard = build_hitl_keyboard(hitl_type, "conv-1", _QUESTION, "fr")
        buttons = keyboard["inline_keyboard"][0]
        pair = _HITL_TYPE_BUTTONS[hitl_type]

        parsed = [parse_hitl_callback_data(button["callback_data"]) for button in buttons]

        assert pair is not None
        assert parsed == [
            HitlPress(action, "conv-1", question_fingerprint(_QUESTION)) for action in pair
        ]

    def test_every_interaction_type_is_declared_and_nothing_else(self) -> None:
        """What the boot checks: a key no interaction writes is a keyboard nobody
        sees (the FOR_EACH one was keyed ``for_each_confirm``), and a type left
        out was answered « free text » by ``.get()``, in silence."""
        from src.domains.agents.services.hitl.protocols import HitlInteractionType
        from src.infrastructure.channels.telegram.hitl_keyboard import (
            assert_keyboard_completeness,
        )

        assert_keyboard_completeness(kind.value for kind in HitlInteractionType)

    def test_an_undeclared_interaction_type_is_named(self) -> None:
        from src.domains.agents.services.hitl.protocols import HitlInteractionType
        from src.infrastructure.channels.telegram.hitl_keyboard import (
            assert_keyboard_completeness,
        )

        with pytest.raises(AssertionError, match="undeclared \\['new_interaction'\\]"):
            assert_keyboard_completeness(
                [*(kind.value for kind in HitlInteractionType), "new_interaction"]
            )

    def test_a_declaration_no_interaction_carries_is_named(self) -> None:
        from src.domains.agents.services.hitl.protocols import HitlInteractionType
        from src.infrastructure.channels.telegram.hitl_keyboard import (
            assert_keyboard_completeness,
        )

        remaining = [kind.value for kind in HitlInteractionType if kind.value != "clarification"]
        with pytest.raises(AssertionError, match="declared but unknown \\['clarification'\\]"):
            assert_keyboard_completeness(remaining)

    def test_the_boot_refuses_an_incomplete_declaration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A check the lifespan never runs protects nothing."""
        from src.infrastructure.channels.telegram import hitl_keyboard
        from src.infrastructure.startup import registries

        declared = {
            kind: answer
            for kind, answer in hitl_keyboard._HITL_TYPE_BUTTONS.items()
            if kind != "tool_confirmation"
        }
        monkeypatch.setattr(hitl_keyboard, "_HITL_TYPE_BUTTONS", declared)

        with pytest.raises(RuntimeError, match="Telegram HITL keyboard incomplete"):
            registries.run_failfast_validations()

    @pytest.mark.parametrize("action", ["delete_everything", "Approve", "approve "])
    def test_an_action_no_keyboard_draws_returns_none(self, action: str) -> None:
        """The client's data: an action nobody offered reached the person's
        message, their resumed turn and an INFO log line."""
        assert parse_hitl_callback_data(f"hitl:{action}:conv-123:0a1b2c3d") is None

    def test_empty_conversation_id_returns_none(self) -> None:
        assert parse_hitl_callback_data("hitl:approve::0a1b2c3d") is None
