"""One door draws a QR code as a data URI (TOTP enrolment, ntfy subscription, ADR-391)."""

from __future__ import annotations

import base64

import pytest

from src.infrastructure.utils.qr_code import render_qr_data_uri

pytestmark = pytest.mark.unit

PREFIX = "data:image/png;base64,"


def _png(uri: str) -> bytes:
    assert uri.startswith(PREFIX)
    return base64.b64decode(uri.removeprefix(PREFIX), validate=True)


def test_a_text_is_drawn_as_a_png_data_uri() -> None:
    assert _png(render_qr_data_uri("ntfy://ntfy.sh/lia_t?display=LIA")).startswith(
        b"\x89PNG\r\n\x1a\n"
    )


def test_the_same_text_draws_the_same_code_and_another_text_another() -> None:
    first = render_qr_data_uri("otpauth://totp/LIA:a?secret=ABC")

    assert render_qr_data_uri("otpauth://totp/LIA:a?secret=ABC") == first
    assert render_qr_data_uri("otpauth://totp/LIA:b?secret=ABC") != first
