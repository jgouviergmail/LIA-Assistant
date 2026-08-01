"""PeersService behavioral tests — every lifecycle guard (Lot 1, Task 6).

The repository and user lookups are mocked (unit scope); the DB-semantics
tests live in tests/integration/domains/peers/. The load-bearing assertions
are the NEUTRALITY ones (a blocked/cooldown/unknown target must produce the
exact same error payload as a genuinely unknown user — spec §12.2) and the
CLAIM semantics (conditional transitions, single re-dispatch on lost races).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.peers.discovery import looks_like_email, mask_email
from src.domains.peers.models import PeerConnectionStatus, PeerShareDomain, PeerShareLevel
from src.domains.peers.service import PeersService

REQUESTER = uuid4()
ADDRESSEE = uuid4()


def _service() -> PeersService:
    """Service with a fully mocked repository and user lookup."""
    service = PeersService(db=AsyncMock())
    service.repo = AsyncMock()
    service.repo.has_block_between.return_value = False
    service.repo.get_pair.return_value = None
    service._get_discoverable_user = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(id=ADDRESSEE, full_name="Peer Beta", email="beta@test.local")
    )
    return service


def _pair_row(
    *,
    status: PeerConnectionStatus,
    requested_by=REQUESTER,
    responded_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        user_a_id=min(REQUESTER, ADDRESSEE),
        user_b_id=max(REQUESTER, ADDRESSEE),
        requested_by_id=requested_by,
        status=status.value,
        context_message=None,
        requested_at=datetime.now(UTC),
        responded_at=responded_at,
        removed_at=None,
    )


def _claiming_transition(row: SimpleNamespace):
    """Side effect honoring the conditional-claim contract of the repository."""

    async def _transition(connection_id, new_status, *, expected_from, now):
        if row.status not in expected_from:
            return None
        row.status = new_status.value
        if new_status in (PeerConnectionStatus.ACCEPTED, PeerConnectionStatus.DECLINED):
            row.responded_at = now
        elif new_status is PeerConnectionStatus.REMOVED:
            row.removed_at = now
        return row

    return _transition


def _error_payload(exc: BaseAPIException) -> tuple[int, object]:
    return (exc.status_code, exc.detail)


@pytest.mark.unit
class TestMaskEmail:
    """A6: masked fragment discriminates homonyms without leaking the address."""

    def test_standard_address(self):
        assert mask_email("jerome@gmail.com") == "j…@g….com"

    def test_short_parts_degrade_gracefully(self):
        assert mask_email("a@b.co") == "a…@b….co"

    def test_domain_without_dot(self):
        assert mask_email("x@localhost") == "x…@l…"


@pytest.mark.unit
class TestLooksLikeEmail:
    """The ONE authority deciding what kind of identity was typed.

    The search box takes a name OR an address; this predicate routes, and
    nothing else may re-decide (a second heuristic in the frontend would make
    the two layers disagree on the same string).
    """

    @pytest.mark.parametrize(
        "value",
        [
            "jean@example.com",
            "  Jean.Dupont@Gmail.COM  ",  # surrounding whitespace is not a name
            "admin@localhost",  # self-hosted: a dot is NOT required
            "jérôme@exemple.fr",
        ],
    )
    def test_addresses(self, value):
        assert looks_like_email(value) is True

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "   ",
            "Jean Dupont",
            "Jean Dupont <jean@x.com>",  # inner whitespace → a name, not an address
            "@lex",  # empty local part
            "jean@",  # empty domain
            "jean@@x.com",  # two separators
            "DJ @lex",
        ],
    )
    def test_not_addresses(self, value):
        assert looks_like_email(value) is False


@pytest.mark.unit
class TestDiscoverySearchByEmail:
    """Search by address: same guards as by name, a different comparison key.

    Bloc B. The address is folded conservatively and compared in PYTHON, on
    the very same scan the name search uses — never re-expressed as SQL
    ``lower()``, which would make the database a second authority on which
    mailbox is which.
    """

    @staticmethod
    def _stub_rows(service: PeersService, rows) -> None:
        result = MagicMock()
        result.all.return_value = rows
        service.db.execute.return_value = result

    async def test_finds_the_owner_of_the_address(self):
        service = _service()
        self._stub_rows(service, [(ADDRESSEE, "Peer Beta", "beta@test.local")])
        matches = await service.search_discoverable(REQUESTER, "beta@test.local")
        assert [(m.peer_id, m.display_name) for m in matches] == [(ADDRESSEE, "Peer Beta")]

    async def test_case_and_padding_are_not_a_difference(self):
        service = _service()
        self._stub_rows(service, [(ADDRESSEE, "Peer Beta", "Beta@Test.Local")])
        matches = await service.search_discoverable(REQUESTER, "  beta@test.local  ")
        assert len(matches) == 1

    async def test_an_address_never_matches_a_name(self):
        """Routing must be exclusive: the email branch reads emails only."""
        service = _service()
        self._stub_rows(service, [(ADDRESSEE, "beta@test.local", "other@test.local")])
        assert await service.search_discoverable(REQUESTER, "beta@test.local") == []

    async def test_a_name_never_matches_an_address(self):
        service = _service()
        self._stub_rows(service, [(ADDRESSEE, "Peer Beta", "beta@test.local")])
        assert await service.search_discoverable(REQUESTER, "Peer Gamma") == []

    async def test_a_near_miss_address_finds_nobody(self):
        """Exact match only — no prefix, no substring, no domain-wide sweep."""
        service = _service()
        self._stub_rows(service, [(ADDRESSEE, "Peer Beta", "beta@test.local")])
        assert await service.search_discoverable(REQUESTER, "bet@test.local") == []
        assert await service.search_discoverable(REQUESTER, "beta@test.loca") == []

    async def test_accents_are_not_folded_away_in_an_address(self):
        """The name fold would merge these two mailboxes; the address must not."""
        service = _service()
        self._stub_rows(service, [(ADDRESSEE, "Peer Beta", "jerome@test.local")])
        assert await service.search_discoverable(REQUESTER, "jérôme@test.local") == []

    async def test_a_blocked_owner_stays_invisible(self):
        service = _service()
        self._stub_rows(service, [(ADDRESSEE, "Peer Beta", "beta@test.local")])
        service.repo.has_block_between.return_value = True
        assert await service.search_discoverable(REQUESTER, "beta@test.local") == []
        service.repo.get_pair.assert_not_awaited()

    async def test_the_relationship_is_annotated_the_same_way(self):
        service = _service()
        self._stub_rows(service, [(ADDRESSEE, "Peer Beta", "beta@test.local")])
        service.repo.get_pair.return_value = _pair_row(status=PeerConnectionStatus.ACCEPTED)
        matches = await service.search_discoverable(REQUESTER, "beta@test.local")
        assert [m.relationship for m in matches] == ["connected"]

    async def test_the_masked_hint_is_still_returned(self):
        """One response shape for both branches — the searcher already knows
        the address they typed, so the hint neither adds nor leaks anything."""
        service = _service()
        self._stub_rows(service, [(ADDRESSEE, "Peer Beta", "beta@test.local")])
        (match,) = await service.search_discoverable(REQUESTER, "beta@test.local")
        assert match.email_hint == mask_email("beta@test.local")

    @pytest.mark.parametrize("blank_name", ["", "   "])
    async def test_a_blank_display_name_is_still_not_discoverable(self, blank_name):
        """`full_name` has no length validation, so "" and "   " are storable.

        The name branch is immune by accident (a blank query folds to "" and
        returns early); the address branch would otherwise answer with a row
        carrying no name at all — a nameless entry the UI cannot render and
        the spec says must not exist.
        """
        service = _service()
        self._stub_rows(service, [(ADDRESSEE, blank_name, "beta@test.local")])
        assert await service.search_discoverable(REQUESTER, "beta@test.local") == []

    async def test_two_mailboxes_differing_only_by_case_both_answer(self):
        """The column is UNIQUE on the raw string, so both rows CAN exist.

        Returning a list rather than one row is what keeps that truthful: the
        searcher sees both names instead of a silently arbitrary one.
        """
        other = uuid4()
        service = _service()
        self._stub_rows(
            service,
            [(ADDRESSEE, "Peer Beta", "Beta@test.local"), (other, "Beta Bis", "beta@test.local")],
        )
        matches = await service.search_discoverable(REQUESTER, "beta@test.local")
        assert {m.peer_id for m in matches} == {ADDRESSEE, other}


@pytest.mark.unit
class TestDiscoverySearchAnnotation:
    """Lot 7: search results carry the searcher's relationship to each match.

    DECLINED/REMOVED must read "none" — a declined request stays
    indistinguishable from no history (spec §12.2 neutrality doctrine).
    """

    @staticmethod
    def _stub_rows(service: PeersService) -> None:
        # AsyncMock children are async by default — `.all()` must stay sync.
        result = MagicMock()
        result.all.return_value = [(ADDRESSEE, "Peer Beta", "beta@test.local")]
        service.db.execute.return_value = result

    @pytest.mark.parametrize(
        ("pair_status", "expected"),
        [
            (None, "none"),
            (PeerConnectionStatus.PENDING, "pending"),
            (PeerConnectionStatus.ACCEPTED, "connected"),
            (PeerConnectionStatus.DECLINED, "none"),
            (PeerConnectionStatus.REMOVED, "none"),
        ],
    )
    async def test_relationship_annotation(self, pair_status, expected):
        service = _service()
        self._stub_rows(service)
        service.repo.get_pair.return_value = (
            None if pair_status is None else _pair_row(status=pair_status)
        )
        matches = await service.search_discoverable(REQUESTER, "Peer Beta")
        assert [m.relationship for m in matches] == [expected]

    async def test_blocked_match_stays_invisible_before_any_annotation(self):
        service = _service()
        self._stub_rows(service)
        service.repo.has_block_between.return_value = True
        assert await service.search_discoverable(REQUESTER, "Peer Beta") == []
        service.repo.get_pair.assert_not_awaited()


@pytest.mark.unit
class TestPeerEmailVisibility:
    """ADR-189: the address is shown only when its owner asked, and only to
    people they actually accepted.

    Being findable (`discovery_enabled`) and handing an address over are two
    different consents — one must never imply the other.
    """

    @staticmethod
    def _directory(service: PeersService, rows) -> None:
        result = MagicMock()
        result.all.return_value = rows
        service.db.execute.return_value = result

    @staticmethod
    def _accepted_pair():
        return SimpleNamespace(
            id=uuid4(),
            user_a_id=min(REQUESTER, ADDRESSEE),
            user_b_id=max(REQUESTER, ADDRESSEE),
            requested_by_id=REQUESTER,
            status=PeerConnectionStatus.ACCEPTED.value,
            context_message=None,
            requested_at=datetime.now(UTC),
            responded_at=datetime.now(UTC),
            removed_at=None,
        )

    async def test_an_accepted_connection_sees_an_address_its_owner_opened(self):
        service = _service()
        service.repo.list_accepted_for_user.return_value = [self._accepted_pair()]
        service.repo.list_shares.return_value = []
        self._directory(service, [(ADDRESSEE, "Peer Beta", "beta@test.local", True)])

        (view,) = await service.get_connections(REQUESTER)

        assert view.peer_email == "beta@test.local"
        assert view.peer_email_hint == mask_email("beta@test.local")  # the hint stays

    async def test_a_peer_who_did_not_opt_in_keeps_only_the_masked_hint(self):
        service = _service()
        service.repo.list_accepted_for_user.return_value = [self._accepted_pair()]
        service.repo.list_shares.return_value = []
        self._directory(service, [(ADDRESSEE, "Peer Beta", "beta@test.local", False)])

        (view,) = await service.get_connections(REQUESTER)

        assert view.peer_email is None
        assert view.peer_email_hint == mask_email("beta@test.local")

    async def test_a_pending_request_never_carries_the_address(self):
        """Not yet accepted is not connected: the opt-in cannot apply early."""
        service = _service()
        pending = _pair_row(status=PeerConnectionStatus.PENDING)
        service.repo.list_pending_for_user.return_value = [pending]
        self._directory(service, [(ADDRESSEE, "Peer Beta", "beta@test.local", True)])

        views = await service.get_pending(REQUESTER)

        assert all(view.peer_email is None for view in views)

    async def test_opening_an_address_never_makes_someone_discoverable(self):
        """Two consents, two columns: one must never imply the other."""
        service = _service()
        user = SimpleNamespace(id=REQUESTER, discovery_enabled=False, peer_email_visible=False)
        service.db.get = AsyncMock(return_value=user)

        await service.set_email_visibility(REQUESTER, True)

        assert user.peer_email_visible is True
        assert user.discovery_enabled is False

    async def test_becoming_discoverable_never_opens_an_address(self):
        service = _service()
        user = SimpleNamespace(id=REQUESTER, discovery_enabled=False, peer_email_visible=False)
        service.db.get = AsyncMock(return_value=user)

        await service.set_discovery(REQUESTER, True)

        assert user.discovery_enabled is True
        assert user.peer_email_visible is False


@pytest.mark.unit
class TestRequestGuards:
    """Guard order and neutrality of request_connection (spec §5.2, §12.2)."""

    async def test_self_request_rejected(self):
        service = _service()
        with pytest.raises(BaseAPIException) as exc:
            await service.request_connection(REQUESTER, REQUESTER, None)
        assert exc.value.status_code == 400

    async def test_context_message_too_long_rejected(self):
        from src.core.constants import PEERS_CONTEXT_MESSAGE_MAX_CHARS

        service = _service()
        with pytest.raises(BaseAPIException) as exc:
            await service.request_connection(
                REQUESTER, ADDRESSEE, "x" * (PEERS_CONTEXT_MESSAGE_MAX_CHARS + 1)
            )
        assert exc.value.status_code == 400

    async def test_blocked_pair_is_byte_identical_to_unknown_user(self):
        """The anti-harassment core: blocked == nonexistent, indistinguishable."""
        service_blocked = _service()
        service_blocked.repo.has_block_between.return_value = True
        with pytest.raises(BaseAPIException) as blocked_exc:
            await service_blocked.request_connection(REQUESTER, ADDRESSEE, None)

        service_unknown = _service()
        service_unknown._get_discoverable_user = AsyncMock(return_value=None)  # type: ignore[method-assign]
        with pytest.raises(BaseAPIException) as unknown_exc:
            await service_unknown.request_connection(REQUESTER, ADDRESSEE, None)

        assert _error_payload(blocked_exc.value) == _error_payload(unknown_exc.value)

    async def test_already_connected_rejected(self):
        service = _service()
        service.repo.get_pair.return_value = _pair_row(status=PeerConnectionStatus.ACCEPTED)
        with pytest.raises(BaseAPIException) as exc:
            await service.request_connection(REQUESTER, ADDRESSEE, None)
        assert exc.value.status_code == 400

    async def test_own_pending_request_is_idempotent(self):
        service = _service()
        pending = _pair_row(status=PeerConnectionStatus.PENDING, requested_by=REQUESTER)
        service.repo.get_pair.return_value = pending
        view = await service.request_connection(REQUESTER, ADDRESSEE, None)
        assert view.status == "pending"
        service.repo.insert_pair_request.assert_not_awaited()
        service.repo.revive_request.assert_not_awaited()
        assert service.pending_events == []

    async def test_plain_new_pair_creates_and_emits(self):
        service = _service()
        created = _pair_row(status=PeerConnectionStatus.PENDING, requested_by=REQUESTER)
        service.repo.insert_pair_request.return_value = created
        view = await service.request_connection(REQUESTER, ADDRESSEE, "salut")
        assert view.status == "pending"
        call = service.repo.insert_pair_request.await_args
        assert call.args == (REQUESTER, ADDRESSEE, "salut")
        assert call.kwargs["now"].tzinfo is not None  # tz-aware UTC contract
        assert [e.kind for e in service.pending_events] == ["request_created"]

    async def test_crossing_requests_auto_accept(self):
        """B requests A while A→B is pending: the pair becomes accepted."""
        service = _service()
        their_pending = _pair_row(status=PeerConnectionStatus.PENDING, requested_by=ADDRESSEE)
        service.repo.get_pair.return_value = their_pending
        service.repo.transition_status.side_effect = _claiming_transition(their_pending)
        view = await service.request_connection(REQUESTER, ADDRESSEE, None)
        assert view.status == "accepted"
        assert [e.kind for e in service.pending_events] == ["request_accepted"]

    async def test_insert_race_redispatches_once_into_auto_accept(self):
        """Two brand-new crossing requests at once: the loser of the pair
        UNIQUE re-dispatches and lands in the auto-accept branch, never a 500."""
        service = _service()
        service.db.rollback = AsyncMock()
        their_pending = _pair_row(status=PeerConnectionStatus.PENDING, requested_by=ADDRESSEE)
        # First pass: no row yet → INSERT loses the race. Second pass: their row.
        service.repo.get_pair.side_effect = [None, their_pending]
        service.repo.insert_pair_request.side_effect = IntegrityError("x", "y", Exception())
        service.repo.transition_status.side_effect = _claiming_transition(their_pending)

        view = await service.request_connection(REQUESTER, ADDRESSEE, None)

        assert view.status == "accepted"
        service.db.rollback.assert_awaited_once()
        assert [e.kind for e in service.pending_events] == ["request_accepted"]

    async def test_declined_within_cooldown_is_neutral_not_found(self):
        """Re-nagging a decliner inside the cooldown looks like a missing user."""
        service = _service()
        service.repo.get_pair.return_value = _pair_row(
            status=PeerConnectionStatus.DECLINED,
            requested_by=REQUESTER,
            responded_at=datetime.now(UTC)
            - timedelta(days=max(settings.peers_request_cooldown_days - 1, 0)),
        )
        with pytest.raises(BaseAPIException) as exc:
            await service.request_connection(REQUESTER, ADDRESSEE, None)

        service_unknown = _service()
        service_unknown._get_discoverable_user = AsyncMock(return_value=None)  # type: ignore[method-assign]
        with pytest.raises(BaseAPIException) as unknown_exc:
            await service_unknown.request_connection(REQUESTER, ADDRESSEE, None)
        assert _error_payload(exc.value) == _error_payload(unknown_exc.value)

    async def test_previous_decliner_is_exempt_from_cooldown(self):
        """The decliner changing their mind may re-request immediately."""
        service = _service()
        declined = _pair_row(
            status=PeerConnectionStatus.DECLINED,
            requested_by=ADDRESSEE,  # the OTHER side had requested; WE declined
            responded_at=datetime.now(UTC),
        )
        service.repo.get_pair.return_value = declined
        service.repo.revive_request.return_value = _pair_row(
            status=PeerConnectionStatus.PENDING, requested_by=REQUESTER
        )
        view = await service.request_connection(REQUESTER, ADDRESSEE, None)
        assert view.status == "pending"
        assert [e.kind for e in service.pending_events] == ["request_created"]


@pytest.mark.unit
class TestRespondGuards:
    """Only the addressee side of a pending request may respond."""

    async def test_requester_cannot_respond_to_own_request(self):
        service = _service()
        pending = _pair_row(status=PeerConnectionStatus.PENDING, requested_by=REQUESTER)
        service.repo.get_by_id = AsyncMock(return_value=pending)
        with pytest.raises(BaseAPIException) as exc:
            await service.respond_request(REQUESTER, pending.id, accept=True)
        assert exc.value.status_code == 403

    async def test_non_participant_gets_neutral_not_found(self):
        service = _service()
        pending = _pair_row(status=PeerConnectionStatus.PENDING, requested_by=REQUESTER)
        service.repo.get_by_id = AsyncMock(return_value=pending)
        outsider = uuid4()
        with pytest.raises(BaseAPIException) as exc:
            await service.respond_request(outsider, pending.id, accept=True)
        assert exc.value.status_code == 404

    async def test_accept_transitions_and_emits_event(self):
        service = _service()
        pending = _pair_row(status=PeerConnectionStatus.PENDING, requested_by=REQUESTER)
        service.repo.get_by_id = AsyncMock(return_value=pending)
        service.repo.transition_status.side_effect = _claiming_transition(pending)
        view = await service.respond_request(ADDRESSEE, pending.id, accept=True)
        assert view.status == "accepted"
        assert [e.kind for e in service.pending_events] == ["request_accepted"]

    async def test_decline_transitions_and_emits_event(self):
        service = _service()
        pending = _pair_row(status=PeerConnectionStatus.PENDING, requested_by=REQUESTER)
        service.repo.get_by_id = AsyncMock(return_value=pending)
        service.repo.transition_status.side_effect = _claiming_transition(pending)
        view = await service.respond_request(ADDRESSEE, pending.id, accept=False)
        assert view.status == "declined"
        assert [e.kind for e in service.pending_events] == ["request_declined"]

    async def test_lost_claim_answers_not_pending(self):
        """A concurrent responder claimed the row first → peers_not_pending."""
        service = _service()
        pending = _pair_row(status=PeerConnectionStatus.PENDING, requested_by=REQUESTER)
        service.repo.get_by_id = AsyncMock(return_value=pending)
        service.repo.transition_status.return_value = None
        with pytest.raises(BaseAPIException) as exc:
            await service.respond_request(ADDRESSEE, pending.id, accept=True)
        assert exc.value.detail == "peers_not_pending"
        assert service.pending_events == []


@pytest.mark.unit
class TestRemovalAndBlock:
    """Removal notifies both (event); blocking is silent and severs everything."""

    async def test_remove_deletes_shares_and_emits_event(self):
        service = _service()
        accepted = _pair_row(status=PeerConnectionStatus.ACCEPTED)
        service.repo.get_by_id = AsyncMock(return_value=accepted)
        service.repo.transition_status.side_effect = _claiming_transition(accepted)
        view = await service.remove_connection(REQUESTER, accepted.id)
        assert view.status == "removed"
        service.repo.delete_shares_for_connection.assert_awaited_once_with(accepted.id)
        assert [e.kind for e in service.pending_events] == ["connection_removed"]

    async def test_block_severs_connection_silently(self):
        """Block: connection removed, shares deleted, NO event (spec A2/§12.2)."""
        service = _service()
        accepted = _pair_row(status=PeerConnectionStatus.ACCEPTED)
        service.repo.get_pair.return_value = accepted
        service.repo.transition_status.side_effect = _claiming_transition(accepted)
        await service.block_peer(REQUESTER, ADDRESSEE)
        service.repo.create_block.assert_awaited_once_with(REQUESTER, ADDRESSEE)
        service.repo.delete_shares_for_connection.assert_awaited_once_with(accepted.id)
        assert service.pending_events == []

    async def test_block_self_rejected(self):
        service = _service()
        with pytest.raises(BaseAPIException) as exc:
            await service.block_peer(REQUESTER, REQUESTER)
        assert exc.value.status_code == 400


@pytest.mark.unit
class TestShareValidation:
    """v1 domain/level combinations only (spec A1)."""

    @pytest.mark.parametrize(
        ("domain", "level", "valid"),
        [
            (PeerShareDomain.CALENDAR, PeerShareLevel.AVAILABILITY, True),
            (PeerShareDomain.CALENDAR, PeerShareLevel.DETAILS, True),
            (PeerShareDomain.CALENDAR, PeerShareLevel.TITLES, False),
            (PeerShareDomain.TASK, PeerShareLevel.TITLES, True),
            (PeerShareDomain.TASK, PeerShareLevel.AVAILABILITY, False),
            (PeerShareDomain.TASK, PeerShareLevel.DETAILS, False),
        ],
    )
    async def test_domain_level_combinations(self, domain, level, valid):
        service = _service()
        accepted = _pair_row(status=PeerConnectionStatus.ACCEPTED)
        service.repo.get_by_id = AsyncMock(return_value=accepted)
        if valid:
            await service.set_share(REQUESTER, accepted.id, domain, level)
            service.repo.upsert_share.assert_awaited_once_with(
                accepted.id, REQUESTER, domain.value, level.value
            )
        else:
            with pytest.raises(BaseAPIException) as exc:
                await service.set_share(REQUESTER, accepted.id, domain, level)
            assert exc.value.status_code == 400

    async def test_none_level_deletes_the_share(self):
        service = _service()
        accepted = _pair_row(status=PeerConnectionStatus.ACCEPTED)
        service.repo.get_by_id = AsyncMock(return_value=accepted)
        await service.set_share(REQUESTER, accepted.id, PeerShareDomain.CALENDAR, None)
        service.repo.delete_share.assert_awaited_once_with(
            accepted.id, REQUESTER, PeerShareDomain.CALENDAR.value
        )

    async def test_share_on_pending_connection_rejected(self):
        service = _service()
        pending = _pair_row(status=PeerConnectionStatus.PENDING)
        service.repo.get_by_id = AsyncMock(return_value=pending)
        with pytest.raises(BaseAPIException) as exc:
            await service.set_share(
                REQUESTER, pending.id, PeerShareDomain.CALENDAR, PeerShareLevel.AVAILABILITY
            )
        assert exc.value.status_code == 400
