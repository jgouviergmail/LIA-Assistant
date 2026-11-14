"""Every module that lists a mailbox DECLARES whether it tells where a message stands (ADR-379).

A message read alone cannot say whether it was answered: the reply is another message
of the same conversation. Until 2026-11-11 every surface listed mail on its own — the
chat tool, the heartbeat, the briefing, the relationship views, the Tools — and none
asked the mailbox what happened next, so the assistant offered to answer mail the
person had already answered. Found one surface at a time, the next one forgets again.

So the family is a DECLARATION over a COMPLETE list (the ``direct_client_callers``
doctrine). The guard (``tests/unit/domains/connectors/test_mail_listers_guard.py``)
walks every module outside the client layer that calls a mailbox's listing
(``search_emails``) and refuses one that declares nothing here, one declared that no
longer lists, and one whose declaration is not what it does: each standing names the
part of the door (``mail_reply_states``) the module goes through, and no other.

- ``SITUATED`` — what the module lists is judged by a model or shown to the person as
  mail to deal with: each message carries its reply state, read from its conversation.
- ``MARKED`` — the module tells what the mailbox ITSELF marks of each message, read
  with the message, and nothing a conversation read would add: an answer that left no
  mark is not seen. The reason no conversation is read is written beside the entry.
- ``NOT_SITUATED`` — the module tells no reply state: one would say nothing useful
  there. The reason is written beside the entry, and it is a reason one can check.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final


class Standing(str, Enum):
    """Whether a lister tells where each message stands in its conversation."""

    SITUATED = "situated"
    MARKED = "marked"
    NOT_SITUATED = "not_situated"


@dataclass(frozen=True, slots=True)
class MailLister:
    """What one module that lists a mailbox does about reply states, and why."""

    standing: Standing
    reason: str


#: Module path under ``src/`` → its declaration. Every lister outside the client
#: layer, and nothing else: the guard refuses an omission AND a stale entry.
MAIL_LISTERS: Final[dict[str, MailLister]] = {
    "domains/agents/tools/emails_tools.py": MailLister(
        Standing.SITUATED,
        "the chat's mail tool, by search and by ids, in both execution modes: what a model "
        "reads and what the card draws both say whether the person answered",
    ),
    "domains/briefing/fetchers.py": MailLister(
        Standing.SITUATED,
        "the unread mail of the Today briefing: the card marks a mail already answered, the "
        "greeting, the synthesis and the radio's journal read the same state; a routine's "
        "condition, which only matches the listing, opts out (situate_items=False)",
    ),
    "domains/connectors/discussion_sources.py": MailLister(
        Standing.MARKED,
        "a proactive discussion's evidence is versioned by its content, and every proof is "
        "read again at its version before any use (ADR-358): what it tells must come WITH "
        "the message, the same at every read — the mailbox's own mark, part of the fact. "
        "One conversation read per listed message does not fit the physical-call allowance "
        "of a read (DISCUSSION_READ_CALL_LIMIT) on a mailbox that reads one thread per call, "
        "and read fail-open it would move a version between two reads and stop the run as a "
        "changed fact. Gmail keeps no mark: its search covers sent mail, so the person's "
        "reply is itself evidence in the window",
    ),
    "domains/heartbeat/mail_context.py": MailLister(
        Standing.SITUATED,
        "the unread mail a heartbeat tick or wake is told: mail the person already answered "
        "is left out before the cap, and an answer drafted but never sent is said on its line",
    ),
    "domains/agents/emails/writing_style.py": MailLister(
        Standing.NOT_SITUATED,
        "reads the person's own SENT e-mails to learn how they write (ADR-383): only their "
        "words are read, nothing is listed or answered, and a reply state says nothing of a voice",
    ),
    "domains/radio/readers/sent_mail.py": MailLister(
        Standing.NOT_SITUATED,
        "the journal's « done » part tells what the listener SENT today: the sending is the "
        "fact told, whether an answer came since is not, and nothing there is mail to answer",
    ),
    "domains/relations/overview/fallback.py": MailLister(
        Standing.SITUATED,
        "the mail found by NAME for a person with no address, read by the overview's model: "
        "one already answered is never told as awaiting an answer",
    ),
    "domains/relations/providers/emails.py": MailLister(
        Standing.SITUATED,
        "the mail exchanged with one person, for their 360° view, their overview and their "
        "debrief: a mail of theirs the owner answered, a mail sent that got a reply",
    ),
    "domains/tool_assists/contact_card.py": MailLister(
        Standing.NOT_SITUATED,
        "reads a contact's latest messages for what their signature says (a number, an "
        "organisation) to complete the card: no message is told there as mail to deal with",
    ),
    "domains/workbench/contacts_history.py": MailLister(
        Standing.SITUATED,
        "the latest mail exchanged with a contact, in the Tools: each row shown marks an "
        "answer given or a reply received",
    ),
    "domains/workbench/mail_reading.py": MailLister(
        Standing.SITUATED,
        "the mailbox as the person lists it in the Tools: the listing is one search, and the "
        "marks of the rows shown are read apart (read_reply_marks), so the page never waits",
    ),
}

__all__ = ["MAIL_LISTERS", "MailLister", "Standing"]
