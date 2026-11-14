"""The turn's last browser screenshot is a durable file before its card names it."""

import threading
from pathlib import Path
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.conversation_execution import ExecutionRevoked
from src.domains.agents.api import browser_screenshot_card
from src.domains.agents.api.browser_screenshot_card import publish_browser_screenshot_card
from src.domains.agents.tools.browser_screenshot_store import store_last_browser_screenshot
from src.domains.attachments.models import AttachmentOrigin, AttachmentStatus
from src.domains.attachments.urls import attachment_url
from tests.helpers.attachment_publication import publication_session, stub_publication
from tests.helpers.run_authority import unit_run_authority

pytestmark = pytest.mark.unit

JPEG = b"\xff\xd8\xff\xe0" + b"s" * 64


@pytest.fixture(autouse=True)
def _capture_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "browser_progressive_screenshots", True)
    monkeypatch.setattr(browser_screenshot_card, "get_db_context", publication_session)


async def test_the_last_screenshot_is_published_off_the_loop_for_its_discussion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, conversation, runtime = uuid4(), uuid4(), uuid4()
    loop_thread = threading.get_ident()
    writers: list[int] = []
    original = Path.write_bytes

    def observed(path: Path, data: bytes) -> int:
        writers.append(threading.get_ident())
        return original(path, data)

    monkeypatch.setattr(Path, "write_bytes", observed)
    created: list[dict[str, object]] = []
    with unit_run_authority(owner, conversation, runtime), stub_publication(tmp_path, created):
        store_last_browser_screenshot(str(runtime), JPEG)
        card = await publish_browser_screenshot_card(
            user_id=owner, conversation_id=conversation, runtime_id=str(runtime), run_id="run"
        )

    [row] = created
    assert card == {"url": attachment_url(str(row["id"])), "alt": "Browser screenshot"}
    assert (row["user_id"], row["origin"], row["conversation_id"], row["status"]) == (
        owner,
        AttachmentOrigin.BROWSER_SCREENSHOT.value,
        conversation,
        AttachmentStatus.READY,
    )
    assert (tmp_path / str(row["file_path"])).read_bytes() == JPEG
    assert len(writers) == 1 and writers[0] != loop_thread


async def test_a_revoked_turn_publishes_no_screenshot_and_is_not_swallowed(
    tmp_path: Path,
) -> None:
    owner, conversation, runtime = uuid4(), uuid4(), uuid4()
    created: list[dict[str, object]] = []
    with (
        unit_run_authority(owner, conversation, runtime) as authority,
        stub_publication(tmp_path, created),
    ):
        store_last_browser_screenshot(str(runtime), JPEG)
        authority.revoked = True
        with pytest.raises(ExecutionRevoked):
            await publish_browser_screenshot_card(
                user_id=owner, conversation_id=conversation, runtime_id=str(runtime), run_id="run"
            )

    assert created == [] and not list(tmp_path.rglob("*.jpg"))


async def test_a_failed_save_costs_the_card_never_the_answer(tmp_path: Path) -> None:
    owner, conversation, runtime = uuid4(), uuid4(), uuid4()
    with (
        unit_run_authority(owner, conversation, runtime),
        stub_publication(tmp_path, fail_stage=True),
    ):
        store_last_browser_screenshot(str(runtime), JPEG)
        card = await publish_browser_screenshot_card(
            user_id=owner, conversation_id=conversation, runtime_id=str(runtime), run_id="run"
        )

    assert card is None
