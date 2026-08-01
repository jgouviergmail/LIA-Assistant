"""Peers domain constants — the cross-layer contracts of the program.

Two audiences share these names and must never drift apart:

- the WRITERS — the delivery engine
  (``infrastructure/scheduler/peer_message_delivery``) and the lifecycle
  dispatcher (``domains/peers/notifications``) — which stamp the metadata of
  every archived peer notification;
- the READERS — the chat quick-actions
  (``components/chat/PeerMessageActions`` on the frontend), which decide what
  a bubble IS and who to act on from that metadata alone, and the Relations
  CRM (``domains/relations/peer_messages``), which uses only ``type`` and
  ``target_id`` to find a delivered text again — identity there comes from the
  ledger's foreign keys, never from a name frozen in a payload.

Nothing between them type-checks the agreement, so it is pinned by
``tests/unit/domains/peers/test_message_archive_contract.py``: the archived
``type`` is asserted against the REAL dispatcher composition, and every other
peers notification is asserted NOT to produce it.
"""

from __future__ import annotations

#: Proactive task type of a RELAYED message delivered to its recipient.
#: ``NotificationDispatcher`` derives the archived metadata ``type`` from it.
PEER_MESSAGE_TASK_TYPE = "peer_message"

#: Proactive task type of every connection-lifecycle notice — accepted,
#: declined, removed, AND the sender's own delivered/failed delivery notice.
PEER_CONNECTION_TASK_TYPE = "peer_connection"

#: Proactive task type of an INCOMING connection request.
PEER_REQUEST_TASK_TYPE = "peer_request"

#: ``conversation_messages.message_metadata['type']`` of a delivered relayed
#: message. Composed exactly as the dispatcher composes it — the single value
#: a reader may filter on (prefix matching would also catch requests and
#: lifecycle notices, which are NOT messages from the peer).
PROACTIVE_PEER_MESSAGE_TYPE = f"proactive_{PEER_MESSAGE_TASK_TYPE}"

#: Metadata key: boolean marker written since Lot 7. NO reader depends on it —
#: what identifies a relayed bubble is ``type``, which cannot be imitated by
#: another peers notification. Kept because rows already carry it and dropping
#: a key from a persisted contract buys nothing.
PEER_META_MESSAGE_FLAG = "peer_message"

#: Metadata key: id of the sender. Read by the CHAT quick-actions, which act
#: on the other side straight from the bubble. The CRM does NOT read it — it
#: resolves identity from the ledger's foreign key, which survives a rename.
PEER_META_SENDER_ID = "sender_id"

#: Metadata key: sender's display name AT DELIVERY TIME. A snapshot for the
#: chat quick-actions, never a source of truth: it freezes a name the person
#: may since have changed, which is exactly why the CRM ignores it.
PEER_META_SENDER_NAME = "sender_name"

#: Display fallback when a participant has no ``full_name`` (the column is
#: nullable). Shared so readers can reject it in ONE place: a CRM card titled
#: "?" is a phantom relationship, not a person.
PEER_UNKNOWN_DISPLAY_NAME = "?"

#: Direction of a relayed message on the CALLER's timeline. Part of the
#: ``/relations`` payload contract — the frontend renders one arrow per value.
PEER_MESSAGE_DIRECTION_RECEIVED = "received"
PEER_MESSAGE_DIRECTION_SENT = "sent"


__all__ = [
    "PEER_CONNECTION_TASK_TYPE",
    "PEER_MESSAGE_DIRECTION_RECEIVED",
    "PEER_MESSAGE_DIRECTION_SENT",
    "PEER_MESSAGE_TASK_TYPE",
    "PEER_META_MESSAGE_FLAG",
    "PEER_META_SENDER_ID",
    "PEER_META_SENDER_NAME",
    "PEER_REQUEST_TASK_TYPE",
    "PEER_UNKNOWN_DISPLAY_NAME",
    "PROACTIVE_PEER_MESSAGE_TYPE",
]
