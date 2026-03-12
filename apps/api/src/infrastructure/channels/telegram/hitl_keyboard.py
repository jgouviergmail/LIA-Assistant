"""
HITL inline keyboard builders for Telegram.

Creates inline keyboards for Human-in-the-Loop interactions
with localized button labels in 6 languages.

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from __future__ import annotations

# HITL button labels in 6 supported languages
HITL_BUTTON_LABELS: dict[str, dict[str, str]] = {
    "approve": {
        "fr": "Approuver",
        "en": "Approve",
        "es": "Aprobar",
        "de": "Genehmigen",
        "it": "Approvare",
        "zh": "批准",
    },
    "reject": {
        "fr": "Rejeter",
        "en": "Reject",
        "es": "Rechazar",
        "de": "Ablehnen",
        "it": "Rifiutare",
        "zh": "拒绝",
    },
    "confirm": {
        "fr": "Confirmer",
        "en": "Confirm",
        "es": "Confirmar",
        "de": "Bestätigen",
        "it": "Confermare",
        "zh": "确认",
    },
    "cancel": {
        "fr": "Annuler",
        "en": "Cancel",
        "es": "Cancelar",
        "de": "Abbrechen",
        "it": "Annullare",
        "zh": "取消",
    },
    "continue": {
        "fr": "Continuer",
        "en": "Continue",
        "es": "Continuar",
        "de": "Fortfahren",
        "it": "Continuare",
        "zh": "继续",
    },
    "stop": {
        "fr": "Arrêter",
        "en": "Stop",
        "es": "Detener",
        "de": "Stoppen",
        "it": "Fermare",
        "zh": "停止",
    },
}

# HITL type → button pair mapping
_HITL_TYPE_BUTTONS: dict[str, tuple[str, str]] = {
    "plan_approval": ("approve", "reject"),
    "destructive_confirm": ("confirm", "cancel"),
    "for_each_confirm": ("continue", "stop"),
}


def get_button_label(action: str, language: str = "fr") -> str:
    """
    Get a localized button label.

    Args:
        action: Button action key (approve, reject, confirm, cancel, continue, stop).
        language: Language code (fr, en, es, de, it, zh).

    Returns:
        Localized label string, falls back to French.
    """
    labels = HITL_BUTTON_LABELS.get(action, {})
    return labels.get(language, labels.get("fr", action.capitalize()))


def build_hitl_keyboard(
    hitl_type: str,
    conversation_id: str,
    language: str = "fr",
) -> dict:
    """
    Build an inline keyboard for a HITL interaction.

    Returns a Telegram InlineKeyboardMarkup dict for use with
    python-telegram-bot's send_message(reply_markup=...).

    For text-based HITL types (clarification, draft_critique, modifier_review),
    no keyboard is needed — the user responds with free text.

    Args:
        hitl_type: HITL type (plan_approval, destructive_confirm, for_each_confirm).
        conversation_id: Conversation ID for callback_data routing.
        language: User language for button labels.

    Returns:
        InlineKeyboardMarkup dict, or empty dict for text-based types.
    """
    button_pair = _HITL_TYPE_BUTTONS.get(hitl_type)
    if not button_pair:
        # Text-based HITL (clarification, draft_critique, modifier_review)
        # User responds with free text, no keyboard needed
        return {}

    action_positive, action_negative = button_pair

    return {
        "inline_keyboard": [
            [
                {
                    "text": get_button_label(action_positive, language),
                    "callback_data": f"hitl:{action_positive}:{conversation_id}",
                },
                {
                    "text": get_button_label(action_negative, language),
                    "callback_data": f"hitl:{action_negative}:{conversation_id}",
                },
            ]
        ]
    }


def parse_hitl_callback_data(callback_data: str) -> tuple[str, str] | None:
    """
    Parse HITL callback data from an inline keyboard button press.

    Expected format: "hitl:{action}:{conversation_id}"

    Args:
        callback_data: Raw callback_data from Telegram.

    Returns:
        Tuple of (action, conversation_id) or None if not a valid HITL callback.
    """
    if not callback_data or not callback_data.startswith("hitl:"):
        return None

    parts = callback_data.split(":", 2)
    if len(parts) != 3:
        return None

    _, action, conversation_id = parts
    if not action or not conversation_id:
        return None

    return action, conversation_id
