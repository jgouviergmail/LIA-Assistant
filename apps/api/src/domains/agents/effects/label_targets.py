"""What an effect's label names when its call carries only an id (ADR-367).

« Reply to Marc's email » saves a reply draft whose call names the message by
its provider id; « mark the dentist task done » completes a task by its id.
The label — built at CLAIM time, the only moment the arguments exist, and
sealed into the ledger chain as built (ADR-263) — could then only say « a
reply draft was saved »: nobody could see WHICH message it answered, which is
exactly how the incident of 2026-10-29 stayed invisible in the register.

Whoever runs the tools publishes the items the turn can name — the registry:
what the person was shown and what this turn fetched — for the length of the
call (:func:`publishing_label_items`); a label builder reads, for an id the
call carries, the words that item was shown with (:func:`item_title`). A
ContextVar, set per call: parallel steps run in tasks of their own, so each
reads what its own executor published.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Final

__all__ = ["item_title", "publishing_label_items"]

_ITEMS: ContextVar[Mapping[str, Any] | None] = ContextVar("effect_label_items", default=None)

#: The fields a payload carries a provider id under.
_ID_FIELDS: Final = (
    "id",
    "message_id",
    "task_id",
    "event_id",
    "file_id",
    "resource_name",
    "mailbox_draft_id",
)
#: The fields that name an item for a reader — the first carried wins.
_NAME_FIELDS: Final = ("subject", "title", "summary", "name")


@contextmanager
def publishing_label_items(registry: Mapping[str, Any] | None) -> Iterator[None]:
    """Publish the turn's registry to the labels built during one tool call.

    Args:
        registry: Registry id → ``RegistryItem`` or its checkpointed dict.

    Yields:
        Nothing; the items are published until the block ends.
    """
    token = _ITEMS.set(registry or None)
    try:
        yield
    finally:
        _ITEMS.reset(token)


def _payload(item: Any) -> Mapping[str, Any] | None:
    payload = item.get("payload") if isinstance(item, Mapping) else getattr(item, "payload", None)
    return payload if isinstance(payload, Mapping) else None


def item_title(identifier: object) -> str | None:
    """The words a published item designated by a provider id was shown with.

    Args:
        identifier: The id a tool call carries (a message id, a task id…).

    Returns:
        The item's subject, title, summary or name; None when nothing
        published carries that id (the label then shows what it had).
    """
    items = _ITEMS.get()
    if not items or not isinstance(identifier, str) or not identifier:
        return None
    for item in items.values():
        payload = _payload(item)
        if payload is None or all(payload.get(field) != identifier for field in _ID_FIELDS):
            continue
        for field in _NAME_FIELDS:
            name = payload.get(field)
            if isinstance(name, str) and name.strip():
                return name
    return None
