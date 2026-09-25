"""A shared image reaches the recipient's chat as a card, never as markup (ADR-316).

The route commits the share first and reaches the chat after, best-effort: the
image is in the recipient's gallery whatever the notification does. The bubble
is a peer's (the chat's reply and block actions read its type and sender), the
card is the very shape of an image LIA generated for them, and the sender's
comment is quoted literally in the recipient's language line.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.peers import image_share
from src.domains.peers.constants import PEER_IMAGE_TASK_TYPE, PROACTIVE_PEER_IMAGE_TYPE
from src.domains.peers.image_share import SharedImage, deliver_shared_image, shared_image_body
from src.domains.peers.router import share_image_with_connection
from src.domains.peers.schemas import ImageShareCreate

pytestmark = pytest.mark.unit

EXPIRES = datetime(2026, 9, 25, 16, 0, tzinfo=UTC)


def _shared(comment: str | None = None) -> SharedImage:
    return SharedImage(
        share_id=uuid4(),
        sender_id=uuid4(),
        sender_display_name="Gérard Dupont",
        recipient_id=uuid4(),
        recipient_display_name="Claire Lefèvre",
        attachment_id=uuid4(),
        url="/api/v1/attachments/abc",
        title="a lighthouse at dusk",
        expires_at=EXPIRES,
        comment=comment,
    )


class TestTheBody:
    def test_the_line_is_in_the_recipients_language(self) -> None:
        assert shared_image_body(_shared(), "fr") == "Gérard Dupont t'a partagé une image."
        assert shared_image_body(_shared(), "zh") == "Gérard Dupont 与你分享了一张图片。"

    def test_the_comment_is_quoted_literally(self) -> None:
        body = shared_image_body(_shared("Regarde ![x](https://t.example/p.png)"), "en")

        assert body == (
            "Gérard Dupont shared an image with you.\n\n"
            "> Regarde !&#91;x&#93;(https://t.example/p.png)"
        )


class TestTheDelivery:
    async def _deliver(self, shared: SharedImage, *, dispatch: AsyncMock) -> tuple[bool, AsyncMock]:
        recipient = SimpleNamespace(id=shared.recipient_id, language="de")
        db = MagicMock()
        db.get = AsyncMock(return_value=recipient)

        class _Session:
            async def __aenter__(self) -> MagicMock:
                return db

            async def __aexit__(self, *_exc: object) -> None:
                return None

        dispatcher = MagicMock()
        dispatcher.dispatch = dispatch
        with (
            patch("src.infrastructure.database.get_db_context", return_value=_Session()),
            patch(
                "src.infrastructure.proactive.notification.NotificationDispatcher",
                return_value=dispatcher,
            ),
        ):
            delivered = await deliver_shared_image(shared)
        return delivered, dispatch

    async def test_the_card_is_the_generated_image_card(self) -> None:
        shared = _shared("Pour toi")
        delivered, dispatch = await self._deliver(
            shared, dispatch=AsyncMock(return_value=SimpleNamespace(success=True))
        )

        assert delivered is True
        kwargs = dispatch.await_args.kwargs
        assert kwargs["task_type"] == PEER_IMAGE_TASK_TYPE
        assert kwargs["target_id"] == str(shared.share_id)
        assert kwargs["content"] == "Gérard Dupont hat ein Bild mit dir geteilt.\n\n> Pour toi"
        assert kwargs["title"] == "Bild von einem Kontakt"
        assert kwargs["metadata"] == {
            "sender_id": str(shared.sender_id),
            "sender_name": "Gérard Dupont",
            "generated_images": [
                {
                    "url": "/api/v1/attachments/abc",
                    "alt": "a lighthouse at dusk",
                    "expires_at": EXPIRES.isoformat(),
                }
            ],
        }

    async def test_a_dispatch_failure_is_reported_never_raised(self) -> None:
        delivered, _dispatch = await self._deliver(
            _shared(), dispatch=AsyncMock(side_effect=RuntimeError("redis down"))
        )

        assert delivered is False

    def test_the_bubble_type_is_the_one_the_chat_reads(self) -> None:
        assert PROACTIVE_PEER_IMAGE_TYPE == "proactive_peer_image"


class TestTheRoute:
    async def test_it_shares_then_delivers_and_says_so(self) -> None:
        shared = _shared()
        user = SimpleNamespace(id=shared.sender_id)
        db = MagicMock()
        payload = ImageShareCreate(attachment_id=uuid4(), comment="hi")
        with (
            patch.object(image_share, "share_image", AsyncMock(return_value=shared)) as share,
            patch("src.domains.peers.router.share_image", share),
            patch("src.domains.peers.router.deliver_shared_image", AsyncMock(return_value=False)),
        ):
            view = await share_image_with_connection(
                connection_id=uuid4(), payload=payload, user=user, db=db
            )

        assert share.await_args.kwargs["attachment_id"] == payload.attachment_id
        assert share.await_args.kwargs["comment"] == "hi"
        assert (view.id, view.recipient_display_name, view.delivered) == (
            shared.share_id,
            "Claire Lefèvre",
            False,
        )

    def test_the_comment_bound_is_published_by_the_schema(self) -> None:
        from pydantic import ValidationError

        from src.core.constants import PEERS_IMAGE_SHARE_COMMENT_MAX_CHARS

        with pytest.raises(ValidationError):
            ImageShareCreate(
                attachment_id=uuid4(), comment="x" * (PEERS_IMAGE_SHARE_COMMENT_MAX_CHARS + 1)
            )


def test_the_web_dialog_publishes_the_bound_the_api_enforces() -> None:
    """ADR-184: the share dialog's `maxLength` is the schema's `max_length`."""
    import re

    from src.core.constants import PEERS_IMAGE_SHARE_COMMENT_MAX_CHARS
    from tests._repo_paths import repo_root_or_skip

    source = (
        repo_root_or_skip() / "apps" / "web" / "src" / "lib" / "peers" / "image-share.ts"
    ).read_text(encoding="utf-8")
    match = re.search(r"IMAGE_SHARE_COMMENT_MAX_CHARS = (\d+);", source)

    assert match is not None
    assert int(match.group(1)) == PEERS_IMAGE_SHARE_COMMENT_MAX_CHARS
