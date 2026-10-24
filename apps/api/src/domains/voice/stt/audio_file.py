"""A meeting's audio opened for an upload: off the event loop, an unreadable file classified.

The three file engines stream the audio through
:func:`~src.infrastructure.multipart_upload.multipart_upload`, which reads it in a
worker thread (AC-035). Opening it is the same act for all three, so it is written
once: a file that cannot be opened is ``provider_http_error`` for every vendor, and
a read failing later is left to propagate as the ``OSError`` it is.
"""

from __future__ import annotations

from pathlib import Path

from src.domains.voice.stt.exceptions import STTProviderError
from src.infrastructure.file_transfer import LocalFileRead


async def open_audio_file(path: str) -> LocalFileRead:
    """Open ``path`` in a worker thread; the caller closes what it receives.

    Args:
        path: The audio file on the API's filesystem.

    Returns:
        The opened reader, its size fixed at the opening.

    Raises:
        STTProviderError: ``provider_http_error`` when the file cannot be opened —
            missing, unreadable, a link, or not a regular file.
    """
    try:
        return await LocalFileRead.async_open(Path(path))
    except (OSError, ValueError) as exc:
        raise STTProviderError(
            code="provider_http_error",
            message=f"Audio file unreadable: {exc.__class__.__name__}",
        ) from exc
