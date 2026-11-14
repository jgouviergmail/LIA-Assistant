"""Where a report's pictures go (ADR-274).

One frame for every picture of a page — the cover of a document and each of its
illustration blocks — at the text width of an A4 page with Word's margins
(6.3 in, which Letter's wider text column holds too), in the proportions of a
photograph (3:2). Word places it at that size; the PDF at the width the Story
gives a paragraph when that is narrower, its height following.

A picture nobody drew is absent from the context: the cover is set without it
and an illustration block writes nothing — not even its caption, which would
name a figure that is not there.
"""

from __future__ import annotations

from src.domains.document_generation.pictures import Frame, IllustrationRequest
from src.domains.document_generation.schemas import SectionedContent

#: The one frame of a page's pictures, in inches.
PAGE = Frame("page", 6.3, 4.2)


def picture_requests(content: SectionedContent) -> list[IllustrationRequest]:
    """The pictures a normalized report asks for: its cover first, then its blocks in order.

    Args:
        content: The normalized document; its pictures are within the budget.

    Returns:
        One request per picture, in document order.
    """
    requests: list[IllustrationRequest] = []
    if content.illustration is not None:
        requests.append(IllustrationRequest(content.illustration.subject, PAGE))
    requests.extend(
        IllustrationRequest(block.illustration.subject, PAGE)
        for block in content.blocks
        if block.kind == "illustration" and block.illustration is not None
    )
    return requests


__all__ = ["PAGE", "picture_requests"]
