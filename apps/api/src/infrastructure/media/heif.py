"""HEIC/HEIF support for Pillow — registered once, where a stranger's picture is decoded.

Pillow opens no HEIC by itself: the codec is the ``pillow-heif`` plugin, which
must be REGISTERED before ``Image.open`` meets an iPhone photo. Three places
decode a picture somebody else produced — an upload, a mail attachment, a
photo handed to the image editor — and each calls :func:`ensure_heif_support`
before opening it. The registration is idempotent and lazy: the plugin (and
libheif under it) is imported on the first picture, never at boot.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_registered = False


def ensure_heif_support() -> None:
    """Register the HEIF opener with Pillow, once per process (thread-safe)."""
    global _registered
    if _registered:
        return
    with _lock:
        if _registered:
            return
        from pillow_heif import register_heif_opener

        register_heif_opener()
        _registered = True


__all__ = ["ensure_heif_support"]
