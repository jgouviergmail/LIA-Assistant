"""The wire path of a stored file — spelled once (ADR-318).

Every producer of a chat card — the image tool, the document generator, the
browser screenshot, a shared image (ADR-316), and the generated-files lookup —
hands the client a RELATIVE path the web app resolves against the API origin
(``apiResourceUrl``). The first four wrote ``/api/v1/attachments/{id}`` by
hand and the response's URL allowlist carried a fifth copy of the prefix; a
path the router serves is one declaration.
"""

from __future__ import annotations

import uuid
from typing import Final

__all__ = ["ATTACHMENT_PATH_PREFIX", "attachment_url"]

#: The route ``GET /api/v1/attachments/{attachment_id}`` serves, as a prefix —
#: also the prefix a proxied photo URL is allowed to carry.
ATTACHMENT_PATH_PREFIX: Final = "/api/v1/attachments/"


def attachment_url(attachment_id: uuid.UUID | str) -> str:
    """The relative path the client fetches a stored file from.

    Args:
        attachment_id: The attachment.

    Returns:
        ``/api/v1/attachments/{id}``.
    """
    return f"{ATTACHMENT_PATH_PREFIX}{attachment_id}"
