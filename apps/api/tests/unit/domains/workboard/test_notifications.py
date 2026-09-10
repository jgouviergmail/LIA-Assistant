"""Who hears about a ticket, and what they read (ADR-276).

The recipient table is enumerated rather than sampled: it is the whole of D6,
the owner's arbitration that a board must not become a source of noise, and one
wrong cell either spams a person or leaves a ticket stuck with nobody told.

The one rule that is NOT a preference: « it is waiting for you » ignores the
follow flag. A run that stopped is a question, and a question nobody hears is a
ticket that never moves again.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from src.core.constants import WORKBOARD_NOTIFICATION_EXCERPT_MAX_CHARS
from src.domains.workboard.constants import AssigneeKind
from src.domains.workboard.notifications import (
    FOLLOW_GATED,
    WorkboardEvent,
    excerpt_of,
    notification_body,
    notification_metadata,
    recipients_for,
)

pytestmark = pytest.mark.unit

OWNER = uuid.uuid4()
PEER = uuid.uuid4()

PROGRESS_EVENTS = [
    WorkboardEvent.RUN_STARTED,
    WorkboardEvent.RUN_FINISHED,
    WorkboardEvent.RUN_FAILED,
]


def _ticket(**overrides: Any) -> Any:
    ticket = type("T", (), {})()
    ticket.id = uuid.uuid4()
    ticket.title = "Book the venue"
    ticket.owner_user_id = OWNER
    ticket.assignee_kind = AssigneeKind.LIA.value
    ticket.assignee_user_id = None
    ticket.follow_owner = False
    ticket.follow_assignee = False
    for name, value in overrides.items():
        setattr(ticket, name, value)
    ticket.effective_assignee_id = ticket.assignee_user_id or ticket.owner_user_id
    return ticket


class TestFollowingIsOffByDefault:
    @pytest.mark.parametrize("event", PROGRESS_EVENTS, ids=lambda e: e.value)
    def test_nothing_is_announced_on_a_ticket_nobody_follows(self, event: WorkboardEvent) -> None:
        """A board of forty tickets that each announced themselves would train
        the person to ignore the chat (D6)."""
        assert recipients_for(event, _ticket()) == ()

    @pytest.mark.parametrize("event", PROGRESS_EVENTS, ids=lambda e: e.value)
    def test_the_owner_hears_when_they_asked_to(self, event: WorkboardEvent) -> None:
        assert recipients_for(event, _ticket(follow_owner=True)) == (OWNER,)

    @pytest.mark.parametrize("event", PROGRESS_EVENTS, ids=lambda e: e.value)
    def test_the_peer_hears_when_they_asked_to(self, event: WorkboardEvent) -> None:
        ticket = _ticket(
            assignee_kind=AssigneeKind.HUMAN.value,
            assignee_user_id=PEER,
            follow_assignee=True,
        )
        assert recipients_for(event, ticket) == (PEER,)

    def test_both_sides_can_follow_the_same_ticket(self) -> None:
        ticket = _ticket(
            assignee_kind=AssigneeKind.HUMAN.value,
            assignee_user_id=PEER,
            follow_owner=True,
            follow_assignee=True,
        )
        assert recipients_for(WorkboardEvent.RUN_FINISHED, ticket) == (OWNER, PEER)

    def test_the_assignee_flag_finds_nobody_when_lia_holds_it(self) -> None:
        """A ticket LIA holds has no second human side; the flag has nobody to
        point at, and the owner must not be notified twice."""
        ticket = _ticket(follow_owner=True, follow_assignee=True)
        assert recipients_for(WorkboardEvent.RUN_FINISHED, ticket) == (OWNER,)

    def test_a_null_assignee_is_the_owner_and_not_a_second_recipient(self) -> None:
        """NULL means « the owner holds it » — the board's own convention."""
        ticket = _ticket(
            assignee_kind=AssigneeKind.HUMAN.value,
            assignee_user_id=None,
            follow_owner=True,
            follow_assignee=True,
        )
        assert recipients_for(WorkboardEvent.RUN_FINISHED, ticket) == (OWNER,)

    def test_nobody_is_told_what_they_just_did(self) -> None:
        ticket = _ticket(
            assignee_kind=AssigneeKind.HUMAN.value,
            assignee_user_id=PEER,
            follow_owner=True,
            follow_assignee=True,
        )
        assert recipients_for(WorkboardEvent.RUN_FINISHED, ticket, actor_user_id=PEER) == (OWNER,)


class TestAQuestionGoesToTheHolderWhoSubscribed:
    """D59: the flag means what it says, and a question is the HOLDER's alone."""

    def test_a_stopped_run_reaches_a_holder_who_follows_the_ticket(self) -> None:
        assert recipients_for(WorkboardEvent.WAITING, _ticket(follow_owner=True)) == (OWNER,)

    def test_it_says_nothing_in_the_chat_when_they_do_not(self) -> None:
        """« LIA travaille en silence » is the flag's own promise. The ticket is
        still found: the column, the hub badge, and the heartbeat after
        ``WORKBOARD_NUDGE_WAITING_HOURS`` — which never reads the flag."""
        assert recipients_for(WorkboardEvent.WAITING, _ticket(follow_owner=False)) == ()

    def test_it_reaches_the_account_the_run_belongs_to_not_the_owner(self) -> None:
        """The run executed on the holder's account, with their tools and their
        quota: they are the only one who can answer it."""
        ticket = _ticket(
            assignee_kind=AssigneeKind.HUMAN.value,
            assignee_user_id=PEER,
            follow_assignee=True,
        )
        assert recipients_for(WorkboardEvent.WAITING, ticket) == (PEER,)

    def test_the_holders_own_flag_decides_it_never_the_owners(self) -> None:
        """A question a peer must answer is not the owner's to subscribe to."""
        ticket = _ticket(
            assignee_kind=AssigneeKind.HUMAN.value,
            assignee_user_id=PEER,
            follow_owner=True,
            follow_assignee=False,
        )
        assert recipients_for(WorkboardEvent.WAITING, ticket) == ()

    def test_the_other_side_is_never_offered_a_question(self) -> None:
        """Subscribed or not: only the holder can answer it."""
        ticket = _ticket(
            assignee_kind=AssigneeKind.HUMAN.value,
            assignee_user_id=PEER,
            follow_owner=True,
            follow_assignee=True,
        )
        assert recipients_for(WorkboardEvent.WAITING, ticket) == (PEER,)

    def test_being_handed_a_ticket_still_ignores_every_flag(self) -> None:
        """The one event no flag can gate: nobody subscribes to a ticket they
        do not yet know they hold."""
        ticket = _ticket(assignee_kind=AssigneeKind.HUMAN.value, assignee_user_id=PEER)
        assert recipients_for(WorkboardEvent.ASSIGNED, ticket) == (PEER,)


class TestWhatTheyRead:
    @pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
    @pytest.mark.parametrize("event", list(WorkboardEvent), ids=lambda e: e.value)
    def test_every_event_has_a_sentence_in_every_language(
        self, event: WorkboardEvent, language: str
    ) -> None:
        body = notification_body(
            event, _ticket(), language=language, comment="Done.", intent_url="https://x/y"
        )
        assert body
        assert "{" not in body, "no placeholder may reach a reader"

    def test_the_body_names_the_ticket(self) -> None:
        body = notification_body(WorkboardEvent.RUN_FINISHED, _ticket(), language="fr")
        assert "Book the venue" in body

    def test_a_stopped_run_carries_the_link_that_finishes_it(self) -> None:
        body = notification_body(
            WorkboardEvent.WAITING, _ticket(), language="fr", intent_url="https://lia/x?intent=y"
        )
        assert "https://lia/x?intent=y" in body

    def test_a_title_that_looks_like_a_template_is_not_one(self) -> None:
        """« payer la facture {montant} » cost a reminder its occurrence once."""
        body = notification_body(
            WorkboardEvent.RUN_STARTED, _ticket(title="Payer {montant}"), language="fr"
        )
        assert "Payer {montant}" in body

    def test_an_unknown_event_says_nothing_rather_than_something_wrong(self) -> None:
        from src.core.i18n_proactive import ProactiveMessages

        assert ProactiveMessages.workboard_body("invented", "T", "fr") == ""


class TestHandingATicketOver:
    """« It was handed to you » is the one thing the flag cannot cover."""

    def test_the_new_holder_is_told_whatever_the_flags_say(self) -> None:
        ticket = _ticket(
            assignee_kind=AssigneeKind.HUMAN.value,
            assignee_user_id=PEER,
            follow_owner=False,
            follow_assignee=False,
        )
        assert recipients_for(WorkboardEvent.ASSIGNED, ticket) == (PEER,)

    def test_the_person_who_handed_it_over_is_not_told(self) -> None:
        """They just did it."""
        ticket = _ticket(assignee_kind=AssigneeKind.HUMAN.value, assignee_user_id=PEER)
        assert recipients_for(WorkboardEvent.ASSIGNED, ticket, actor_user_id=PEER) == ()

    def test_taking_a_ticket_back_tells_nobody(self) -> None:
        """A NULL assignee means the owner holds it; there is no new holder."""
        ticket = _ticket(assignee_kind=AssigneeKind.HUMAN.value, assignee_user_id=None)
        assert recipients_for(WorkboardEvent.ASSIGNED, ticket) == ()

    def test_handing_it_to_lia_tells_nobody(self) -> None:
        """LIA reads no notifications; the owner already knows they asked."""
        assert recipients_for(WorkboardEvent.ASSIGNED, _ticket()) == ()

    def test_the_owner_is_never_told_they_still_own_it(self) -> None:
        ticket = _ticket(
            assignee_kind=AssigneeKind.HUMAN.value,
            assignee_user_id=PEER,
            follow_owner=True,
        )
        assert OWNER not in recipients_for(WorkboardEvent.ASSIGNED, ticket)

    def test_the_body_names_the_ticket(self) -> None:
        ticket = _ticket(assignee_kind=AssigneeKind.HUMAN.value, assignee_user_id=PEER)
        body = notification_body(WorkboardEvent.ASSIGNED, ticket, language="fr")
        assert "Book the venue" in body


class TestWhereTheLinksPoint:
    def test_the_board_and_the_ticket_share_one_builder(self) -> None:
        """Two builders would eventually name two different boards."""
        from src.domains.workboard.notifications import board_url, ticket_url

        ticket = _ticket()
        assert ticket_url(ticket).startswith(board_url() + "/")
        assert str(ticket.id) in ticket_url(ticket)

    def test_the_intent_link_carries_the_instruction_in_the_readers_language(self) -> None:
        from src.domains.workboard.notifications import intent_url

        french = intent_url(_ticket(), "fr")
        chinese = intent_url(_ticket(), "zh-CN")
        assert "intent=" in french
        assert french != chinese

    def test_a_title_with_a_space_is_escaped_not_broken(self) -> None:
        """The sentence travels in a query string; an unescaped one truncates."""
        from src.domains.workboard.notifications import intent_url

        url = intent_url(_ticket(title="Book the venue"), "fr")
        assert " " not in url.split("intent=", 1)[1]


class TestTheExcerpt:
    def test_a_short_answer_is_quoted_whole(self) -> None:
        assert excerpt_of("The room is booked.") == "The room is booked."

    def test_a_long_answer_is_cut_and_says_so(self) -> None:
        excerpt = excerpt_of("x" * 5000)
        assert len(excerpt) == WORKBOARD_NOTIFICATION_EXCERPT_MAX_CHARS
        assert excerpt.endswith("…")

    def test_the_excerpt_is_one_line(self) -> None:
        """A push notification is a headline; a paragraph break in it renders
        as whatever the platform feels like."""
        assert excerpt_of("Two\n\nparagraphs\there") == "Two paragraphs here"

    def test_no_answer_quotes_nothing(self) -> None:
        assert excerpt_of(None) == ""
        assert excerpt_of("   ") == ""


class TestTheMetadata:
    def test_it_carries_what_the_action_row_needs(self) -> None:
        ticket = _ticket()
        payload = notification_metadata(
            WorkboardEvent.RUN_FINISHED,
            ticket,
            board_url="https://lia/board",
            ticket_url="https://lia/board/1",
        )
        assert payload["event"] == "run_finished"
        assert payload["ticket_id"] == str(ticket.id)
        assert payload["ticket_title"] == "Book the venue"
        assert payload["board_url"] == "https://lia/board"
        assert payload["ticket_url"] == "https://lia/board/1"

    def test_the_intent_link_travels_only_when_there_is_one(self) -> None:
        """An empty key would make the frontend draw a button leading nowhere."""
        payload = notification_metadata(
            WorkboardEvent.RUN_FINISHED, _ticket(), board_url="b", ticket_url="t"
        )
        assert "intent" not in payload

        waiting = notification_metadata(
            WorkboardEvent.WAITING,
            _ticket(),
            board_url="b",
            ticket_url="t",
            intent_url="https://lia/chat?intent=finish",
        )
        assert waiting["intent"] == "https://lia/chat?intent=finish"

    def test_the_type_is_the_dispatchers_to_write(self) -> None:
        """Two places writing `proactive_workboard` is one place too many."""
        payload = notification_metadata(
            WorkboardEvent.WAITING, _ticket(), board_url="b", ticket_url="t"
        )
        assert "type" not in payload


class TestAConfirmationIsAQuestion:
    """Lot 7: « LIA needs your go-ahead » is heard by the holder, flags or not."""

    def test_it_reaches_a_holder_who_follows_the_ticket(self) -> None:
        assert recipients_for(WorkboardEvent.CONFIRMING, _ticket(follow_owner=True)) == (OWNER,)

    def test_it_says_nothing_in_the_chat_on_an_unfollowed_ticket(self) -> None:
        """D59: the confirmation waits on the board, not in the chat."""
        assert recipients_for(WorkboardEvent.CONFIRMING, _ticket(follow_owner=False)) == ()

    def test_it_reaches_the_account_the_run_belongs_to(self) -> None:
        ticket = _ticket(
            assignee_kind=AssigneeKind.HUMAN.value,
            assignee_user_id=PEER,
            follow_assignee=True,
        )
        assert recipients_for(WorkboardEvent.CONFIRMING, ticket) == (PEER,)

    def test_it_is_read_as_a_question_not_as_progress(self) -> None:
        """Progress may reach BOTH subscribed sides; a question reaches the
        holder alone — so it is gated, but not by the progress rule."""
        assert WorkboardEvent.CONFIRMING not in FOLLOW_GATED

    @pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
    def test_the_body_links_to_the_ticket_where_it_is_answered(self, language: str) -> None:
        body = notification_body(
            WorkboardEvent.CONFIRMING,
            _ticket(),
            language=language,
            ticket_url="https://lia.example/dashboard/workboard/1",
        )
        assert "(https://lia.example/dashboard/workboard/1)" in body
        assert "Book the venue" in body

    def test_a_finished_run_does_not_link_to_the_ticket_in_its_body(self) -> None:
        """The action row already offers it; the sentence quotes the answer."""
        body = notification_body(
            WorkboardEvent.RUN_FINISHED,
            _ticket(),
            language="fr",
            comment="Done.",
            ticket_url="https://lia.example/dashboard/workboard/1",
        )
        assert "https://lia.example" not in body
