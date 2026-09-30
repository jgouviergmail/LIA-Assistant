"""The chat cards a turn queues for its answer (ADR-226, ADR-279, ADR-327).

A tool that produces something the person sees as a card (a generated image, a
generated document, a skill ready to install) cannot write it into the answer:
the answer is archived and streamed by the streaming layer, after the graph.
So the tool QUEUES the card under the conversation, the archive PEEKS it into
the message metadata (the card must survive a reload) and the done chunk TAKES
it (the live card, and the queue is freed).

One shape for every card family: the image and document stores were two
copies of it, and a third family would have been a third.
"""

from __future__ import annotations

import threading


class PendingCards[T]:
    """Cards queued per conversation, until the answer carrying them is sent.

    Process-local on purpose: the turn that queues a card is the turn that
    archives and streams it, in the same worker.
    """

    def __init__(self, family: str) -> None:
        """Name the card family (for the reader of a heap dump or a test).

        Args:
            family: What these cards are, e.g. ``"generated_documents"``.
        """
        self.family = family
        self._cards: dict[str, list[T]] = {}
        self._lock = threading.Lock()

    def add(self, conversation_id: str, card: T) -> None:
        """Queue a card under the answer being written for this conversation.

        Args:
            conversation_id: The conversation's thread id.
            card: The card's payload.
        """
        with self._lock:
            self._cards.setdefault(conversation_id, []).append(card)

    def peek(self, conversation_id: str) -> list[T]:
        """The queued cards, left in place (the archive; the done chunk still needs them).

        Args:
            conversation_id: The conversation's thread id.

        Returns:
            A copy of the queue, oldest first; empty when nothing is queued.
        """
        with self._lock:
            return list(self._cards.get(conversation_id, []))

    def take(self, conversation_id: str) -> list[T]:
        """The queued cards, removed (the done chunk frees the queue).

        Args:
            conversation_id: The conversation's thread id.

        Returns:
            The queue, oldest first; empty when nothing is queued.
        """
        with self._lock:
            return self._cards.pop(conversation_id, [])

    def clear(self) -> None:
        """Forget every conversation's cards (a test's isolation, never production)."""
        with self._lock:
            self._cards.clear()
