"""The wire path of a stored file, and back (ADR-318, Telegram lot 11)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.domains.attachments.urls import attachment_id_from_url, attachment_url

pytestmark = pytest.mark.unit


def test_a_stored_file_s_path_names_it_back() -> None:
    attachment_id = uuid4()

    assert attachment_id_from_url(attachment_url(attachment_id)) == attachment_id


@pytest.mark.parametrize(
    "url",
    [
        "https://maps.example/photo.jpg",
        f"/api/v1/attachments/{uuid4()}/preview",
        "/api/v1/attachments/not-an-id",
        "/api/v1/attachments/",
        f"/api/v2/attachments/{uuid4()}",
    ],
    ids=["provider", "sub_route", "not_an_id", "empty", "other_version"],
)
def test_any_other_url_names_no_stored_file(url: str) -> None:
    assert attachment_id_from_url(url) is None
