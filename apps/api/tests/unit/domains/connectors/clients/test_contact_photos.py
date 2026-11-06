"""A contact's photo on the three providers (ADR-369, lot 9).

One contract: a read answers the bytes and their type, or None for no photo; a write replaces it;
a removal takes it off, and one with nothing to remove is done. Measured on Graph: ``$value``
reads and writes, ``/photo`` deletes (``$value`` answers 405), a read with no photo answers 404.
What a card or a provider calls a photo is believed only when its first bytes agree, so a card's
script never leaves as an image.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
import vobject

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients import contact_photos
from src.domains.connectors.clients.apple_contacts_client import AppleContactsClient
from src.domains.connectors.clients.contact_photos import (
    ContactPhoto,
    card_photo,
    card_with_photo,
    photo_type,
)
from src.domains.connectors.clients.google_people_client import GooglePeopleClient
from src.domains.connectors.clients.microsoft_contacts_client import MicrosoftContactsClient
from src.domains.connectors.clients.normalizers.contacts_normalizer import build_vcard
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

JPEG = b"\xff\xd8\xff\xe0" + b"jpeg"
PNG = b"\x89PNG\r\n\x1a\n" + b"png"
SVG = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"
PHOTO = ContactPhoto(JPEG, "image/jpeg")


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


class TestWhatAPhotoIs:
    @pytest.mark.parametrize(
        ("data", "kind"), [(JPEG, "image/jpeg"), (PNG, "image/png"), (SVG, None), (b"", None)]
    )
    def test_its_first_bytes_say(self, data: bytes, kind: str | None) -> None:
        assert photo_type(data) == kind


class TestGoogle:
    def _client(self, *answers: Any) -> tuple[GooglePeopleClient, AsyncMock]:
        client = GooglePeopleClient(uuid4(), _credentials(), MagicMock())
        request = AsyncMock(side_effect=list(answers))
        client._make_request = request
        client._get_cache = AsyncMock(
            return_value=MagicMock(invalidate_user=AsyncMock(), set_details=AsyncMock())
        )
        return client, request

    async def test_a_photo_is_read_from_the_address_google_gave(self) -> None:
        url = "https://lh3.googleusercontent.com/contacts/abc=s100"
        client, _ = self._client({"photos": [{"url": url}]})
        fetched = AsyncMock(return_value=PHOTO)

        with patch.object(contact_photos, "fetch_photo", fetched):
            assert await client.get_contact_photo("people/c1") == PHOTO

        fetched.assert_awaited_once_with(url)

    async def test_the_silhouette_google_draws_is_no_photo(self) -> None:
        url = "https://lh3.googleusercontent.com/default"
        client, _ = self._client({"photos": [{"url": url, "default": True}]})
        fetched = AsyncMock()

        with patch.object(contact_photos, "fetch_photo", fetched):
            assert await client.get_contact_photo("people/c1") is None

        fetched.assert_not_awaited()

    async def test_a_new_photo_goes_as_its_bytes(self) -> None:
        client, request = self._client({})

        await client.set_contact_photo("people/c1", PHOTO)

        assert request.await_args.args == ("PATCH", "/people/c1:updateContactPhoto")
        written = request.await_args.kwargs["json_data"]["photoBytes"]
        assert base64.b64decode(written) == JPEG

    async def test_it_is_taken_off(self) -> None:
        client, request = self._client({})

        await client.remove_contact_photo("people/c1")

        assert request.await_args.args == ("DELETE", "/people/c1:deleteContactPhoto")

    @pytest.mark.parametrize("name", ["otherContacts/c9", "people/c1:batch", "../people/c1"])
    async def test_a_name_of_another_shape_reaches_no_one(self, name: str) -> None:
        client, request = self._client({})

        with pytest.raises(ConnectorAPIError):
            await client.set_contact_photo(name, PHOTO)

        request.assert_not_awaited()


class TestFetchingWhatGoogleNames:
    @pytest.mark.parametrize(
        "url",
        [
            "http://lh3.googleusercontent.com/a",
            "https://lh3.googleusercontent.com.evil.example/a",
            "https://evil.example/a",
            "https://user@lh3.googleusercontent.com/a",
            "https://169.254.169.254/latest",
        ],
    )
    async def test_an_address_of_no_known_host_is_never_asked(self, url: str) -> None:
        validated = AsyncMock()

        with patch.object(contact_photos, "validate_url", validated):
            assert await contact_photos.fetch_photo(url) is None

        validated.assert_not_awaited()

    async def test_an_answer_that_is_no_image_is_no_photo(self) -> None:
        with _answering(SVG):
            assert await contact_photos.fetch_photo(_GOOGLE_URL) is None

    async def test_an_image_is_read_under_its_ceiling(self) -> None:
        with _answering(JPEG):
            assert await contact_photos.fetch_photo(_GOOGLE_URL) == PHOTO

    async def test_a_failed_answer_is_no_photo(self) -> None:
        with _answering(JPEG, status=500):
            assert await contact_photos.fetch_photo(_GOOGLE_URL) is None

    async def test_a_redirect_is_not_followed(self) -> None:
        with _answering(b"", status=302):
            assert await contact_photos.fetch_photo(_GOOGLE_URL) is None


_GOOGLE_URL = "https://lh3.googleusercontent.com/a"


def _answering(body: bytes, *, status: int = 200) -> Any:
    """``pinned_stream`` answering once, the bytes read through the bounded reader."""

    class _Stream:
        async def __aenter__(self) -> httpx.Response:
            return httpx.Response(status, content=body)

        async def __aexit__(self, *_: Any) -> None:
            return None

    verdict = MagicMock(valid=True)
    stack = patch.multiple(
        contact_photos,
        validate_url=AsyncMock(return_value=verdict),
        pinned_stream=MagicMock(return_value=_Stream()),
        read_bounded=AsyncMock(return_value=body),
    )
    return stack


class TestGraph:
    def _client(self, answer: Any) -> tuple[MicrosoftContactsClient, AsyncMock]:
        client = MicrosoftContactsClient(uuid4(), _credentials(), MagicMock())
        request = AsyncMock(side_effect=answer if isinstance(answer, Exception) else [answer])
        client._make_request = request
        return client, request

    async def test_a_photo_is_read_with_its_answer_kept_as_bytes(self) -> None:
        client, request = self._client({"data": JPEG})

        assert await client.get_contact_photo("people/c1") == PHOTO

        assert request.await_args.args == ("GET", "/me/contacts/c1/photo/$value")

    async def test_no_photo_is_answered_404(self) -> None:
        missing = ConnectorAPIError(
            connector_type="microsoft_contacts", status_code=404, detail="x"
        )
        client, _ = self._client(missing)

        assert await client.get_contact_photo("people/c1") is None

    async def test_any_other_failure_stays_one(self) -> None:
        down = ConnectorAPIError(connector_type="microsoft_contacts", status_code=503, detail="x")
        client, _ = self._client(down)

        with pytest.raises(ConnectorAPIError):
            await client.get_contact_photo("people/c1")

    async def test_what_is_no_image_is_no_photo(self) -> None:
        client, _ = self._client({"data": SVG})

        assert await client.get_contact_photo("people/c1") is None

    async def test_a_new_photo_goes_to_value_with_its_type(self) -> None:
        client, request = self._client({})

        await client.set_contact_photo("people/c1", PHOTO)

        assert request.await_args.args == ("PUT", "/me/contacts/c1/photo/$value")
        assert request.await_args.kwargs["content"] == JPEG
        assert request.await_args.kwargs["extra_headers"] == {"Content-Type": "image/jpeg"}

    async def test_it_is_taken_off_at_photo_not_at_value(self) -> None:
        client, request = self._client({})

        await client.remove_contact_photo("people/c1")

        assert request.await_args.args == ("DELETE", "/me/contacts/c1/photo")

    async def test_taking_off_what_is_not_there_is_done(self) -> None:
        missing = ConnectorAPIError(
            connector_type="microsoft_contacts", status_code=404, detail="x"
        )
        client, _ = self._client(missing)

        await client.remove_contact_photo("people/c1")


class TestACard:
    def test_a_photo_reads_from_a_card(self) -> None:
        card = card_with_photo(build_vcard("Ana Lima"), PHOTO)

        assert card_photo(card) == PHOTO

    def test_a_written_photo_keeps_every_other_line(self) -> None:
        kept = build_vcard("Ana Lima", email="ana@example.org", organization="Acme")

        card = vobject.readOne(card_with_photo(kept, PHOTO))

        assert card.email.value == "ana@example.org"
        assert card.org.value == ["Acme"]

    def test_a_new_photo_replaces_the_old(self) -> None:
        card = card_with_photo(build_vcard("Ana Lima"), ContactPhoto(PNG, "image/png"))

        replaced = card_with_photo(card, PHOTO)

        assert card_photo(replaced) == PHOTO
        assert len(vobject.readOne(replaced).contents["photo"]) == 1

    def test_it_is_taken_off(self) -> None:
        card = card_with_photo(build_vcard("Ana Lima"), PHOTO)

        assert card_photo(card_with_photo(card, None)) is None

    def test_a_card_pointing_elsewhere_is_never_followed(self) -> None:
        assert card_photo(_card("PHOTO;VALUE=uri:https://evil.example/a.jpg")) is None

    def test_a_card_calling_a_script_a_photo_shows_nothing(self) -> None:
        encoded = base64.b64encode(SVG).decode()

        assert card_photo(_card(f"PHOTO;ENCODING=b;TYPE=JPEG:{encoded}")) is None

    def test_a_card_with_none_has_none(self) -> None:
        assert card_photo(build_vcard("Ana Lima")) is None


class TestApple:
    def _client(self, card: str) -> tuple[AppleContactsClient, MagicMock]:
        http = MagicMock(
            get=AsyncMock(return_value=MagicMock(status_code=200, text=card)),
            put=AsyncMock(return_value=MagicMock(status_code=204)),
        )
        client = AppleContactsClient.__new__(AppleContactsClient)
        client.user_id = uuid4()
        client._get_http_client = AsyncMock(return_value=http)
        client._execute_with_retry = _straight
        client._invalidate_contacts_cache = AsyncMock()
        return client, http

    async def test_it_reads_from_the_card(self) -> None:
        client, _ = self._client(card_with_photo(build_vcard("Ana Lima"), PHOTO))

        assert await client.get_contact_photo("/addressbook/c1.vcf") == PHOTO

    async def test_a_new_photo_is_put_back_on_the_card_whole(self) -> None:
        client, http = self._client(build_vcard("Ana Lima", email="ana@example.org"))

        await client.set_contact_photo("/addressbook/c1.vcf", PHOTO)

        written = http.put.await_args.kwargs["content"]
        assert card_photo(written) == PHOTO
        assert "ana@example.org" in written
        client._invalidate_contacts_cache.assert_awaited_once()

    async def test_taking_it_off_keeps_the_card(self) -> None:
        client, http = self._client(card_with_photo(build_vcard("Ana Lima"), PHOTO))

        await client.remove_contact_photo("/addressbook/c1.vcf")

        written = http.put.await_args.kwargs["content"]
        assert card_photo(written) is None
        assert "Ana Lima" in written


async def _straight(_name: str, function: Any, *args: Any, **kwargs: Any) -> Any:
    return await function(*args, **kwargs)


def _card(*lines: str) -> str:
    separator = chr(13) + chr(10)
    return separator.join(
        ["BEGIN:VCARD", "VERSION:3.0", "FN:Ana", "N:;Ana;;;", *lines, "END:VCARD", ""]
    )
