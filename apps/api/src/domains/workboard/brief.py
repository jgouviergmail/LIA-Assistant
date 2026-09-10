"""What a ticket says to LIA when it runs it alone (ADR-276).

This is the one place a ticket's content becomes an INSTRUCTION, so what enters
it is a security decision rather than a formatting one:

- **the owner's words only.** A peer holding a ticket can write a comment,
  and a comment carried into an unattended run would be a stranger dictating
  what LIA does with somebody else's account, tools and quota (ADR-167/170:
  data are never instructions). The OWNER's comments do reach the brief since
  lot 7 — their answer to a confirmation travels this way — and the rule is
  enforced by SHAPE: the one query this module asks for comments takes the
  owner as its author and pins the ``user`` kind, so a peer's words cannot
  come back from it however it is called.
- **an approved action is replayed to the letter.** When the person approved
  a draft on the ticket, the brief cites it whole and says so; the HITL node
  then lets the rebuilt draft through only on the exact identity of what was
  shown (ADR-092), so the citation is what gives the replay a chance to match.
- **the person's words are always a VALUE, never a format string.** A
  description reading « payer la facture {montant} » cost a reminder its whole
  occurrence once: the text had been interpolated INTO a template, and
  ``str.format`` raised on the unknown key. Every substitution below puts the
  person's text on the right-hand side, and ``str.format`` does not rescan what
  it substitutes.
- **the prompt text lives in the store, not here.** The main template and the
  three fragments the ticket's own shape switches on are versioned files, read
  by PATH: lot 3 makes ``agents`` import ``workboard``, so importing the agents
  prompt loader from this package would close a cycle — the break meetings,
  telephony and documents already made (:mod:`src.core.prompt_store`).

The brief carries no cap of its own, and needs none: the title, the description
and the number of children are each bounded by the write path, so its ceiling
is arithmetic instead of a fourth number somebody would have to keep in step.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from src.core.config import settings
from src.core.i18n_types import get_language_name
from src.core.prompt_store import read_prompt_file

if TYPE_CHECKING:
    from src.domains.workboard.models import WorkboardTicket
    from src.domains.workboard.repository import WorkboardRepository


def _bullets(titles: list[str]) -> str:
    """Render titles as a list. Structure, so it is built here, not in a file.

    Args:
        titles: The titles, already in board order.

    Returns:
        One ``- title`` line per entry.
    """
    return "\n".join(f"- {title}" for title in titles)


def _description_block(description: str | None) -> str:
    """The person's own words about the ticket, when they wrote any.

    An empty description is not a defect: « Appeler le traiteur » is a complete
    instruction, and inventing a sentence to fill the slot would put words in
    their mouth.

    Args:
        description: What the owner wrote, if anything.

    Returns:
        The rendered fragment, or an empty string.
    """
    if not description or not description.strip():
        return ""
    return read_prompt_file("workboard_brief_description").format(description=description)


async def _context_block(repository: WorkboardRepository, ticket: WorkboardTicket) -> str:
    """Where this ticket sits in a decomposed plan, if it sits in one.

    Two shapes, never both: a ticket is a step of something bigger, or it was
    broken into steps — the hierarchy is ONE level deep by design.

    A parent that disappeared between the claim and the brief is a race, not a
    reason to fail a ticket whose own words are right there: the context is
    dropped and the run goes on.

    Args:
        repository: Reads the surrounding tickets.
        ticket: The ticket being briefed.

    Returns:
        The rendered fragment, or an empty string for a lone ticket.
    """
    if ticket.parent_id is not None:
        parent = await repository.get_visible(ticket.parent_id, ticket.owner_user_id)
        if parent is None:
            return ""
        siblings = await repository.list_children(ticket.parent_id)
        return read_prompt_file("workboard_brief_parent_step").format(
            parent_title=parent.title,
            sibling_titles=_bullets([other.title for other in siblings if other.id != ticket.id]),
        )
    children = await repository.list_children(ticket.id)
    if not children:
        return ""
    return read_prompt_file("workboard_brief_substeps").format(
        child_titles=_bullets([child.title for child in children])
    )


async def _notes_block(repository: WorkboardRepository, ticket: WorkboardTicket) -> str:
    """What the owner wrote on the ticket since LIA last ran it.

    Their answer to a confirmation, a correction, a precision — the owner's
    own words, so they are instructions like the description is. Bounded by
    ``workboard_brief_max_notes`` notes of ``workboard_comment_max_chars`` each.

    Args:
        repository: Reads the owner's comments.
        ticket: The ticket being briefed.

    Returns:
        The rendered fragment, or an empty string when there is nothing new.
    """
    if settings.workboard_brief_max_notes <= 0:
        return ""
    notes = await repository.owner_notes_since(
        ticket.id,
        ticket.owner_user_id,
        since=ticket.last_run_at,
        limit=settings.workboard_brief_max_notes,
    )
    bodies = [note.body.strip() for note in notes if note.body.strip()]
    if not bodies:
        return ""
    return read_prompt_file("workboard_brief_notes").format(
        notes="\n".join("  - " + body.replace("\n", "\n    ") for body in bodies)
    )


def _approved_block(ticket: WorkboardTicket) -> str:
    """The action the person approved on the ticket, cited whole.

    Args:
        ticket: The ticket being briefed.

    Returns:
        The rendered fragment, or an empty string when nothing is approved.
    """
    pending = ticket.pending_action or {}
    if not pending.get("approved"):
        return ""
    batch = pending.get("batch") or []
    cited: object = (
        [item.get("draft_content") or {} for item in batch]
        if batch
        else pending.get("draft_content") or {}
    )
    return read_prompt_file("workboard_brief_approved_action").format(
        tool_name=str(pending.get("tool_name") or ""),
        draft_type=str(pending.get("draft_type") or ""),
        content_json=json.dumps(cited, ensure_ascii=False, indent=2, sort_keys=True),
    )


async def build_ticket_brief(
    repository: WorkboardRepository, ticket: WorkboardTicket, *, language: str
) -> str:
    """Compose the instruction one run of a ticket receives.

    Args:
        repository: Reads the parent and the siblings of a decomposed ticket,
            and the owner's notes since the last run.
        ticket: The claimed ticket.
        language: Backend-canonical code of the account the run belongs to;
            the brief names the language rather than coding it, because a model
            reads « French » and not « fr ».

    Returns:
        The message the pipeline runs, as the person's own instruction.
    """
    return read_prompt_file("workboard_ticket_brief_prompt").format(
        title=ticket.title,
        description_block=_description_block(ticket.description),
        context_block=await _context_block(repository, ticket),
        notes_block=await _notes_block(repository, ticket),
        approved_block=_approved_block(ticket),
        user_language=get_language_name(language),
    )
