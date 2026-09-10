"""What a ticket says to LIA when it runs alone (ADR-276).

The brief is the one place a ticket's content becomes an INSTRUCTION, so what
goes into it is a security decision, not a formatting one:

- **the owner's words only.** A peer who holds a ticket can write a comment,
  and a comment that reached the brief would be a stranger dictating what LIA
  does on somebody else's account (ADR-167/170 — data are never instructions).
  The OWNER's own notes do reach it since lot 7 — their answer to a
  confirmation travels this way — through ONE query that takes the owner as
  its author, so the exclusion of everyone else holds by shape.
- **an approved action is cited to the letter**, so the replay has a chance to
  rebuild exactly what the person confirmed (ADR-092).
- **the shape of the work travels, the work of others does not.** A child
  ticket carries its parent's title and its siblings' titles so a decomposed
  plan keeps its context, and it is told to do ITS step only.
- **the brief is bounded by the columns' own caps.** Nothing here can grow
  without a cap somewhere refusing the write first.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.config import settings
from src.core.constants import (
    WORKBOARD_BRIEF_MAX_NOTES_DEFAULT,
    WORKBOARD_COMMENT_MAX_CHARS_DEFAULT,
    WORKBOARD_DESCRIPTION_MAX_CHARS_DEFAULT,
    WORKBOARD_MAX_CHILDREN_PER_TICKET_DEFAULT,
    WORKBOARD_TITLE_MAX_CHARS_DEFAULT,
)
from src.domains.workboard.brief import build_ticket_brief

pytestmark = pytest.mark.unit

OWNER = uuid.uuid4()


def _ticket(**overrides: Any) -> Any:
    ticket = MagicMock()
    ticket.id = overrides.pop("id", uuid.uuid4())
    ticket.owner_user_id = OWNER
    ticket.title = "Book the venue"
    ticket.description = "Find a room for twelve on the 20th."
    ticket.parent_id = None
    ticket.last_run_at = None
    ticket.pending_action = None
    for name, value in overrides.items():
        setattr(ticket, name, value)
    return ticket


def _note(body: str) -> Any:
    return MagicMock(body=body)


def _repository(
    *, parent: Any = None, children: list[Any] | None = None, notes: list[Any] | None = None
) -> Any:
    """A repository that can answer THREE questions and no others.

    ``spec_set`` is the oracle of the « owner's words only » rule: a brief that
    reached for the comment THREAD would raise here rather than quietly build
    a bigger prompt. The one comment query it may ask takes the owner as its
    author.
    """
    repository = MagicMock(spec_set=["get_visible", "list_children", "owner_notes_since"])
    repository.get_visible = AsyncMock(return_value=parent)
    repository.list_children = AsyncMock(return_value=children or [])
    repository.owner_notes_since = AsyncMock(return_value=notes or [])
    return repository


class TestTheOwnersWords:
    async def test_the_title_and_the_description_are_the_task(self) -> None:
        brief = await build_ticket_brief(_repository(), _ticket(), language="fr")

        assert "Book the venue" in brief
        assert "Find a room for twelve on the 20th." in brief

    async def test_a_ticket_with_no_description_still_reads_as_a_task(self) -> None:
        """The title alone is a legitimate ticket — « Appeler le traiteur » is
        a complete instruction, and inventing a description would be worse."""
        brief = await build_ticket_brief(
            _repository(), _ticket(title="Call the caterer", description=None), language="fr"
        )

        assert "Call the caterer" in brief
        assert "What they wrote about it" not in brief

    async def test_an_empty_description_is_the_same_as_none(self) -> None:
        brief = await build_ticket_brief(_repository(), _ticket(description="   "), language="fr")

        assert "What they wrote about it" not in brief

    async def test_the_answer_language_is_named_not_coded(self) -> None:
        """« Answer in fr » is a code; a model reads a name."""
        brief = await build_ticket_brief(_repository(), _ticket(), language="zh-CN")

        assert "Simplified Chinese" in brief

    async def test_only_the_owners_notes_can_reach_the_brief(self) -> None:
        """The rule this module exists for: a peer holding the ticket can write
        a comment, and a comment in the brief is a stranger giving orders on
        somebody else's account. The one comment query is asked with the OWNER
        as its author; the thread itself is never read."""
        repository = _repository()

        brief = await build_ticket_brief(repository, _ticket(), language="fr")

        assert brief, "reaching for anything else would have raised"
        call = repository.owner_notes_since.await_args
        assert call.args[1] == OWNER
        with pytest.raises(AttributeError):
            # The double really is that narrow — without this the test above
            # would pass on a repository that answers everything.
            repository.list_comments  # noqa: B018

    async def test_braces_in_the_persons_words_are_not_a_template(self) -> None:
        """« payer la facture {montant} » once cost a whole occurrence: the
        text was interpolated INTO a template and raised ``KeyError``. Here the
        person's words are always a VALUE, never a format string."""
        brief = await build_ticket_brief(
            _repository(),
            _ticket(
                title="Pay {supplier}",
                description="Amount is {montant} before {date}, ref {{42}}",
            ),
            language="fr",
        )

        assert "Pay {supplier}" in brief
        assert "{montant}" in brief
        assert "{{42}}" in brief

    async def test_the_board_state_is_not_part_of_the_instruction(self) -> None:
        """Status, priority and position describe how the person ORGANISES the
        work; none of them tells LIA what to do, and each would be one more
        thing for a model to react to."""
        brief = await build_ticket_brief(
            _repository(),
            _ticket(status="todo", priority="urgent", position=3),
            language="fr",
        )

        assert "urgent" not in brief.lower()
        assert "position" not in brief.lower()


class TestADecomposedPlan:
    async def test_a_child_carries_its_parent_and_its_siblings(self) -> None:
        child_id = uuid.uuid4()
        parent = _ticket(title="Organise the launch party")
        siblings = [
            _ticket(id=child_id, title="Book the venue"),
            _ticket(title="Send the invitations"),
            _ticket(title="Order the food"),
        ]
        repository = _repository(parent=parent, children=siblings)

        brief = await build_ticket_brief(
            repository,
            _ticket(id=child_id, title="Book the venue", parent_id=parent.id),
            language="fr",
        )

        assert "Organise the launch party" in brief
        assert "Send the invitations" in brief
        assert "Order the food" in brief

    async def test_a_child_is_told_to_do_its_own_step_only(self) -> None:
        parent = _ticket(title="Organise the launch party")
        repository = _repository(parent=parent, children=[])

        brief = await build_ticket_brief(repository, _ticket(parent_id=parent.id), language="fr")

        assert "ONE step" in brief
        assert "YOUR step only" in brief

    async def test_a_child_is_not_listed_among_its_own_siblings(self) -> None:
        child = _ticket(title="Book the venue")
        parent = _ticket(title="Organise the launch party")
        repository = _repository(parent=parent, children=[child, _ticket(title="Order the food")])

        brief = await build_ticket_brief(
            repository,
            _ticket(id=child.id, title="Book the venue", parent_id=parent.id),
            language="fr",
        )

        assert brief.count("Book the venue") == 1, "the step must not be its own sibling"

    async def test_a_parent_carries_the_steps_it_was_broken_into(self) -> None:
        repository = _repository(
            children=[_ticket(title="Book the venue"), _ticket(title="Order the food")]
        )

        brief = await build_ticket_brief(
            repository, _ticket(title="Organise the launch party"), language="fr"
        )

        assert "Book the venue" in brief
        assert "Order the food" in brief

    async def test_a_lone_ticket_carries_no_context_block(self) -> None:
        brief = await build_ticket_brief(_repository(), _ticket(), language="fr")

        assert "ONE step" not in brief
        assert "broke this task into steps" not in brief

    async def test_a_missing_parent_does_not_stop_the_run(self) -> None:
        """A parent deleted between the claim and the brief is a race, not a
        reason to fail a ticket whose own words are right there."""
        repository = _repository(parent=None, children=[])

        brief = await build_ticket_brief(repository, _ticket(parent_id=uuid.uuid4()), language="fr")

        assert "Book the venue" in brief
        assert "ONE step" not in brief


class TestTheOwnersNotes:
    """Lot 7: what the owner wrote since LIA's last run is part of the task."""

    async def test_the_notes_are_listed_oldest_first_as_the_query_returns_them(self) -> None:
        brief = await build_ticket_brief(
            _repository(notes=[_note("Oui mais pour 14 personnes."), _note("Et près du métro.")]),
            _ticket(),
            language="fr",
        )

        assert "Notes the person added on the ticket since your last run" in brief
        assert brief.index("14 personnes") < brief.index("près du métro")
        assert "  - Oui mais pour 14 personnes." in brief

    async def test_a_multi_line_note_stays_one_bullet(self) -> None:
        brief = await build_ticket_brief(
            _repository(notes=[_note("Deux choses :\n1. la salle\n2. le traiteur")]),
            _ticket(),
            language="fr",
        )
        assert "  - Deux choses :\n    1. la salle\n    2. le traiteur" in brief

    async def test_the_query_is_bounded_and_starts_at_the_last_run(self) -> None:
        from datetime import UTC, datetime

        last_run = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
        repository = _repository()
        await build_ticket_brief(repository, _ticket(last_run_at=last_run), language="fr")

        call = repository.owner_notes_since.await_args
        assert call.kwargs == {"since": last_run, "limit": settings.workboard_brief_max_notes}

    async def test_no_note_means_no_block(self) -> None:
        brief = await build_ticket_brief(_repository(), _ticket(), language="fr")
        assert "Notes the person added" not in brief

    async def test_a_blank_note_is_not_a_note(self) -> None:
        brief = await build_ticket_brief(
            _repository(notes=[_note("   ")]), _ticket(), language="fr"
        )
        assert "Notes the person added" not in brief

    async def test_braces_in_a_note_are_not_a_template(self) -> None:
        brief = await build_ticket_brief(
            _repository(notes=[_note("Budget {montant} max")]), _ticket(), language="fr"
        )
        assert "Budget {montant} max" in brief

    async def test_a_zero_cap_reads_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "workboard_brief_max_notes", 0)
        repository = _repository(notes=[_note("Oui")])
        brief = await build_ticket_brief(repository, _ticket(), language="fr")
        repository.owner_notes_since.assert_not_awaited()
        assert "Notes the person added" not in brief


class TestAnApprovedAction:
    """Lot 7: the replay cites what was approved, to the letter."""

    def _approved(self) -> dict[str, Any]:
        return {
            "draft_id": "draft_1",
            "draft_type": "tool_call",
            "draft_content": {
                "tool_name": "send_email_tool",
                "tool_args": {"to": "paul@example.org", "body": "Budget {montant}"},
            },
            "tool_name": "send_email_tool",
            "question": "J'envoie ?",
            "approved": True,
        }

    async def test_it_is_cited_whole_with_its_tool(self) -> None:
        brief = await build_ticket_brief(
            _repository(), _ticket(pending_action=self._approved()), language="fr"
        )

        assert "has APPROVED, on the ticket, the exact action below" in brief
        assert 'calling the tool "send_email_tool"' in brief
        assert "Approved draft (tool_call)" in brief
        assert '"to": "paul@example.org"' in brief
        assert "Budget {montant}" in brief

    async def test_a_draft_still_awaiting_its_answer_is_not_an_instruction(self) -> None:
        pending = {**self._approved(), "approved": False}
        brief = await build_ticket_brief(
            _repository(), _ticket(pending_action=pending), language="fr"
        )
        assert "APPROVED" not in brief
        assert "paul@example.org" not in brief

    async def test_no_draft_means_no_block(self) -> None:
        brief = await build_ticket_brief(_repository(), _ticket(), language="fr")
        assert "APPROVED" not in brief


class TestItIsBounded:
    async def test_the_worst_brief_stays_inside_the_columns_caps(self) -> None:
        """No cap of its own, and none needed: every input is already bounded
        by the write path — the notes by their cap and their count — so the
        brief's ceiling is arithmetic rather than a second number somebody
        would have to keep in step."""
        children = [
            _ticket(title="s" * WORKBOARD_TITLE_MAX_CHARS_DEFAULT)
            for _ in range(WORKBOARD_MAX_CHILDREN_PER_TICKET_DEFAULT)
        ]
        notes = [
            _note("n" * WORKBOARD_COMMENT_MAX_CHARS_DEFAULT)
            for _ in range(WORKBOARD_BRIEF_MAX_NOTES_DEFAULT)
        ]
        brief = await build_ticket_brief(
            _repository(children=children, notes=notes),
            _ticket(
                title="t" * WORKBOARD_TITLE_MAX_CHARS_DEFAULT,
                description="d" * WORKBOARD_DESCRIPTION_MAX_CHARS_DEFAULT,
            ),
            language="fr",
        )

        ceiling = (
            WORKBOARD_TITLE_MAX_CHARS_DEFAULT
            + WORKBOARD_DESCRIPTION_MAX_CHARS_DEFAULT
            + WORKBOARD_MAX_CHILDREN_PER_TICKET_DEFAULT * (WORKBOARD_TITLE_MAX_CHARS_DEFAULT + 8)
            + WORKBOARD_BRIEF_MAX_NOTES_DEFAULT * (WORKBOARD_COMMENT_MAX_CHARS_DEFAULT + 8)
            + 4000  # the scaffolding itself
        )
        assert len(brief) < ceiling


class TestAnApprovedBatch:
    async def test_every_draft_of_the_batch_is_cited_in_order(self) -> None:
        first = {"tool_name": "send_email_tool", "tool_args": {"to": "a@example.org"}}
        second = {"tool_name": "send_email_tool", "tool_args": {"to": "b@example.org"}}
        pending = {
            "draft_type": "tool_call",
            "draft_content": first,
            "tool_name": "send_email_tool",
            "batch": [
                {"draft_id": "d1", "draft_type": "tool_call", "draft_content": first},
                {"draft_id": "d2", "draft_type": "tool_call", "draft_content": second},
            ],
            "approved": True,
        }
        brief = await build_ticket_brief(
            _repository(), _ticket(pending_action=pending), language="fr"
        )
        assert "a@example.org" in brief and "b@example.org" in brief
        assert brief.index("a@example.org") < brief.index("b@example.org")
        assert "a list means several drafts approved together" in brief
