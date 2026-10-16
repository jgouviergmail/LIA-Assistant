"""Whether a message item is one of the person's mailbox drafts (ADR-344).

One predicate for every reader that draws or acts on a message: a draft is the
person's own unsent text, so it is headed by its recipients, offers no
« Reply » nor « Forward » — which would answer the person's own draft — and
opens in the provider's compose window. A draft tool marks its items with
``mailbox_draft_id``; a draft read some other way still carries the label every
provider's normaliser gives it.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.core.field_names import FIELD_MAILBOX_DRAFT_ID

#: The label every e-mail normaliser gives a draft (Gmail, Graph, IMAP).
DRAFT_LABEL = "DRAFT"


def is_mailbox_draft(payload: Mapping[str, object]) -> bool:
    """Whether ``payload`` is a draft in the person's mailbox.

    Args:
        payload: A message item, as the e-mail tools publish it.

    Returns:
        True for an item a draft tool published, or one labelled a draft.
    """
    if payload.get(FIELD_MAILBOX_DRAFT_ID):
        return True
    labels = payload.get("labelIds")
    return isinstance(labels, list) and DRAFT_LABEL in labels


__all__ = ["DRAFT_LABEL", "is_mailbox_draft"]
