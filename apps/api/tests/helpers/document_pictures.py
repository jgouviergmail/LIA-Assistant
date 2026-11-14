"""Synthetic pictures for documents rendered without an image model (corpus, tests).

A corpus document that asks for pictures gets one flat-coloured picture per
request, cropped and resampled by the production's own ``fit_to_frame``: the
layout around a picture is measured — in the tests and by Office — without a
vendor call or a cent spent.
"""

from __future__ import annotations

import io
from dataclasses import replace
from types import MappingProxyType
from typing import Any

from PIL import Image

from src.core.document_preferences import DocumentPreferences
from src.domains.document_generation.context import RenderContext
from src.domains.document_generation.illustrations import fit_to_frame, requests_for
from src.domains.document_generation.normalize import normalize_content
from src.domains.document_generation.pictures import Picture
from src.domains.document_generation.schemas import DocumentContent

#: Flat colours a reader can tell apart on a slide, cycled over the requests.
_COLOURS: tuple[tuple[int, int, int], ...] = ((44, 120, 214), (201, 133, 0), (0, 131, 0))


def synthetic_pictures(content: DocumentContent) -> MappingProxyType[str, Picture]:
    """One flat picture for every picture a normalized document asks for.

    Args:
        content: A normalized document.

    Returns:
        The pictures, by the key the renderer looks them up under.
    """
    pictures: dict[str, Picture] = {}
    for index, request in enumerate(requests_for(content)):
        buffer = io.BytesIO()
        colour = _COLOURS[index % len(_COLOURS)]
        Image.new("RGB", (1024, 1536), colour).save(buffer, format="PNG")
        pictures[request.key] = fit_to_frame(buffer.getvalue(), request.frame)
    return MappingProxyType(pictures)


def fixture_context(raw: dict[str, Any], content: DocumentContent) -> RenderContext:
    """The context a corpus fixture declares: its reader, its structure, its pictures.

    ``"pictures": "synthetic"`` lets the document carry pictures (the reader's
    images on, the default budget) and draws each one flat.

    Args:
        raw: The fixture, as read from its JSON file.
        content: Its content, validated.

    Returns:
        The context to render it with.
    """
    pictured = raw.get("pictures") == "synthetic"
    context = RenderContext(
        language=raw.get("language", "en"),
        structure=raw.get("structure", "auto"),
        preferences=DocumentPreferences(images_allowed=pictured),
    )
    if not pictured:
        return context
    return replace(context, pictures=synthetic_pictures(normalize_content(content, context)))
