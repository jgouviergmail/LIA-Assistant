"""The images a message carries inside itself (ADR-369, lot 3).

What the HTML names ``cid:`` is the message's own part: nothing leaves for a sender
to count, so it needs no click. Only an image of a known type is drawn, never an
SVG; each and all are bounded, and what was left out is counted, never silent.
"""

from __future__ import annotations

import pytest

from src.domains.connectors.clients.mail_inline_images import (
    InlineBudget,
    InlineImage,
    content_id_of,
    usable_image_type,
)

pytestmark = pytest.mark.unit


class TestContentId:
    @pytest.mark.parametrize(
        ("header", "expected"),
        [("<logo@x>", "logo@x"), ("logo@x", "logo@x"), (" <logo@x> ", "logo@x"), ("", None)],
    )
    def test_the_angle_brackets_are_not_the_id(self, header: str, expected: str | None) -> None:
        assert content_id_of(header) == expected

    def test_no_header_is_no_id(self) -> None:
        assert content_id_of(None) is None


class TestUsableImageType:
    @pytest.mark.parametrize("mime", ["image/png", "image/jpeg", "image/gif", "image/webp"])
    def test_what_a_frame_draws(self, mime: str) -> None:
        assert usable_image_type(mime) == mime

    def test_a_type_is_read_without_its_parameters_or_case(self) -> None:
        assert usable_image_type('IMAGE/PNG; name="a.png"') == "image/png"
        assert usable_image_type("image/jpg") == "image/jpeg"

    @pytest.mark.parametrize(
        "mime", ["image/svg+xml", "text/html", "application/pdf", "image/", ""]
    )
    def test_nothing_else_is_drawn(self, mime: str) -> None:
        assert usable_image_type(mime) is None


class TestInlineBudget:
    def test_keeps_what_fits_as_a_data_address(self) -> None:
        budget = InlineBudget(each_max=10, total_max=100, count_max=5)

        assert budget.admit("logo", "image/png", b"abc") is True

        assert budget.images == [
            InlineImage(cid="logo", data_url="data:image/png;base64,YWJj"),
        ]
        assert budget.skipped == 0

    def test_counts_what_passes_its_own_bound(self) -> None:
        budget = InlineBudget(each_max=2, total_max=100, count_max=5)

        assert budget.admit("logo", "image/png", b"abc") is False

        assert budget.images == []
        assert budget.skipped == 1

    def test_counts_what_passes_the_whole_bound(self) -> None:
        budget = InlineBudget(each_max=10, total_max=5, count_max=5)

        budget.admit("a", "image/png", b"abc")
        budget.admit("b", "image/png", b"abc")

        assert [image.cid for image in budget.images] == ["a"]
        assert budget.skipped == 1

    def test_counts_what_passes_the_number_of_images(self) -> None:
        budget = InlineBudget(each_max=10, total_max=100, count_max=1)

        budget.admit("a", "image/png", b"a")
        budget.admit("b", "image/png", b"b")

        assert budget.skipped == 1

    def test_a_listed_size_is_refused_before_it_is_read(self) -> None:
        budget = InlineBudget(each_max=2, total_max=100, count_max=5)

        assert budget.worth_reading(3) is False
        assert budget.skipped == 1
        assert budget.worth_reading(None) is True

    def test_nothing_is_read_once_the_room_is_gone(self) -> None:
        budget = InlineBudget(each_max=10, total_max=100, count_max=1)
        budget.admit("a", "image/png", b"a")

        assert budget.worth_reading(1) is False
        assert budget.skipped == 1

    def test_a_refused_type_is_counted(self) -> None:
        budget = InlineBudget(each_max=10, total_max=100, count_max=5)

        assert budget.admit("a", "image/svg+xml", b"<svg/>") is False

        assert budget.skipped == 1
