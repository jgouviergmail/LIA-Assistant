"""
HITL inline keyboard builders for Telegram.

Creates inline keyboards for Human-in-the-Loop interactions
with localized button labels in 6 languages.

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from typing import NamedTuple

from src.core.i18n import resolve_language

# HITL button labels in 6 supported languages
HITL_BUTTON_LABELS: dict[str, dict[str, str]] = {
    "approve": {
        "fr": "Approuver",
        "en": "Approve",
        "es": "Aprobar",
        "de": "Genehmigen",
        "it": "Approvare",
        "zh-CN": "批准",
    },
    "reject": {
        "fr": "Rejeter",
        "en": "Reject",
        "es": "Rechazar",
        "de": "Ablehnen",
        "it": "Rifiutare",
        "zh-CN": "拒绝",
    },
    "confirm": {
        "fr": "Confirmer",
        "en": "Confirm",
        "es": "Confirmar",
        "de": "Bestätigen",
        "it": "Confermare",
        "zh-CN": "确认",
    },
    "cancel": {
        "fr": "Annuler",
        "en": "Cancel",
        "es": "Cancelar",
        "de": "Abbrechen",
        "it": "Annullare",
        "zh-CN": "取消",
    },
    "continue": {
        "fr": "Continuer",
        "en": "Continue",
        "es": "Continuar",
        "de": "Fortfahren",
        "it": "Continuare",
        "zh-CN": "继续",
    },
    "stop": {
        "fr": "Arrêter",
        "en": "Stop",
        "es": "Detener",
        "de": "Stoppen",
        "it": "Fermare",
        "zh-CN": "停止",
    },
}

#: How a person answers each HITL interaction on Telegram: a pair of buttons,
#: or free text (``None``). Keyed by the type an interaction WRITES
#: (``action_requests[0]["type"]``); EVERY ``HitlInteractionType`` is declared,
#: which :func:`assert_keyboard_completeness` checks at boot — a default drew
#: Approve / Reject on every question, a clarification included, and left
#: drafts and tool confirmations to free text by fallback, not by decision.
#: A draft and a tool confirmation take the two main answers the chat's card
#: offers, and a press sends the same structured decision as a click on that
#: card; an answer that needs words (a clarification, a choice among
#: namesakes) is typed. ``plan_approval``, ``destructive_confirm`` and
#: ``edit_confirmation`` have no producer today (ADR-323): declared, never drawn.
_HITL_TYPE_BUTTONS: dict[str, tuple[str, str] | None] = {
    "plan_approval": ("approve", "reject"),
    "destructive_confirm": ("confirm", "cancel"),
    "for_each_confirmation": ("continue", "stop"),
    "draft_critique": ("confirm", "cancel"),
    "tool_confirmation": ("confirm", "cancel"),
    "clarification": None,
    "entity_disambiguation": None,
    "edit_confirmation": None,
}

#: Every action a keyboard draws — the only actions a press may carry back.
_DRAWN_ACTIONS: frozenset[str] = frozenset(
    action for pair in _HITL_TYPE_BUTTONS.values() if pair for action in pair
)
if not _DRAWN_ACTIONS <= HITL_BUTTON_LABELS.keys():
    raise RuntimeError(
        "every drawn HITL action needs its labels: "
        f"{sorted(_DRAWN_ACTIONS - HITL_BUTTON_LABELS.keys())}"
    )

#: The prefix of every HITL button's callback data.
_CALLBACK_PREFIX = "hitl"
#: Hexadecimal digits of the question's fingerprint a button carries.
_QUESTION_FINGERPRINT_CHARS = 8
_QUESTION_FINGERPRINT = re.compile(rf"[0-9a-f]{{{_QUESTION_FINGERPRINT_CHARS}}}")
#: Telegram's bound on a button's callback data, in bytes (Bot API,
#: ``InlineKeyboardButton.callback_data``: 1-64 bytes).
TELEGRAM_CALLBACK_DATA_MAX_BYTES = 64


class HitlPress(NamedTuple):
    """What a HITL button press carries back.

    Attributes:
        action: The button's action (one a keyboard draws).
        conversation_id: The conversation the question was asked in.
        question: The fingerprint of the question the button answers
            (:func:`question_fingerprint` of its message id).
    """

    action: str
    conversation_id: str
    question: str


def question_fingerprint(message_id: str) -> str:
    """The mark a button carries of the ONE question it answers.

    A question's message id (``hitl_{conversation_id}_{interrupt_id}``) is too
    long for a callback's 64 bytes beside the conversation id, so the button
    carries the first digits of its SHA-256. The door resumes a press only
    when the pending question has the same fingerprint: a button left in the
    chat under an earlier question must never answer the one now waiting.

    Args:
        message_id: The question's message id, as the engine writes it.

    Returns:
        The fingerprint: ``_QUESTION_FINGERPRINT_CHARS`` lowercase hex digits.
    """
    digest = hashlib.sha256(message_id.encode("utf-8")).hexdigest()
    return digest[:_QUESTION_FINGERPRINT_CHARS]


def assert_keyboard_completeness(interaction_types: Iterable[str]) -> None:
    """Assert every HITL interaction type declares how Telegram answers it.

    Called at startup with ``HitlInteractionType``'s values (ADR-085 pattern): a
    type added without a declaration refuses to boot, where ``.get()`` would
    otherwise answer « free text » for it in silence.

    Args:
        interaction_types: Every interaction type the application defines.

    Raises:
        AssertionError: Naming the types left undeclared, and the declared
            ones no interaction type carries.
    """
    wanted = set(interaction_types)
    missing = sorted(wanted - _HITL_TYPE_BUTTONS.keys())
    stale = sorted(_HITL_TYPE_BUTTONS.keys() - wanted)
    if missing or stale:
        raise AssertionError(
            f"Telegram HITL keyboard: undeclared {missing}, declared but unknown {stale}. "
            "Declare each interaction type as a button pair or as free text (None) in "
            "src/infrastructure/channels/telegram/hitl_keyboard.py."
        )


def get_button_label(action: str, language: str | None = None) -> str:
    """
    Get a localized button label.

    Args:
        action: Button action key (approve, reject, confirm, cancel, continue, stop).
        language: Language code in any spelling; the declared language when
            absent (ADR-323).

    Returns:
        Localized label string (the capitalized action for an unknown action).
    """
    labels = HITL_BUTTON_LABELS.get(action, {})
    return labels.get(resolve_language(language), action.capitalize())


def build_hitl_keyboard(
    hitl_type: str,
    conversation_id: str,
    question_id: str,
    language: str | None = None,
) -> dict:
    """
    Build an inline keyboard for a HITL interaction.

    Returns a Telegram InlineKeyboardMarkup dict for use with
    python-telegram-bot's send_message(reply_markup=...).

    A type declared free text (a clarification, a choice among namesakes)
    draws no keyboard: the person answers in words. Each button's callback
    data is ``hitl:{action}:{conversation_id}:{fingerprint}``, the fingerprint
    naming the question the button answers (:func:`question_fingerprint`).

    Args:
        hitl_type: The interaction type, as the interaction writes it (see
            ``_HITL_TYPE_BUTTONS``; an unknown one draws none).
        conversation_id: Conversation ID for callback_data routing.
        question_id: The question's message id, as the engine streams it.
        language: Language code in any spelling; the declared language when
            absent (ADR-323).

    Returns:
        InlineKeyboardMarkup dict, or empty dict for text-based types.
    """
    language = resolve_language(language)
    button_pair = _HITL_TYPE_BUTTONS.get(hitl_type)
    if not button_pair:
        # Declared free text (or unknown): the person answers in words.
        return {}

    question = question_fingerprint(question_id)
    return {
        "inline_keyboard": [
            [
                {
                    "text": get_button_label(action, language),
                    "callback_data": ":".join(
                        (_CALLBACK_PREFIX, action, conversation_id, question)
                    ),
                }
                for action in button_pair
            ]
        ]
    }


def parse_hitl_callback_data(callback_data: str | None) -> HitlPress | None:
    """
    Parse HITL callback data from an inline keyboard button press.

    Expected format: ``hitl:{action}:{conversation_id}:{fingerprint}``. A
    button drawn before buttons carried their question
    (``hitl:{action}:{conversation_id}``, still in chats' histories) parses
    with an EMPTY fingerprint, which no waiting question has: the door answers
    it « expired » rather than guessing which question it meant.

    Args:
        callback_data: Raw callback_data from Telegram (None when absent).

    Returns:
        The press, or None if not a valid HITL callback — an action no
        keyboard draws included: the data is the client's, and an action no
        keyboard offers would reach the person's turn.
    """
    parts = (callback_data or "").split(":")
    if len(parts) == 3:
        parts.append("")
    if len(parts) != 4 or parts[0] != _CALLBACK_PREFIX:
        return None

    _, action, conversation_id, question = parts
    if action not in _DRAWN_ACTIONS or not conversation_id:
        return None
    if question and not _QUESTION_FINGERPRINT.fullmatch(question):
        return None

    return HitlPress(action, conversation_id, question)
