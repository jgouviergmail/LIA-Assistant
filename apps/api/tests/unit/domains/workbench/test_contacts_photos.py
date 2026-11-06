"""A contact's photo from the screen (ADR-369, lot 9).

Whatever a person picks is redrawn before it leaves: one small JPEG, its metadata gone with it,
so a phone's GPS never reaches a provider, a card stays a size iCloud takes, and a file that is no
image is refused here rather than by whoever receives it.
"""

from __future__ import annotations

import contextlib
import io
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from PIL import Image

from src.core.constants import WORKBENCH_CONTACT_PHOTO_MAX_SIDE
from src.core.exceptions import BaseAPIException
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.contact_photos import ContactPhoto
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import contacts_photos
from src.domains.workbench.errors import ITEM_GONE, NOT_AN_IMAGE, refusal_code_of

pytestmark = pytest.mark.unit

USER = uuid4()
GOOGLE = ConnectorType.GOOGLE_CONTACTS


def _door(client: Any) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(client=client, connector_type=GOOGLE, preferred_name=None)

    return patch.object(contacts_photos, "open_tool_client", opened)


def _image(
    size: tuple[int, int] = (32, 32), kind: str = "PNG", mode: str = "RGB", **save: Any
) -> bytes:
    out = io.BytesIO()
    Image.new(mode, size, (20, 120, 200) if mode == "RGB" else (20, 120, 200, 0)).save(
        out, kind, **save
    )
    return out.getvalue()


class TestWhatLeaves:
    def test_any_image_leaves_as_a_jpeg(self) -> None:
        photo = contacts_photos.prepared_photo(_image())

        assert photo.mime_type == "image/jpeg"
        assert Image.open(io.BytesIO(photo.data)).format == "JPEG"

    def test_a_large_one_is_brought_down_keeping_its_shape(self) -> None:
        side = WORKBENCH_CONTACT_PHOTO_MAX_SIDE
        photo = contacts_photos.prepared_photo(_image((side * 4, side * 2)))

        assert Image.open(io.BytesIO(photo.data)).size == (side, side // 2)

    def test_a_small_one_is_never_blown_up(self) -> None:
        photo = contacts_photos.prepared_photo(_image((32, 16)))

        assert Image.open(io.BytesIO(photo.data)).size == (32, 16)

    def test_what_a_phone_wrote_in_it_does_not_leave(self) -> None:
        exif = Image.Exif()
        exif[0x010F] = "A camera"
        source = _image(kind="JPEG", exif=exif)
        assert Image.open(io.BytesIO(source)).getexif()

        photo = contacts_photos.prepared_photo(source)

        assert not Image.open(io.BytesIO(photo.data)).getexif()

    def test_a_phone_s_turned_picture_stands_up(self) -> None:
        exif = Image.Exif()
        exif[0x0112] = 6  # Rotated 90 degrees: the file is wider than what the person saw.
        photo = contacts_photos.prepared_photo(_image((40, 20), kind="JPEG", exif=exif))

        assert Image.open(io.BytesIO(photo.data)).size == (20, 40)

    def test_a_transparent_one_stands_on_white(self) -> None:
        photo = contacts_photos.prepared_photo(_image(mode="RGBA"))

        red, green, blue = Image.open(io.BytesIO(photo.data)).convert("RGB").getpixel((5, 5))
        assert min(red, green, blue) > 240

    @pytest.mark.parametrize("data", [b"", b"hello", b"<svg></svg>", b"\xff\xd8\xff\xe0broken"])
    def test_what_is_no_image_is_refused(self, data: bytes) -> None:
        with pytest.raises(BaseAPIException) as refused:
            contacts_photos.prepared_photo(data)

        assert refusal_code_of(refused.value) == NOT_AN_IMAGE

    def test_what_pillow_itself_calls_a_bomb_is_refused(self) -> None:
        with (
            patch.object(Image, "MAX_IMAGE_PIXELS", 10),
            pytest.raises(BaseAPIException) as refused,
        ):
            contacts_photos.prepared_photo(_image((32, 32)))

        assert refusal_code_of(refused.value) == NOT_AN_IMAGE

    def test_a_decompression_bomb_is_refused_before_it_is_drawn(self) -> None:
        with (
            patch.object(contacts_photos, "_MAX_PIXELS", 10),
            pytest.raises(BaseAPIException) as refused,
        ):
            contacts_photos.prepared_photo(_image((32, 32)))

        assert refusal_code_of(refused.value) == NOT_AN_IMAGE


class TestTheActs:
    async def test_a_photo_is_read(self) -> None:
        photo = ContactPhoto(b"x", "image/jpeg")
        client = MagicMock(get_contact_photo=AsyncMock(return_value=photo))

        with _door(client):
            assert await contacts_photos.read_photo(USER, "people/c1") == photo

    async def test_no_photo_is_said_gone(self) -> None:
        client = MagicMock(get_contact_photo=AsyncMock(return_value=None))

        with _door(client), pytest.raises(BaseAPIException) as refused:
            await contacts_photos.read_photo(USER, "people/c1")

        assert refusal_code_of(refused.value) == ITEM_GONE

    async def test_a_contact_met_in_mail_has_none_to_read(self) -> None:
        client = MagicMock(get_contact_photo=AsyncMock())

        with _door(client), pytest.raises(BaseAPIException):
            await contacts_photos.read_photo(USER, "otherContacts/c9")

        client.get_contact_photo.assert_not_awaited()

    async def test_what_is_written_is_what_was_redrawn(self) -> None:
        client = MagicMock(set_contact_photo=AsyncMock())

        with _door(client):
            await contacts_photos.write_photo(USER, "people/c1", _image())

        name, photo = client.set_contact_photo.await_args.args
        assert name == "people/c1"
        assert photo.mime_type == "image/jpeg"

    async def test_a_file_that_is_no_image_reaches_no_provider(self) -> None:
        client = MagicMock(set_contact_photo=AsyncMock())

        with _door(client), pytest.raises(BaseAPIException):
            await contacts_photos.write_photo(USER, "people/c1", b"hello")

        client.set_contact_photo.assert_not_awaited()

    async def test_it_is_taken_off(self) -> None:
        client = MagicMock(remove_contact_photo=AsyncMock())

        with _door(client):
            await contacts_photos.remove_photo(USER, "people/c1")

        client.remove_contact_photo.assert_awaited_once_with("people/c1")
