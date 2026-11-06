"""A contact's photo from the screen (ADR-369, lot 9).

Whatever a person picks is redrawn before it leaves: one small JPEG. Its metadata stays behind, so
a phone's GPS never reaches a provider; a card stays a size iCloud takes; and a file that is no
image is refused here rather than by whoever receives it. The picture a phone turned stands up.
The drawing runs off the event loop.
"""

from __future__ import annotations

import asyncio
import io
from typing import Final
from uuid import UUID

from src.core.constants import WORKBENCH_CONTACT_PHOTO_MAX_SIDE
from src.domains.connectors.clients.contact_photos import ContactPhoto
from src.domains.connectors.clients.protocols import ContactsClientProtocol
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.contacts_service import refuse_other_contact
from src.domains.workbench.errors import ITEM_GONE, NOT_AN_IMAGE, refuse
from src.domains.workbench.features import WorkbenchTool

_TOOL = WorkbenchTool.CONTACTS
#: What is opened at all: a small file can claim to be a vast image.
_MAX_PIXELS: Final = 50_000_000
_JPEG_QUALITY: Final = 85
_WHITE: Final = (255, 255, 255)


def prepared_photo(data: bytes) -> ContactPhoto:
    """Any image as the one small JPEG that leaves.

    Args:
        data: What the person picked; anybody's.

    Returns:
        The photo, its longest side bounded, its metadata gone.

    Raises:
        BaseAPIException: ``not_an_image`` for what cannot be drawn.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.width * source.height > _MAX_PIXELS:
                refuse(NOT_AN_IMAGE)
            upright = ImageOps.exif_transpose(source)
            upright.load()
    except UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError, SyntaxError:
        refuse(NOT_AN_IMAGE)
    upright.thumbnail((WORKBENCH_CONTACT_PHOTO_MAX_SIDE, WORKBENCH_CONTACT_PHOTO_MAX_SIDE))
    drawn = Image.new("RGB", upright.size, _WHITE)
    held = upright.convert("RGBA")
    drawn.paste(held, mask=held.getchannel("A"))
    out = io.BytesIO()
    drawn.save(out, "JPEG", quality=_JPEG_QUALITY)
    return ContactPhoto(out.getvalue(), "image/jpeg")


async def read_photo(user_id: UUID, contact_id: str) -> ContactPhoto:
    """A contact's photo; a contact holding none is said gone."""
    refuse_other_contact(contact_id)
    async with open_tool_client(_TOOL, user_id) as opened:
        client: ContactsClientProtocol = opened.client
        async with provider_call(_TOOL, "read_photo", act=False):
            photo = await client.get_contact_photo(contact_id)
    if photo is None:
        refuse(ITEM_GONE)
    return photo


async def write_photo(user_id: UUID, contact_id: str, data: bytes) -> None:
    """Replace a contact's photo with what the person picked, redrawn."""
    refuse_other_contact(contact_id)
    photo = await asyncio.to_thread(prepared_photo, data)
    async with open_tool_client(_TOOL, user_id) as opened:
        client: ContactsClientProtocol = opened.client
        async with provider_call(_TOOL, "write_photo", act=True):
            await client.set_contact_photo(contact_id, photo)


async def remove_photo(user_id: UUID, contact_id: str) -> None:
    """Take a contact's photo off."""
    refuse_other_contact(contact_id)
    async with open_tool_client(_TOOL, user_id) as opened:
        client: ContactsClientProtocol = opened.client
        async with provider_call(_TOOL, "remove_photo", act=True):
            await client.remove_contact_photo(contact_id)


__all__ = ["prepared_photo", "read_photo", "remove_photo", "write_photo"]
