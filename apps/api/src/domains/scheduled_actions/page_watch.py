"""A page a person watches, as the routine's contract states it (ADR-387).

Pure — no database, no network. The domain owns what a page watch may KEEP:
an address whose own spelling does not rule out a public page, refused at the
API boundary where no network call may run (``literal_refusal``: the scheme,
the host, a blocked name, a blocked literal address), and never an address
carrying credentials — a watch is a public reader, and a password in a stored
URL would travel in every request. Where the name resolves is judged by the
read itself, at every hop (``infrastructure/scheduler/page_reading.py``).
"""

from __future__ import annotations

from urllib.parse import urlsplit

from src.infrastructure.utils.url_validation import literal_refusal


def page_url_refusal(url: str) -> str | None:
    """Why a page watch may not keep this address, or ``None``.

    Args:
        url: The address as the person or the assistant gave it.

    Returns:
        The refusal, worded for the API caller; ``None`` when only reading the
        page can tell more.
    """
    refusal = literal_refusal(url)
    if refusal is not None:
        return refusal
    if "@" in urlsplit(url.strip()).netloc:
        return "an address carrying credentials is not kept"
    return None


__all__ = ["page_url_refusal"]
