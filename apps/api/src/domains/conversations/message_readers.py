"""Every module that queries the message table outside its repository DECLARES how it reads.

Since ADR-276 a conversation holds rows a person must never be shown: the
question and the answer of a ticket LIA ran alone, archived so the record stays
whole and marked ``hidden`` so the chat stays quiet. The repository applies
that predicate to every read it owns — and a predicate a repository applies
says nothing about the modules that build their own ``select`` over the same
table. Measured 2026-09-09: nineteen modules reference the model, and the
heartbeat's « last user message » read took a run's synthetic question for the
person's last words.

Three found one at a time is not a method, so this module makes the answer a
DECLARATION over a COMPLETE list (the ``direct_client_callers`` doctrine): the
guard walks every module under ``src/``, finds each one that reads a column of
``ConversationMessage``, and refuses one that is not declared here, one that is
declared and no longer reads, and one declared ``VISIBLE_ONLY`` whose statement
carries no hidden-row exclusion.

Two scopes, and the reason is written beside each entry:

- ``VISIBLE_ONLY`` — the module interprets rows as the PERSON's: what they last
  said, when they were last active, what they mean. A run's rows must not
  reach it.
- ``WHOLE_RECORD`` — the module measures, exports, purges or joins the record
  itself, or narrows to rows a run never writes. Hiding rows from it would make
  a count wrong or a record incomplete.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final


class ReadScope(str, Enum):
    """How a module reads the message table."""

    VISIBLE_ONLY = "visible_only"
    WHOLE_RECORD = "whole_record"


class ConversationReadScope(str, Enum):
    """Which discussions a reader intentionally traverses, independently of visibility."""

    TARGET = "target"  # An admitted target or a message/opening's explicit source.
    MAIN = "main"  # External channels and automatic notifications.
    ACCOUNT = "account"  # Shared learning, rhythm and personal exports.
    INSTANCE = "instance"  # Operator-only exports and aggregate maintenance/metrics.


@dataclass(frozen=True, slots=True)
class MessageReader:
    """Both independent scopes and the verified purpose of a direct reader."""

    visibility: ReadScope
    conversations: frozenset[ConversationReadScope]
    reason: str


#: Module path → both scopes and reason. Every reader outside the repository, and
#: nothing else: the guard refuses an omission AND a stale entry.
MESSAGE_READERS: Final[dict[str, MessageReader]] = {
    "src.domains.conversations.discussion_search": MessageReader(
        ReadScope.VISIBLE_ONLY,
        frozenset({ConversationReadScope.ACCOUNT}),
        "finds the person's words and LIA's answers across the account's active discussions, "
        "for the history search field and the assistant's lookup; only what the chat shows",
    ),
    "src.domains.conversations.lifecycle": MessageReader(
        ReadScope.WHOLE_RECORD,
        frozenset({ConversationReadScope.TARGET}),
        "retires the owned generation, including hidden rows; never projects its content",
    ),
    "src.domains.conversations.publication_repository": MessageReader(
        ReadScope.WHOLE_RECORD,
        frozenset({ConversationReadScope.TARGET}),
        "deduplicates an exact invocation's request and answer, including hidden runs; never treats its HITL question as its answer",
    ),
    "src.domains.proactive_discussions.outbox_repository": MessageReader(
        ReadScope.VISIBLE_ONLY,
        frozenset({ConversationReadScope.TARGET}),
        "delivers only the owner's visible assistant opening joined through its owner-bound outbox and logical discussion",
    ),
    "src.domains.proactive_discussions.replies": MessageReader(
        ReadScope.VISIBLE_ONLY,
        frozenset({ConversationReadScope.TARGET}),
        "binds genuine visible human replies to the owner's archived discussion and acknowledges only matching extraction receipts",
    ),
    "src.domains.proactive_discussions.history": MessageReader(
        ReadScope.VISIBLE_ONLY,
        frozenset({ConversationReadScope.TARGET}),
        "old assistant opening wording is read only after its complete current proof set was freshly permitted",
    ),
    "src.domains.proactive_discussions.openings": MessageReader(
        ReadScope.VISIBLE_ONLY,
        frozenset({ConversationReadScope.TARGET}),
        "the owner's visible assistant openings and explicit feedback, with stable archived identities",
    ),
    "src.domains.agents.services.card_composition_service": MessageReader(
        ReadScope.VISIBLE_ONLY,
        frozenset({ConversationReadScope.TARGET}),
        "validates a message-owned composition target from an owned visible assistant answer; "
        "a hidden run is never a browser selection",
    ),
    "src.domains.voice_sessions.summary": MessageReader(
        ReadScope.WHOLE_RECORD,
        frozenset({ConversationReadScope.TARGET}),
        "narrows to rows stamped with a voice session key (ADR-299, ADR-301 — a browser "
        "session id or a phone call's run id), a key a hidden run never writes: the run "
        "ids of the session's delegated turns and its voice-only rows",
    ),
    "src.domains.radio.readers.notifications": MessageReader(
        ReadScope.VISIBLE_ONLY,
        frozenset({ConversationReadScope.MAIN}),
        "the notifications the person was told, which the radio comes back to (ADR-324) — "
        "a hidden run row is not something they were told",
    ),
    "src.domains.radio.readers.reminders": MessageReader(
        ReadScope.VISIBLE_ONLY,
        frozenset({ConversationReadScope.MAIN}),
        "the reminders that rang today, read from the message each one left in the chat "
        "(ADR-324 decision 41) — a hidden run row is not a reminder the person heard",
    ),
    "src.domains.conversations.activity_probe": MessageReader(
        ReadScope.VISIBLE_ONLY,
        frozenset({ConversationReadScope.ACCOUNT}),
        "when the person was last active — a run's synthetic question is not them speaking",
    ),
    "src.domains.heartbeat.context_sources": MessageReader(
        ReadScope.WHOLE_RECORD,
        frozenset({ConversationReadScope.ACCOUNT}),
        "narrowed to proactive rows by their `type`, a key a run's rows never carry",
    ),
    "src.domains.journals.conversation_sources": MessageReader(
        ReadScope.VISIBLE_ONLY,
        frozenset({ConversationReadScope.ACCOUNT}),
        "the person's rhythm and their exchange — a run's brief is LIA's words, not theirs",
    ),
    "src.domains.conversations.response_feedback": MessageReader(
        ReadScope.WHOLE_RECORD,
        frozenset({ConversationReadScope.TARGET}),
        "marks the row a person voted on, by the run id the card carries — a hidden row is "
        "never shown, so it is never voted on",
    ),
    "src.domains.shared.provenance_repository": MessageReader(
        ReadScope.WHOLE_RECORD,
        frozenset({ConversationReadScope.TARGET}),
        "reads the content of a row a provenance reference names by id",
    ),
    "src.domains.google_api.export_service": MessageReader(
        ReadScope.WHOLE_RECORD,
        frozenset({ConversationReadScope.ACCOUNT, ConversationReadScope.INSTANCE}),
        "an export is the record, and STT/TTS cost rows are never a run's",
    ),
    "src.infrastructure.scheduler.demo_daily_report": MessageReader(
        ReadScope.WHOLE_RECORD,
        frozenset({ConversationReadScope.INSTANCE}),
        "counts the record for the demo operator, hidden rows included and said so",
    ),
    "src.infrastructure.observability.lifetime_metrics": MessageReader(
        ReadScope.WHOLE_RECORD,
        frozenset({ConversationReadScope.INSTANCE}),
        "measures the record: an archived row is a row, whoever wrote it",
    ),
    "src.domains.workboard.repository": MessageReader(
        ReadScope.WHOLE_RECORD,
        frozenset({ConversationReadScope.INSTANCE}),
        "the retention sweep targets the hidden rows themselves and measures their volume",
    ),
    "src.domains.bookmarks.repository": MessageReader(
        ReadScope.VISIBLE_ONLY,
        frozenset({ConversationReadScope.TARGET}),
        "the answer a person chose to keep and their last words before it — a run's rows are "
        "never shown, so never kept, and its synthetic question is not what they asked",
    ),
}


__all__ = ["MESSAGE_READERS", "ReadScope", "ConversationReadScope", "MessageReader"]
