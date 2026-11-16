"""The two answers of a message that did not leave, as Telegram buttons (lot 34).

A release that did not end normally holds what the person wrote meanwhile
(ADR-384): it leaves only on their click. The chat draws « Send now » and
« Withdraw » on the waiting bubble; on Telegram the notice that says the message
did not leave carries the same two answers. Each button names the waiting
message it was drawn for (``wait:{action}:{waiting_id}``, 50 bytes of the 64
Telegram allows), and the door acts only while that message is the one waiting.
"""

from __future__ import annotations

from typing import NamedTuple
from uuid import UUID

from src.core.i18n import resolve_language
from src.infrastructure.channels.assistant_gateway import WaitingAction

#: The prefix of every waiting-message button's callback data.
WAITING_CALLBACK_PREFIX = "wait"

#: The labels of the two buttons, in the six languages.
WAITING_BUTTON_LABELS: dict[str, dict[str, str]] = {
    WaitingAction.SEND.value: {
        "fr": "Envoyer",
        "en": "Send",
        "es": "Enviar",
        "de": "Senden",
        "it": "Invia",
        "zh-CN": "发送",
    },
    WaitingAction.WITHDRAW.value: {
        "fr": "Retirer",
        "en": "Withdraw",
        "es": "Retirar",
        "de": "Zurückziehen",
        "it": "Ritira",
        "zh-CN": "撤回",
    },
}


class WaitingPress(NamedTuple):
    """What a waiting-message button carries back.

    Attributes:
        action: Send it now, or withdraw it.
        waiting_id: The waiting message the button was drawn for.
    """

    action: WaitingAction
    waiting_id: UUID


def build_waiting_keyboard(waiting_id: UUID, language: str | None = None) -> dict:
    """The inline keyboard of a held message: Send, Withdraw.

    Args:
        waiting_id: The waiting message both buttons act on.
        language: The reader's language (default: the declared language).

    Returns:
        An InlineKeyboardMarkup dict.
    """
    language = resolve_language(language)
    return {
        "inline_keyboard": [
            [
                {
                    "text": WAITING_BUTTON_LABELS[action.value][language],
                    "callback_data": f"{WAITING_CALLBACK_PREFIX}:{action.value}:{waiting_id}",
                }
                for action in WaitingAction
            ]
        ]
    }


def parse_waiting_callback_data(callback_data: str | None) -> WaitingPress | None:
    """Read a waiting-message button press, or None when it is not one.

    Args:
        callback_data: What the client sent back — anything at all.

    Returns:
        The press, or None for any other data (an action no keyboard draws, an
        id that is no UUID).
    """
    parts = (callback_data or "").split(":")
    if len(parts) != 3 or parts[0] != WAITING_CALLBACK_PREFIX:
        return None
    try:
        return WaitingPress(WaitingAction(parts[1]), UUID(parts[2]))
    except ValueError:
        return None
