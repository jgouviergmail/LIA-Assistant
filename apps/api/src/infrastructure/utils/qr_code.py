"""Draw a QR code as a PNG data URI — one door for every screen that shows one.

A TOTP enrolment shows its provisioning URI, an ntfy subscription the link that subscribes the
app (ADR-391). Drawing is CPU-bound: an async caller runs it off the event loop
(``asyncio.to_thread``).
"""

from __future__ import annotations

import base64
import io

import qrcode


def render_qr_data_uri(text: str) -> str:
    """The QR code of a text, as a PNG data URI.

    Args:
        text: What the code carries (a URI).

    Returns:
        ``data:image/png;base64,...``
    """
    image = qrcode.make(text)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


__all__ = ["render_qr_data_uri"]
