"""The buttons of a message that did not leave carry the message they act on (lot 34)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.infrastructure.channels.assistant_gateway import WaitingAction
from src.infrastructure.channels.telegram.hitl_keyboard import TELEGRAM_CALLBACK_DATA_MAX_BYTES
from src.infrastructure.channels.telegram.waiting_keyboard import (
    WaitingPress,
    build_waiting_keyboard,
    parse_waiting_callback_data,
)

pytestmark = pytest.mark.unit


def test_each_button_reads_back_as_its_action_on_its_message() -> None:
    waiting_id = uuid4()

    [row] = build_waiting_keyboard(waiting_id, "fr")["inline_keyboard"]

    assert [button["text"] for button in row] == ["Envoyer", "Retirer"]
    presses = [parse_waiting_callback_data(button["callback_data"]) for button in row]
    assert presses == [
        WaitingPress(WaitingAction.SEND, waiting_id),
        WaitingPress(WaitingAction.WITHDRAW, waiting_id),
    ]
    assert all(
        len(button["callback_data"].encode()) <= TELEGRAM_CALLBACK_DATA_MAX_BYTES for button in row
    )


def test_the_buttons_speak_the_reader_s_language() -> None:
    [row] = build_waiting_keyboard(uuid4(), "zh-CN")["inline_keyboard"]
    assert [button["text"] for button in row] == ["发送", "撤回"]


#: A fixed id: parameters drawn at collection differ between xdist workers,
#: which then refuse to run (« Different tests were collected »).
_SOME_ID = "4f1c2b9e-8d7a-4c3b-9e2f-1a2b3c4d5e6f"


@pytest.mark.parametrize(
    "data",
    [
        None,
        "",
        "hitl:confirm:c:0a1b2c3d",
        "wait:send",
        f"wait:delete:{_SOME_ID}",
        "wait:send:not-a-uuid",
        f"wait:send:{_SOME_ID}:extra",
    ],
)
def test_anything_else_is_no_press(data: str | None) -> None:
    assert parse_waiting_callback_data(data) is None
