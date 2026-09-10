"""What a ticket notification puts in front of the reader, on both sides.

`notification_metadata` composes a bounded payload and the chat renders three
actions from it (`WorkboardNotificationActions`). The two halves are written in
different languages, so the KEYS are the contract — and a rename on either side
is silent: the row simply stops offering the action, and « finish this in the
chat » is the one action a stopped run exists to offer.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.domains.workboard.notifications import WorkboardEvent, notification_metadata
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit


def _ticket() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), title="Réserver la salle")


def _frontend_keys() -> set[str]:
    """The metadata fields the chat row actually reads."""
    root = repo_root_or_skip()
    path = (
        Path(root)
        / "apps"
        / "web"
        / "src"
        / "components"
        / "chat"
        / "WorkboardNotificationActions.tsx"
    )
    if not path.exists():  # pragma: no cover - the frontend tree is absent
        pytest.skip("apps/web is not checked out beside apps/api")
    source = path.read_text(encoding="utf-8")
    return set(re.findall(r"str\(metadata, '([a-z_]+)'\)", source))


class TestTheChatReadsWhatTheNotificationWrites:
    def test_every_field_the_row_reads_is_one_the_payload_writes(self) -> None:
        waiting = notification_metadata(
            WorkboardEvent.WAITING,
            _ticket(),
            board_url="https://lia.example/dashboard/workboard",
            ticket_url="https://lia.example/dashboard/workboard/1",
            intent_url="https://lia.example/dashboard/chat?intent=x",
        )
        unknown = _frontend_keys() - set(waiting)
        assert (
            not unknown
        ), f"the chat reads metadata fields the notification never writes: {sorted(unknown)}"

    def test_the_row_reads_the_three_it_needs(self) -> None:
        assert {"board_url", "ticket_url", "intent"} <= _frontend_keys()

    def test_the_intent_is_written_for_a_stopped_run_and_for_nothing_else(self) -> None:
        """Offering « finish in the chat » on a finished run would invite a turn
        with nothing to do."""
        finished = notification_metadata(
            WorkboardEvent.RUN_FINISHED, _ticket(), board_url="b", ticket_url="t"
        )
        assert "intent" not in finished

    def test_the_type_the_row_gates_on_is_the_one_the_dispatcher_stamps(self) -> None:
        # `NotificationDispatcher` stamps `type = f"proactive_{task_type}"`, and
        # the row renders nothing unless it matches exactly.
        from src.domains.workboard.constants import NOTIFICATION_TASK_TYPE

        root = repo_root_or_skip()
        source = (
            Path(root)
            / "apps"
            / "web"
            / "src"
            / "components"
            / "chat"
            / "WorkboardNotificationActions.tsx"
        ).read_text(encoding="utf-8")
        assert f"'proactive_{NOTIFICATION_TASK_TYPE}'" in source
