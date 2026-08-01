"""The 360° tool — what it reads, and what it refuses to pretend.

Production, 2026-07-31: a user asked for a 360° point on a connected peer and
got "je n'ai pas réussi à remonter ses interactions récentes". Two defects
behind it, both closed here:

- the tool was catalogued but its module was never imported, so the planner
  selected a tool the executor could not find (pinned by the catalogue/registry
  parity guard, next door);
- it searched mail by the person's NAME and the calendar by a text query —
  neither of which reliably finds a person. It now delegates to the Relations
  services, which resolve ADDRESSES from the user's own address book.

The third thing tested here is the SCOPE: the chat link carries prose, so the
selection is read server-side. What the user ticked is what the assistant
gets, whatever the sentence says.

Replaces ``test_person_tools.py``, whose oracles pinned the by-name searches
this rewrite removed. Its two concerns did not vanish, they MOVED:

- the aggregation and its partial-failure honesty are the classes below;
- "the provider client is closed on every path, including when the body
  raises" now belongs to the module that owns the client —
  tests/unit/domains/relations/providers/test_client.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.tools import person_tools
from src.domains.relations.overview_scope import (
    OverviewDirection,
    OverviewRole,
    OverviewSection,
    RelationOverviewScope,
)
from src.domains.relations.providers.schemas import (
    ContactCard,
    ContactEmail,
    ContactPhone,
    ContactValue,
    ContextSection,
    ContextStatus,
    ExchangedEmail,
    RelationContext,
    SharedEvent,
)
from src.domains.relations.schemas import (
    IdentityConfidence,
    RelationCall,
    RelationDetail,
    RelationMemory,
    RelationOpenLoop,
    RelationPeerLink,
    RelationPeerMessage,
    RelationShare,
)

pytestmark = pytest.mark.unit

USER_ID = uuid4()
NOW = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)


def _detail(**over) -> RelationDetail:
    base = {
        "display_name": "Gérard Dupont",
        "identity_confidence": IdentityConfidence.EXACT,
        "open_loops": [
            RelationOpenLoop(
                id=f"l{index}",
                subject=f"Engagement {index}",
                direction="user_owes",
                due_hint=None,
                days_open=index,
            )
            for index in range(8)
        ],
        "open_loops_total": 8,
        "recent_calls": [
            RelationCall(
                id="c1", objective="Anniversaire", outcome=None, summary=None, created_at=NOW
            )
        ],
        "recent_calls_total": 1,
        "memories": [RelationMemory(id="m1", content="Aime la randonnée")],
        "memories_total": 1,
        "peer_messages": [
            RelationPeerMessage(id="p1", direction="received", content="Salut", occurred_at=NOW),
            RelationPeerMessage(id="p2", direction="sent", content="Ok", occurred_at=NOW),
        ],
        "peer_messages_total": 2,
        "peer_link": None,
        "is_favorite": False,
        "is_peer": True,
    }
    return RelationDetail(**{**base, **over})


def _section(status=ContextStatus.OK, **over) -> ContextSection:
    return ContextSection(status=status, generated_at=NOW, **over)


def _context(**over) -> RelationContext:
    base = {
        "contact": _section(
            contact=ContactCard(
                display_name="Gérard Dupont",
                organization="ACME",
                emails=[ContactEmail(value="gerard@x.com", label="work")],
            )
        ),
        "emails": _section(
            emails=[
                ExchangedEmail(id="e1", direction="received", subject="Devis", occurred_at=NOW),
                ExchangedEmail(id="e2", direction="sent", subject="Relance", occurred_at=NOW),
            ]
        ),
        "events": _section(
            events=[
                SharedEvent(
                    id="v1",
                    summary="Chantier",
                    starts_at=NOW,
                    ends_at=NOW,
                    is_past=False,
                    role="organizer",
                    organizer_known=True,
                ),
                SharedEvent(
                    id="v2",
                    summary="Point",
                    starts_at=NOW,
                    ends_at=None,
                    is_past=False,
                    role="attendee",
                    organizer_known=True,
                ),
            ]
        ),
        "addresses_used": 1,
        "window_days": 90,
        "email_window_days": 365,
    }
    return RelationContext(**{**base, **over})


def _runtime():
    return SimpleNamespace(context=SimpleNamespace(user_id=str(USER_ID)))


#: Sentinel: `_run(memories=...)` defaults to a working recall. Passing None
#: means "the embedding could not be computed", which is a DIFFERENT answer
#: from an empty list and must never be reported as one.
_DEFAULT_MEMORIES = ["Aime la randonnée"]


async def _run(*, scope=None, detail=None, context=None, by_name=None, memories=_DEFAULT_MEMORIES):
    """Invoke the tool with the reads stubbed.

    ``by_name`` stubs the last-resort fallback: (emails, events) as the
    old-style by-name searches would return them.

    ``memories`` stubs the semantic recall. Stubbed rather than left live on
    purpose: the real one needs an embedding provider, so an unstubbed test
    would assert one thing on a developer machine and another in CI — where no
    key exists and the recall answers "I could not look".
    """
    service = SimpleNamespace(
        get_overview_scope=AsyncMock(return_value=scope or RelationOverviewScope.default()),
        build_detail=AsyncMock(
            return_value=detail if detail is not None else _detail(),
            side_effect=detail if isinstance(detail, BaseException) else None,
        ),
    )
    ctx_service = SimpleNamespace(
        build=AsyncMock(
            return_value=context if context is not None else _context(),
            side_effect=context if isinstance(context, BaseException) else None,
        )
    )
    mails, events = by_name or ([], [])
    with (
        patch.object(person_tools, "RelationsService", return_value=service),
        patch.object(person_tools, "RelationContextService", return_value=ctx_service),
        patch.object(person_tools, "_fetch_recent_emails", AsyncMock(return_value=mails)),
        patch.object(person_tools, "_fetch_upcoming_events", AsyncMock(return_value=events)),
        patch.object(
            person_tools,
            "_fetch_person_memories",
            AsyncMock(
                return_value=None if isinstance(memories, BaseException) else memories,
                side_effect=memories if isinstance(memories, BaseException) else None,
            ),
        ),
        patch.object(
            person_tools,
            "validate_runtime_config",
            return_value=SimpleNamespace(user_id=str(USER_ID)),
        ),
    ):
        return await person_tools.get_person_overview_tool.coroutine(
            person_name="Gérard Dupont", runtime=_runtime()
        )


class TestItReadsTheWholeCard:
    """The reported defect: mails and meetings were missing from the answer."""

    async def test_carries_both_halves_of_the_relationship(self) -> None:
        result = await _run()
        data = result.structured_data
        assert set(data) >= {
            "open_commitments",
            "recent_calls",
            "memories",
            "relayed_messages",
            "contact",
            "emails",
            "events",
        }
        assert data["contact"]["emails"] == ["gerard@x.com"]
        assert [item["subject"] for item in data["emails"]] == ["Devis", "Relance"]

    async def test_states_the_windows_it_looked_at(self) -> None:
        """No totals — a provider page proves none. The SCOPE instead."""
        data = (await _run()).structured_data
        assert data["emails_window_days"] == 365
        assert data["events_window_days"] == 90

    async def test_the_assistant_reads_the_same_card_the_page_shows(self) -> None:
        """Asking about a person and opening their file must agree.

        The card holds far more than a name and a mailbox; sending four fields
        while the page shows twelve makes the assistant look less informed than
        the screen the user just closed.
        """
        card = ContactCard(
            display_name="Gérard Dupont",
            nickname="Gégé",
            organization="ACME",
            occupation="Architecte",
            birthday="--04-07",
            biography="Rencontré au forum.",
            emails=[ContactEmail(value="gerard@x.com", label="work")],
            phones=[ContactPhone(value="+33600000000", label="mobile")],
            addresses=[ContactValue(value="12 rue des Lilas, Lyon", label="home")],
            relations=[ContactValue(value="Claire Lefèvre", label="spouse")],
            links=[ContactValue(value="https://example.com", label=None)],
            important_dates=[ContactValue(value="2011-09-03", label="anniversary")],
            messaging=[ContactValue(value="gerard.d", label="skype")],
        )
        data = (await _run(context=_context(contact=_section(contact=card)))).structured_data

        assert data["contact"]["nickname"] == "Gégé"
        assert data["contact"]["occupation"] == "Architecte"
        assert data["contact"]["birthday"] == "--04-07"
        assert data["contact"]["biography"] == "Rencontré au forum."
        assert data["contact"]["addresses"] == ["12 rue des Lilas, Lyon"]
        # The label is what makes the value legible: "Claire Lefèvre" alone
        # does not say she is his spouse.
        assert data["contact"]["relations"] == ["Claire Lefèvre (spouse)"]
        assert data["contact"]["important_dates"] == ["2011-09-03 (anniversary)"]
        # A phone the assistant may be asked to call needs its label; a postal
        # address already names a street and a city.
        assert data["contact"]["phones"] == ["+33600000000 (mobile)"]
        assert data["contact"]["addresses"] == ["12 rue des Lilas, Lyon"]
        assert data["contact"]["links"] == ["https://example.com"]
        # The protocol is what tells the assistant HOW to reach that handle.
        assert data["contact"]["messaging"] == ["gerard.d (skype)"]

    async def test_a_block_the_address_book_lacks_is_absent_not_empty(self) -> None:
        """Apple and Microsoft store no relations at all.

        Sending ``"relations": []`` invites the model to answer "he has no
        family recorded" — a negative nobody verified (ADR-184).
        """
        data = (await _run()).structured_data
        assert "relations" not in data["contact"]
        assert "birthday" not in data["contact"]
        assert data["contact"]["display_name"] == "Gérard Dupont"


class TestTheScopeIsObeyed:
    """Not a hint the planner may honor — a selection the tool applies."""

    async def test_an_unticked_section_is_absent_entirely(self) -> None:
        scope = RelationOverviewScope(sections=[OverviewSection.OPEN_LOOPS])
        data = (await _run(scope=scope)).structured_data
        assert "open_commitments" in data
        for absent in ("emails", "events", "memories", "relayed_messages", "contact"):
            assert absent not in data

    async def test_the_item_cap_is_applied_per_section(self) -> None:
        scope = RelationOverviewScope(max_items=3)
        data = (await _run(scope=scope)).structured_data
        assert len(data["open_commitments"]) == 3

    async def test_directions_filter_mail_and_relayed_messages_alike(self) -> None:
        scope = RelationOverviewScope(directions=[OverviewDirection.RECEIVED])
        data = (await _run(scope=scope)).structured_data
        assert [item["direction"] for item in data["emails"]] == ["received"]
        assert [item["direction"] for item in data["relayed_messages"]] == ["received"]

    async def test_roles_filter_meetings(self) -> None:
        scope = RelationOverviewScope(roles=[OverviewRole.ORGANIZER])
        data = (await _run(scope=scope)).structured_data
        assert [item["summary"] for item in data["events"]] == ["Chantier"]

    async def test_a_role_nobody_verified_is_never_filtered_on(self) -> None:
        """Apple exposes no organizer. Filtering by role there would drop every
        meeting — reporting an empty agenda for a distinction we cannot make."""
        context = _context(
            events=_section(
                events=[
                    SharedEvent(
                        id="v1",
                        summary="Chantier",
                        starts_at=NOW,
                        ends_at=None,
                        is_past=False,
                        role="attendee",
                        organizer_known=False,
                    )
                ]
            )
        )
        scope = RelationOverviewScope(roles=[OverviewRole.ORGANIZER])
        data = (await _run(scope=scope, context=context)).structured_data
        assert [item["summary"] for item in data["events"]] == ["Chantier"]
        assert data["events"][0]["role"] == "unknown"


class TestHonestyAboutGaps:
    async def test_names_the_sections_it_could_not_read(self) -> None:
        context = _context(
            emails=_section(status=ContextStatus.NOT_CONFIGURED),
            events=_section(status=ContextStatus.NO_ADDRESS),
        )
        result = await _run(context=context)
        assert set(result.structured_data["unavailable"]) == {"emails", "events"}
        assert "could not read" in result.message

    async def test_an_unticked_section_is_never_reported_as_unavailable(self) -> None:
        """The reader excluded it; it is not a gap."""
        scope = RelationOverviewScope(sections=[OverviewSection.OPEN_LOOPS])
        context = _context(emails=_section(status=ContextStatus.ERROR))
        data = (await _run(scope=scope, context=context)).structured_data
        assert data["unavailable"] == []

    async def test_the_provider_half_failing_never_loses_the_local_half(self) -> None:
        result = await _run(context=TimeoutError("connectors down"))
        data = result.structured_data
        assert data["open_commitments"]  # the database answered
        assert set(data["unavailable"]) == {"contact", "emails", "events"}

    async def test_the_local_half_failing_is_a_failure_not_an_empty_card(self) -> None:
        result = await _run(detail=RuntimeError("db down"))
        assert result.success is False
        assert result.error_code == "person_overview_unavailable"


class TestNameFallbackOfLastResort:
    """No address on the card must not mean an empty answer.

    The address path is exact and comes first. When the card carries no
    address, the old by-name search runs rather than returning nothing — and
    its results are FLAGGED, because matching a name against MIME headers and
    event text finds strangers and misses real threads. The assistant has to
    be able to say so instead of presenting it as fact.
    """

    async def test_fills_mail_and_meetings_when_the_card_has_no_address(self) -> None:
        context = _context(
            emails=_section(status=ContextStatus.NO_ADDRESS),
            events=_section(status=ContextStatus.NO_ADDRESS),
        )
        data = (
            await _run(
                context=context,
                by_name=([{"subject": "Devis"}], [{"title": "Chantier"}]),
            )
        ).structured_data

        assert data["emails"] == [{"subject": "Devis"}]
        assert data["events"] == [{"title": "Chantier"}]
        assert data["unavailable"] == []

    async def test_flags_what_was_matched_by_name(self) -> None:
        """The flag IS the honesty: this path finds strangers and misses threads."""
        context = _context(emails=_section(status=ContextStatus.NO_ADDRESS))
        data = (await _run(context=context, by_name=([{"subject": "Devis"}], []))).structured_data
        assert data["emails_matched_by_name"] is True
        assert "events_matched_by_name" not in data

    async def test_the_cap_still_applies_to_the_fallback(self) -> None:
        context = _context(emails=_section(status=ContextStatus.NO_ADDRESS))
        scope = RelationOverviewScope(max_items=1)
        data = (
            await _run(
                scope=scope,
                context=context,
                by_name=([{"subject": "A"}, {"subject": "B"}], []),
            )
        ).structured_data
        assert len(data["emails"]) == 1

    async def test_a_missing_connector_is_never_retried_by_name(self) -> None:
        """ "Not plugged in" is a different answer from "no address" — asking a
        provider that does not exist would answer a question nobody can ask."""
        context = _context(emails=_section(status=ContextStatus.NOT_CONFIGURED))
        data = (await _run(context=context, by_name=([{"subject": "Devis"}], []))).structured_data
        assert data["unavailable"] == ["emails"]
        assert "emails_matched_by_name" not in data

    async def test_an_empty_fallback_leaves_the_section_unavailable(self) -> None:
        """Nothing found by name is still "I could not read it by address"."""
        context = _context(emails=_section(status=ContextStatus.NO_ADDRESS))
        data = (await _run(context=context, by_name=([], []))).structured_data
        assert data["unavailable"] == ["emails"]

    async def test_an_unticked_section_is_never_filled_by_the_fallback(self) -> None:
        scope = RelationOverviewScope(sections=[OverviewSection.OPEN_LOOPS])
        context = _context(emails=_section(status=ContextStatus.NO_ADDRESS))
        data = (
            await _run(scope=scope, context=context, by_name=([{"subject": "X"}], []))
        ).structured_data
        assert "emails" not in data


class TestACountIsAClaim:
    """ADR-185, one surface further: the assistant states counts out loud.

    The page ships each section's EXACT total next to its capped page. The
    tool used to ship the page alone, so an assistant reading five rows would
    say "you have five open commitments" — the very under-report the CRM cards
    were fixed for.
    """

    async def test_a_commitment_carries_its_deadline(self) -> None:
        """`due_hint` is the most actionable field of the whole payload.

        "What should I raise next" is answered by what is DUE, and the card
        shows it — the assistant was given the age of a commitment but never
        its deadline.
        """
        due = datetime(2026, 8, 15, 9, 0, tzinfo=UTC)
        detail = _detail(
            open_loops=[
                RelationOpenLoop(
                    id="l1",
                    subject="Rendre la perceuse",
                    direction="user_owes",
                    due_hint=due,
                    days_open=4,
                )
            ],
            open_loops_total=1,
        )
        data = (await _run(detail=detail)).structured_data
        assert data["open_commitments"][0]["due_hint"] == due.isoformat()

    async def test_a_commitment_without_a_deadline_says_nothing(self) -> None:
        """Absent, not `null`-shaped prose: most commitments have no due date
        and a key full of nulls trains the model to mention them."""
        data = (await _run()).structured_data
        assert "due_hint" not in data["open_commitments"][0]

    async def test_the_lia_connection_is_part_of_the_briefing(self) -> None:
        """A 360° on a CONNECTED peer that never says they are one.

        Being connected — since when, and what each side shares — is
        relationship context the card shows and the assistant needs before a
        call. Root level, like `identity_confidence`: it describes the
        relationship, it is not a source of items the scope can narrow.
        """
        since = datetime(2026, 5, 4, 8, 0, tzinfo=UTC)
        detail = _detail(
            is_peer=True,
            peer_link=RelationPeerLink(
                connected_since=since,
                shared_by_me=[RelationShare(domain="calendar", level="availability")],
                shared_with_me=[RelationShare(domain="task", level="titles")],
            ),
        )
        data = (await _run(detail=detail)).structured_data
        assert data["is_peer"] is True
        assert data["peer_connection"]["connected_since"] == since.isoformat()
        assert data["peer_connection"]["shared_by_me"] == ["calendar:availability"]
        assert data["peer_connection"]["shared_with_me"] == ["task:titles"]

    async def test_someone_who_is_not_a_connection_carries_no_block(self) -> None:
        data = (await _run()).structured_data
        assert data["is_peer"] is True  # the default fixture is a peer…
        assert "peer_connection" not in data  # …but shares nothing yet

    async def test_every_interaction_can_be_placed_in_time(self) -> None:
        """Production, 2026-08-01: "interactions récentes" came back without
        the calls, though the CRM held four of them.

        Every other block carries an instant — commitments their age, mail and
        relayed messages their date, meetings their slot. Calls carried none,
        so nothing in the payload said they were RECENT, and the block the
        request was literally about could not be used.
        """
        data = (await _run()).structured_data
        assert data["recent_calls"][0]["occurred_at"] == NOW.isoformat()
        assert "days_open" in data["open_commitments"][0]
        assert data["relayed_messages"][0]["occurred_at"]
        assert data["emails"][0]["occurred_at"]
        assert data["events"][0]["starts_at"]

    async def test_each_page_carries_its_exact_total(self) -> None:
        data = (await _run()).structured_data
        # Eight commitments exist; the scope shows five.
        assert len(data["open_commitments"]) == 5
        assert data["open_commitments_total"] == 8
        assert data["recent_calls_total"] == 1
        assert data["relayed_messages_total"] == 2

    async def test_a_filtered_list_carries_NO_total(self) -> None:
        """A direction filter narrows the rows but not the stored total.

        Shipping it anyway would put a count next to a list it does not
        describe — an inexact count must not exist at all.
        """
        scope = RelationOverviewScope(directions=[OverviewDirection.RECEIVED])
        data = (await _run(scope=scope)).structured_data
        assert [item["direction"] for item in data["relayed_messages"]] == ["received"]
        assert "relayed_messages_total" not in data


class TestAnUnreadableSectionIsNeverAnEmptyOne:
    """ "I could not look" and "there is nothing" must not share a payload."""

    async def test_a_broken_section_carries_no_empty_list(self) -> None:
        context = _context(
            emails=_section(ContextStatus.ERROR),
            events=_section(ContextStatus.NOT_CONFIGURED),
        )
        data = (await _run(context=context)).structured_data
        # Neither the rows nor the window: both would read as an answer.
        assert "emails" not in data and "emails_window_days" not in data
        assert "events" not in data and "events_window_days" not in data
        assert set(data["unavailable"]) == {"emails", "events"}

    async def test_a_section_that_looked_and_found_nothing_says_so(self) -> None:
        """EMPTY is a real answer — the list stays, and nothing is flagged."""
        context = _context(emails=_section(ContextStatus.EMPTY))
        data = (await _run(context=context)).structured_data
        assert data["emails"] == []
        assert "emails" not in data["unavailable"]

    async def test_a_recall_that_could_not_run_is_not_an_absence_of_memories(self) -> None:
        """No embedding provider = no answer. Reporting `[]` would have the
        assistant state this person is unmemorable."""
        data = (await _run(memories=None)).structured_data
        assert "memories" not in data
        assert "memories" in data["unavailable"]

    async def test_a_failing_recall_is_reported_the_same_way(self) -> None:
        data = (await _run(memories=RuntimeError("embeddings down"))).structured_data
        assert "memories" not in data
        assert "memories" in data["unavailable"]

    async def test_a_recall_that_genuinely_found_nothing_keeps_the_empty_list(self) -> None:
        data = (await _run(memories=[])).structured_data
        assert data["memories"] == []
        assert "memories" not in data["unavailable"]


class TestWhatActuallyReachesTheAssistant:
    """The payload is worthless if the response synthesizer never sees it.

    Measured on the dev API, 2026-08-01: this tool ran, produced relayed
    messages, commitments and memories, and the assistant answered *"I have no
    data at hand"*. Every oracle above passed throughout — they assert what the
    tool PRODUCES (`structured_data`), and the response prompt is fed by two
    other channels entirely: the data registry (only tools declaring a
    `context_key`, which this one deliberately does not — the registry
    serialises ITEMS for filtering, one truncated line each) and the `message`
    field, which carried `"overview built for X"`. Proof the tool ran, and not
    one fact.

    These oracles therefore assert the CHANNEL, not the payload.
    """

    async def test_the_message_carries_the_facts_not_just_a_receipt(self) -> None:
        result = await _run()

        assert "Engagement 0" in result.message
        assert "Salut" in result.message
        assert "gerard@x.com" in result.message

    async def test_the_message_names_the_person(self) -> None:
        """The synthesizer must know WHO the block is about."""
        result = await _run()

        assert result.message.startswith("360 overview for Gérard Dupont")

    async def test_the_message_and_the_payload_never_diverge(self) -> None:
        """One source: the message IS the payload, not a second rendering.

        A hand-written summary alongside a structured payload is two truths
        about the same read, free to drift apart.
        """
        import json

        result = await _run()
        _, _, body = result.message.partition("\n")

        assert json.loads(body) == json.loads(json.dumps(result.structured_data, default=str))

    async def test_an_unreadable_section_stays_unreadable_in_the_message(self) -> None:
        """The ADR-190 distinction must survive serialisation.

        A block that could not be read carries NO key and is named in
        `unavailable`; an empty list means "looked, found nothing". Collapsing
        the two is how "I could not check" becomes "there is nothing".
        """
        import json

        context = _context(emails=_section(ContextStatus.NOT_CONFIGURED))
        result = await _run(context=context)
        body = json.loads(result.message.partition("\n")[2])

        assert "emails" not in body
        assert "emails" in body["unavailable"]

    async def test_an_empty_section_stays_an_empty_list(self) -> None:
        import json

        context = _context(emails=_section(ContextStatus.EMPTY))
        result = await _run(context=context)
        body = json.loads(result.message.partition("\n")[2])

        assert body["emails"] == []
        assert "emails" not in body["unavailable"]

    async def test_the_exact_totals_reach_the_assistant(self) -> None:
        """ADR-185: a count shown is a claim. It must survive the channel."""
        import json

        result = await _run()
        body = json.loads(result.message.partition("\n")[2])

        assert body["open_commitments_total"] == 8
        assert body["recent_calls_total"] == 1
