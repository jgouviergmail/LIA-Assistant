"""RelationsService (N-09) — aggregation, identity resolution, honesty.

What must hold:
- open loops, calls and relayed peer messages fold into ONE relationship when
  their names match after accent/case folding, and the confidence reflects
  whether the raw spellings agreed (EXACT) or only folded (NORMALIZED);
- the overview ranks by most-recent interaction, honors the cap, and its
  counts are EXACT — they come from database aggregates over the whole set,
  never from the length of a page (a count the card shows is a claim);
- the 360° view queries each source FOR THIS PERSON, by the exact spellings
  the aggregates reported, so folding stays the sole business of `fold_name`
  and SQL never gets a second opinion on identity;
- every section states its exact total next to its page, so a cap is stated
  rather than silently applied;
- blank counterparties/callees are dropped, never a phantom relationship.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.peers.schemas import PeerConnectionProfile
from src.domains.relations.overview_scope import OverviewSection, RelationOverviewScope
from src.domains.relations.peer_messages import PeerMessagePage
from src.domains.relations.schemas import IdentityConfidence
from src.domains.relations.service import RelationsService, _normalize_name
from src.domains.shared.aggregates import NameActivity

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)

_EMPTY_PAGE = PeerMessagePage(signals=[], total=0)


@pytest.fixture(autouse=True)
def _peers_bridge_silent_by_default():
    """The peers bridge owns its own session — never let it reach a real one.

    Tests that assert on relayed messages opt in via the explicit patches
    (an inner patch wins over this one).
    """
    with (
        patch(
            "src.domains.relations.service.fetch_peer_messages_for",
            new=AsyncMock(return_value=_EMPTY_PAGE),
        ),
        patch(
            "src.domains.relations.service.fetch_peer_message_activity",
            new=AsyncMock(return_value=[]),
        ),
    ):
        yield


def _activity(name: str, *, count: int = 1, days_ago: int = 0) -> NameActivity:
    """One source aggregate row: a raw spelling, its exact count, its recency."""
    return NameActivity(raw_name=name, count=count, last_at=NOW - timedelta(days=days_ago))


def _loop(counterparty, subject="dossier", *, days_ago=1, direction="user_owes"):
    return SimpleNamespace(
        id=uuid4(),
        counterparty=counterparty,
        subject=subject,
        direction=direction,
        due_hint=None,
        created_at=NOW - timedelta(days=days_ago),
    )


def _call(callee, objective="réserver", *, days_ago=0, outcome=None, summary=None):
    return SimpleNamespace(
        id=uuid4(),
        callee_display=callee,
        objective=objective,
        outcome=outcome,
        summary=summary,
        created_at=NOW - timedelta(days=days_ago),
    )


def _memory(content):
    return SimpleNamespace(id=uuid4(), content=content)


def _patch_sources(
    *,
    loop_activity=(),
    call_activity=(),
    loops=(),
    calls=(),
    memories=(),
    memories_total=None,
):
    """Patch the three repositories the service reads through.

    Each exposes BOTH halves of its contract: the aggregate the overview
    counts from, and the per-person page the 360° view lists.
    """
    return (
        patch(
            "src.domains.relations.service.OpenLoopRepository",
            return_value=SimpleNamespace(
                aggregate_open_by_counterparty=AsyncMock(return_value=list(loop_activity)),
                list_open_for_counterparties=AsyncMock(return_value=list(loops)),
            ),
        ),
        patch(
            "src.domains.relations.service.TelephonyRepository",
            return_value=SimpleNamespace(
                aggregate_calls_by_callee=AsyncMock(return_value=list(call_activity)),
                list_calls_for_callees=AsyncMock(return_value=list(calls)),
            ),
        ),
        patch(
            "src.domains.memories.repository.MemoryRepository",
            return_value=SimpleNamespace(
                list_mentioning_name=AsyncMock(
                    return_value=(
                        list(memories),
                        len(memories) if memories_total is None else memories_total,
                    )
                )
            ),
        ),
    )


def _patch_db():
    import contextlib

    @contextlib.asynccontextmanager
    async def _ctx():
        yield SimpleNamespace()

    return patch("src.domains.relations.service.get_db_context", _ctx)


def _favorite(name, key=None):
    return SimpleNamespace(
        name_key=key if key is not None else _normalize_name(name),
        display_name=name,
    )


def _patch_aliases(pairs=()):
    """Patch the merge table — empty means "no relationship was merged".

    Added when manual merges landed: the service resolves identity through
    this table on EVERY read, so a suite that does not stub it is asserting
    on a code path the product no longer has.
    """
    return patch(
        "src.domains.relations.service.RelationAliasRepository",
        return_value=SimpleNamespace(
            list_for_user=AsyncMock(
                return_value=[
                    SimpleNamespace(
                        alias_key=alias, canonical_key=canonical, alias_display_name=alias
                    )
                    for alias, canonical in pairs
                ]
            ),
            merge=AsyncMock(),
            split=AsyncMock(return_value=True),
        ),
    )


def _patch_favorites(favorites=()):
    return patch(
        "src.domains.relations.service.RelationFavoriteRepository",
        return_value=SimpleNamespace(
            list_for_user=AsyncMock(return_value=list(favorites)),
            add=AsyncMock(),
            remove=AsyncMock(return_value=True),
        ),
    )


#: Deterministic peer id, so a share owned by "them" is recognizable.
PEER_ID = uuid4()
ME_ID = uuid4()


def _share(owner_id, domain="calendar", level="availability"):
    return SimpleNamespace(owner_user_id=owner_id, domain=domain, level=level)


def _patch_peers(peer_names=(), enabled=True, shares=(), connected_since=None):
    """Patch the peers bridge: ONE read feeds both the badge and the block."""
    profiles = [
        PeerConnectionProfile(
            connection_id=uuid4(),
            peer_id=PEER_ID,
            peer_display_name=name,
            connected_since=connected_since,
        )
        for name in peer_names
    ]
    peers_patch = patch(
        "src.domains.relations.service.PeersRepository",
        return_value=SimpleNamespace(
            list_accepted_peer_profiles=AsyncMock(return_value=profiles),
            list_shares=AsyncMock(return_value=list(shares)),
        ),
    )
    flag_patch = patch.object(
        __import__("src.domains.relations.service", fromlist=["settings"]).settings,
        "peers_enabled",
        enabled,
    )
    return peers_patch, flag_patch


def _peer_signal(
    name="Marie Dupont", *, direction="received", content="Salut !", days_ago=0, key=None
):
    from src.domains.relations.peer_messages import PeerMessageSignal

    return PeerMessageSignal(
        message_id=str(uuid4()),
        name_key=key if key is not None else _normalize_name(name),
        peer_display_name=name,
        direction=direction,
        content=content,
        occurred_at=NOW - timedelta(days=days_ago),
    )


def _patch_peer_messages(signals=(), activity=None, total=None):
    """Patch the peers bridge — it owns its own session and failure boundary.

    The detail entry point returns the page AND its total together: they come
    from ONE read precisely so a section can never announce a count its own
    rows contradict.
    """
    from src.domains.relations.peer_messages import PeerMessagePage

    resolved = (
        list(activity)
        if activity is not None
        else [
            NameActivity(
                raw_name=signal.peer_display_name,
                count=1,
                last_at=signal.occurred_at,
            )
            for signal in signals
        ]
    )
    page = PeerMessagePage(signals=list(signals), total=len(signals) if total is None else total)
    return (
        patch(
            "src.domains.relations.service.fetch_peer_messages_for",
            new=AsyncMock(return_value=page),
        ),
        patch(
            "src.domains.relations.service.fetch_peer_message_activity",
            new=AsyncMock(return_value=resolved),
        ),
    )


@pytest.mark.unit
def test_normalize_name_folds_accents_and_case() -> None:
    assert _normalize_name("Gérard") == _normalize_name("gerard")
    assert _normalize_name("  Marie  ") == "marie"
    assert _normalize_name("") == ""


@pytest.mark.unit
class TestOverview:
    """The list of people, ranked, capped, and counted exactly."""

    async def test_folds_matching_spellings_into_one_relationship(self) -> None:
        service = RelationsService(uuid4())
        p_loop, p_call, p_mem = _patch_sources(
            loop_activity=[_activity("Gérard Dupont", days_ago=3)],
            call_activity=[_activity("gerard dupont", days_ago=1)],
        )
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            _patch_peers()[0],
        ):
            overview = await service.build_overview()

        (relation,) = overview.relations
        assert relation.open_loops_count == 1
        assert relation.calls_count == 1
        # Raw spellings differ ⇒ NORMALIZED, and the richest spelling shows.
        assert relation.identity_confidence is IdentityConfidence.NORMALIZED
        assert relation.display_name == "Gérard Dupont"
        assert relation.last_interaction_at == NOW - timedelta(days=1)

    async def test_counts_are_exact_not_a_page_length(self) -> None:
        """The regression this replaced: counting rows from a capped window
        under-reported as soon as someone had more than the window held."""
        service = RelationsService(uuid4())
        p_loop, p_call, p_mem = _patch_sources(
            loop_activity=[_activity("Marie Dupont", count=137)],
            call_activity=[_activity("Marie Dupont", count=42)],
        )
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            _patch_peers()[0],
        ):
            overview = await service.build_overview()

        (relation,) = overview.relations
        assert relation.open_loops_count == 137
        assert relation.calls_count == 42

    async def test_counts_sum_across_spellings_of_one_person(self) -> None:
        service = RelationsService(uuid4())
        p_loop, p_call, p_mem = _patch_sources(
            loop_activity=[_activity("Gérard", count=2), _activity("gerard", count=3)],
        )
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            _patch_peers()[0],
        ):
            overview = await service.build_overview()

        (relation,) = overview.relations
        assert relation.open_loops_count == 5

    async def test_ranks_by_recent_interaction_and_caps(self) -> None:
        service = RelationsService(uuid4())
        p_loop, p_call, p_mem = _patch_sources(
            loop_activity=[_activity("Alice", days_ago=10), _activity("Bob", days_ago=1)],
        )
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            _patch_peers()[0],
            patch("src.domains.relations.service.settings") as cfg,
        ):
            cfg.relations_max_items = 1
            cfg.relations_max_items_per_section = 25
            overview = await service.build_overview()

        assert [r.display_name for r in overview.relations] == ["Bob"]

    async def test_the_capped_page_still_states_how_many_relationships_exist(self) -> None:
        """ADR-185 applies to the LIST itself, not only to its sections.

        Truncating to the cap without saying so is the very failure the exact
        counts exist to kill: past the cap, people vanish from the CRM with no
        sign that anything was left out.
        """
        service = RelationsService(uuid4())
        p_loop, p_call, p_mem = _patch_sources(
            loop_activity=[_activity(f"Person {index}", days_ago=index) for index in range(7)],
        )
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            _patch_peers()[0],
            patch("src.domains.relations.service.settings") as cfg,
        ):
            cfg.relations_max_items = 3
            cfg.relations_max_items_per_section = 25
            overview = await service.build_overview()

        assert len(overview.relations) == 3
        assert overview.relations_total == 7

    async def test_ties_are_ordered_by_name_not_backwards(self) -> None:
        """Starred-but-quiet relationships all tie on "no interaction ever".

        A single reverse sort ordered those Z→A, which reads as random to the
        one user who sees it — the person with several dormant favorites.
        """
        service = RelationsService(uuid4())
        p_loop, p_call, p_mem = _patch_sources()
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites([_favorite("Carla"), _favorite("Bruno"), _favorite("Alice")]),
            _patch_aliases(),
            _patch_peers()[0],
        ):
            overview = await service.build_overview()

        assert [r.display_name for r in overview.relations] == ["Alice", "Bruno", "Carla"]

    async def test_drops_blank_names(self) -> None:
        service = RelationsService(uuid4())
        p_loop, p_call, p_mem = _patch_sources(
            loop_activity=[_activity("   ")], call_activity=[_activity("")]
        )
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            _patch_peers()[0],
        ):
            overview = await service.build_overview()
        assert overview.relations == []


@pytest.mark.unit
class TestFavoritesInOverview:
    """CRM favorites: starred people lead the list and survive signal expiry."""

    async def test_marks_favorites_and_ranks_them_first(self) -> None:
        service = RelationsService(user_id=uuid4())
        p_loop, p_call, p_mem = _patch_sources(
            loop_activity=[_activity("Marie Dupont", days_ago=9)],
            call_activity=[_activity("Paul Martin", days_ago=0)],
        )
        p_peers, p_flag = _patch_peers()
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites([_favorite("Marie Dupont")]),
            _patch_aliases(),
            p_peers,
            p_flag,
        ):
            overview = await service.build_overview()
        assert [r.display_name for r in overview.relations] == ["Marie Dupont", "Paul Martin"]
        assert [r.is_favorite for r in overview.relations] == [True, False]

    async def test_starred_relation_survives_without_live_signals(self) -> None:
        service = RelationsService(user_id=uuid4())
        p_loop, p_call, p_mem = _patch_sources(call_activity=[_activity("Paul Martin")])
        p_peers, p_flag = _patch_peers()
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites([_favorite("Mémé Jeanne")]),
            _patch_aliases(),
            p_peers,
            p_flag,
        ):
            overview = await service.build_overview()
        starred = next(r for r in overview.relations if r.is_favorite)
        assert starred.display_name == "Mémé Jeanne"
        assert starred.open_loops_count == 0 and starred.calls_count == 0
        assert starred.last_interaction_at is None

    async def test_favorite_survives_the_cap(self) -> None:
        service = RelationsService(user_id=uuid4())
        p_loop, p_call, p_mem = _patch_sources(
            call_activity=[_activity("Paul Martin", days_ago=0), _activity("Ana Lima", days_ago=1)]
        )
        p_peers, p_flag = _patch_peers()
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites([_favorite("Ana Lima")]),
            _patch_aliases(),
            p_peers,
            p_flag,
            patch("src.domains.relations.service.settings") as cfg,
        ):
            cfg.relations_max_items = 1
            cfg.peers_enabled = True
            overview = await service.build_overview()
        assert [r.display_name for r in overview.relations] == ["Ana Lima"]

    async def test_peer_badge_set_from_accepted_connections(self) -> None:
        service = RelationsService(user_id=uuid4())
        p_loop, p_call, p_mem = _patch_sources(
            call_activity=[_activity("Marie Dupont"), _activity("Paul Martin")]
        )
        p_peers, p_flag = _patch_peers(peer_names=["marie dupont"])
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            p_peers,
            p_flag,
        ):
            overview = await service.build_overview()
        flags = {r.display_name: r.is_peer for r in overview.relations}
        assert flags == {"Marie Dupont": True, "Paul Martin": False}

    async def test_peer_badge_silent_when_flag_off(self) -> None:
        service = RelationsService(user_id=uuid4())
        p_loop, p_call, p_mem = _patch_sources(call_activity=[_activity("Marie Dupont")])
        p_peers, p_flag = _patch_peers(peer_names=["marie dupont"], enabled=False)
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            p_peers,
            p_flag,
        ):
            overview = await service.build_overview()
        assert overview.relations[0].is_peer is False

    async def test_add_and_remove_favorite_fold_the_name(self) -> None:
        service = RelationsService(user_id=uuid4())
        repo = SimpleNamespace(add=AsyncMock(), remove=AsyncMock(return_value=True))
        with (
            _patch_db(),
            patch("src.domains.relations.service.RelationFavoriteRepository", return_value=repo),
        ):
            await service.add_favorite("  Mémé Jeanne ")
            await service.remove_favorite("MÉMÉ jeanne")
        repo.add.assert_awaited_once_with(
            service.user_id, name_key="meme jeanne", display_name="Mémé Jeanne"
        )
        repo.remove.assert_awaited_once_with(service.user_id, name_key="meme jeanne")


@pytest.mark.unit
class TestDetail:
    """The 360° view: queried per person, capped explicitly, counted exactly."""

    async def test_gathers_loops_calls_and_memories(self) -> None:
        service = RelationsService(uuid4())
        p_loop, p_call, p_mem = _patch_sources(
            loop_activity=[_activity("Gérard")],
            call_activity=[_activity("gérard")],
            loops=[_loop("Gérard", subject="prêt perceuse")],
            calls=[_call("gérard", objective="anniversaire")],
            memories=[_memory("Gérard adore la randonnée")],
        )
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            _patch_peers()[0],
        ):
            detail = await service.build_detail("Gérard")

        assert [loop.subject for loop in detail.open_loops] == ["prêt perceuse"]
        assert [call.objective for call in detail.recent_calls] == ["anniversaire"]
        assert "randonnée" in detail.memories[0].content

    async def test_queries_every_stored_spelling_of_the_person(self) -> None:
        """SQL matches EXACT strings; the spellings come from the aggregates,
        folded in Python — so identity has exactly one implementation."""
        service = RelationsService(uuid4())
        loop_repo = SimpleNamespace(
            aggregate_open_by_counterparty=AsyncMock(
                return_value=[_activity("Gérard Dupont"), _activity("gerard dupont")]
            ),
            list_open_for_counterparties=AsyncMock(return_value=[]),
        )
        _p_loop, p_call, p_mem = _patch_sources()
        with (
            _patch_db(),
            patch("src.domains.relations.service.OpenLoopRepository", return_value=loop_repo),
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            _patch_peers()[0],
        ):
            await service.build_detail("GERARD DUPONT")

        spellings = loop_repo.list_open_for_counterparties.await_args.args[1]
        assert sorted(spellings) == ["Gérard Dupont", "gerard dupont"]

    async def test_totals_are_exact_even_when_the_page_is_capped(self) -> None:
        """The silent-cap defect: the panel showed ten items and said nothing
        about the rest. Each section now carries what it left out."""
        service = RelationsService(uuid4())
        p_loop, p_call, p_mem = _patch_sources(
            loop_activity=[_activity("Marie", count=137)],
            call_activity=[_activity("Marie", count=9)],
            loops=[_loop("Marie") for _ in range(3)],
            calls=[_call("Marie")],
            memories=[_memory("Marie aime la voile")],
            memories_total=54,
        )
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            _patch_peers()[0],
        ):
            detail = await service.build_detail("Marie")

        assert len(detail.open_loops) == 3 and detail.open_loops_total == 137
        assert len(detail.recent_calls) == 1 and detail.recent_calls_total == 9
        assert len(detail.memories) == 1 and detail.memories_total == 54

    async def test_unknown_person_answers_empty_without_inventing_a_name(self) -> None:
        service = RelationsService(uuid4())
        p_loop, p_call, p_mem = _patch_sources()
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            _patch_peers()[0],
        ):
            detail = await service.build_detail("  Personne Inconnue  ")

        assert detail.display_name == "Personne Inconnue"
        assert detail.open_loops == [] and detail.open_loops_total == 0
        assert detail.memories_total == 0

    async def test_carries_favorite_and_peer_flags(self) -> None:
        service = RelationsService(user_id=uuid4())
        p_loop, p_call, p_mem = _patch_sources(call_activity=[_activity("Marie Dupont")])
        p_peers, p_flag = _patch_peers(peer_names=["marie dupont"])
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites([_favorite("Marie Dupont")]),
            _patch_aliases(),
            p_peers,
            p_flag,
        ):
            detail = await service.build_detail("marie dupont")
        assert detail.is_favorite is True
        assert detail.is_peer is True


@pytest.mark.unit
class TestPeerMessagesInTheCrm:
    """Relayed messages are a first-class CRM signal (peers spec §11, D2).

    They also close a gap the badge alone left open: before this, a connected
    peer with no open loop and no phone call had NO card at all, so `is_peer`
    had nobody to decorate.
    """

    async def test_a_relayed_message_alone_creates_the_relationship(self) -> None:
        service = RelationsService(user_id=uuid4())
        p_loop, p_call, p_mem = _patch_sources()
        p_peers, p_flag = _patch_peers(peer_names=["marie dupont"])
        p_signals, p_activity = _patch_peer_messages([_peer_signal("Marie Dupont")])
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            p_peers,
            p_flag,
            p_signals,
            p_activity,
        ):
            overview = await service.build_overview()

        (relation,) = overview.relations
        assert relation.display_name == "Marie Dupont"
        assert relation.peer_messages_count == 1
        assert relation.open_loops_count == 0 and relation.calls_count == 0
        assert relation.is_peer is True

    async def test_both_directions_count_and_the_latest_dates_the_relationship(self) -> None:
        service = RelationsService(user_id=uuid4())
        p_loop, p_call, p_mem = _patch_sources(
            loop_activity=[_activity("Marie Dupont", days_ago=9)]
        )
        p_peers, p_flag = _patch_peers()
        p_signals, p_activity = _patch_peer_messages(
            [
                _peer_signal("Marie Dupont", direction="received", days_ago=1),
                _peer_signal("Marie Dupont", direction="sent", days_ago=3),
            ],
            activity=[_activity("Marie Dupont", count=2, days_ago=1)],
        )
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            p_peers,
            p_flag,
            p_signals,
            p_activity,
        ):
            overview = await service.build_overview()

        (relation,) = overview.relations
        assert relation.peer_messages_count == 2
        # A message IS an interaction: it outranks the 9-day-old open loop.
        assert relation.last_interaction_at == NOW - timedelta(days=1)

    async def test_messages_fold_into_an_existing_relationship(self) -> None:
        """The peer's stored name is evidence like any other spelling: it
        merges with the loop's, and the disagreement is stated, not hidden."""
        service = RelationsService(user_id=uuid4())
        p_loop, p_call, p_mem = _patch_sources(loop_activity=[_activity("Gérard Dupont")])
        p_peers, p_flag = _patch_peers()
        p_signals, p_activity = _patch_peer_messages([_peer_signal("gerard dupont")])
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            p_peers,
            p_flag,
            p_signals,
            p_activity,
        ):
            overview = await service.build_overview()

        (relation,) = overview.relations
        assert relation.open_loops_count == 1 and relation.peer_messages_count == 1
        assert relation.identity_confidence is IdentityConfidence.NORMALIZED
        assert relation.display_name == "Gérard Dupont"  # richest spelling wins

    async def test_blank_peer_name_never_creates_a_phantom(self) -> None:
        service = RelationsService(user_id=uuid4())
        p_loop, p_call, p_mem = _patch_sources()
        p_peers, p_flag = _patch_peers()
        p_signals, p_activity = _patch_peer_messages(
            [_peer_signal("", key="")], activity=[_activity("   ")]
        )
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            p_peers,
            p_flag,
            p_signals,
            p_activity,
        ):
            overview = await service.build_overview()
        assert overview.relations == []

    async def test_detail_renders_the_page_the_bridge_narrowed(self) -> None:
        """The bridge narrows to this person IN SQL and returns the total from
        the same read — the panel renders both, it does not re-filter."""
        service = RelationsService(user_id=uuid4())
        p_loop, p_call, p_mem = _patch_sources()
        p_peers, p_flag = _patch_peers()
        recent = _peer_signal("Marie Dupont", content="Coucou", days_ago=0)
        older = _peer_signal("Marie Dupont", direction="sent", content=None, days_ago=5)
        p_signals, p_activity = _patch_peer_messages([recent, older], total=37)
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            p_peers,
            p_flag,
            p_signals,
            p_activity,
        ):
            detail = await service.build_detail("marie dupont")

        assert [item.id for item in detail.peer_messages] == [
            recent.message_id,
            older.message_id,
        ]
        # The total is the bridge's, not the page length: a capped page must
        # never be mistaken for the whole exchange.
        assert detail.peer_messages_total == 37
        assert detail.peer_messages[0].content == "Coucou"
        # A sent message keeps its date and states plainly that it has no text.
        assert detail.peer_messages[1].direction == "sent"
        assert detail.peer_messages[1].content is None

    async def test_detail_of_a_message_only_peer_names_them_from_the_ledger(self) -> None:
        """No loop, no call: the ledger's spelling is the only evidence, and
        it must beat the raw query string the user clicked."""
        service = RelationsService(user_id=uuid4())
        p_loop, p_call, p_mem = _patch_sources()
        p_peers, p_flag = _patch_peers()
        p_signals, p_activity = _patch_peer_messages([_peer_signal("Marie Dupont")])
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            p_peers,
            p_flag,
            p_signals,
            p_activity,
        ):
            detail = await service.build_detail("marie dupont")
        assert detail.display_name == "Marie Dupont"
        assert detail.identity_confidence is IdentityConfidence.EXACT


@pytest.mark.unit
class TestPeerConnectionBlock:
    """The connection block the peers spec §11 reserved and never shipped.

    Both directions are stated: a one-sided view of a two-sided arrangement
    is misleading, and the CRM is read-only — sharing is granted and revoked
    in the Connections settings, never here.
    """

    async def test_states_since_when_and_both_share_directions(self) -> None:
        service = RelationsService(user_id=ME_ID)
        since = NOW - timedelta(days=30)
        p_loop, p_call, p_mem = _patch_sources(call_activity=[_activity("Marie Dupont")])
        p_peers, p_flag = _patch_peers(
            peer_names=["Marie Dupont"],
            connected_since=since,
            shares=[
                _share(ME_ID, "calendar", "availability"),
                _share(PEER_ID, "task", "titles"),
            ],
        )
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            p_peers,
            p_flag,
        ):
            detail = await service.build_detail("marie dupont")

        assert detail.peer_link is not None
        assert detail.peer_link.connected_since == since
        assert [(s.domain, s.level) for s in detail.peer_link.shared_by_me] == [
            ("calendar", "availability")
        ]
        assert [(s.domain, s.level) for s in detail.peer_link.shared_with_me] == [
            ("task", "titles")
        ]

    async def test_absent_for_someone_who_is_not_a_connection(self) -> None:
        service = RelationsService(user_id=ME_ID)
        p_loop, p_call, p_mem = _patch_sources(call_activity=[_activity("Paul Martin")])
        p_peers, p_flag = _patch_peers(peer_names=["Marie Dupont"])
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            p_peers,
            p_flag,
        ):
            detail = await service.build_detail("paul martin")

        assert detail.peer_link is None
        assert detail.is_peer is False

    async def test_absent_when_the_feature_is_off(self) -> None:
        service = RelationsService(user_id=ME_ID)
        p_loop, p_call, p_mem = _patch_sources(call_activity=[_activity("Marie Dupont")])
        p_peers, p_flag = _patch_peers(peer_names=["Marie Dupont"], enabled=False)
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            p_peers,
            p_flag,
        ):
            detail = await service.build_detail("marie dupont")
        assert detail.peer_link is None

    async def test_a_connection_that_shares_nothing_still_has_a_block(self) -> None:
        """Connected with no sharing is a real, sayable state — the panel must
        be able to say "nothing shared" rather than hide the connection."""
        service = RelationsService(user_id=ME_ID)
        p_loop, p_call, p_mem = _patch_sources(call_activity=[_activity("Marie Dupont")])
        p_peers, p_flag = _patch_peers(peer_names=["Marie Dupont"], shares=[])
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            p_peers,
            p_flag,
        ):
            detail = await service.build_detail("marie dupont")

        assert detail.peer_link is not None
        assert detail.peer_link.shared_by_me == []
        assert detail.peer_link.shared_with_me == []

    async def test_matches_the_connection_through_folding(self) -> None:
        service = RelationsService(user_id=ME_ID)
        p_loop, p_call, p_mem = _patch_sources(call_activity=[_activity("gerard dupont")])
        p_peers, p_flag = _patch_peers(peer_names=["Gérard Dupont"])
        with (
            _patch_db(),
            p_loop,
            p_call,
            p_mem,
            _patch_favorites(),
            _patch_aliases(),
            p_peers,
            p_flag,
        ):
            detail = await service.build_detail("GÉRARD DUPONT")
        assert detail.peer_link is not None
        assert detail.is_peer is True


@pytest.mark.unit
class TestOverviewScopePersistence:
    """The scope is stored so the 360° tool can READ it, not merely remember it.

    Two failure modes this closes: a JSONB column mutated in place (SQLAlchemy
    silently skips the UPDATE, so the selection never leaves the browser), and
    a legacy shape reaching the tool as a half-scope.
    """

    def _patch_user(self, user):
        import contextlib

        db = SimpleNamespace(get=AsyncMock(return_value=user), commit=AsyncMock())

        @contextlib.asynccontextmanager
        async def _ctx():
            yield db

        return patch("src.domains.relations.service.get_db_context", _ctx), db

    async def test_never_saved_reads_as_the_defaults(self) -> None:
        user = SimpleNamespace(relation_overview_scope=None)
        patcher, _ = self._patch_user(user)
        with patcher:
            scope = await RelationsService(user_id=uuid4()).get_overview_scope()
        assert scope == RelationOverviewScope.default()

    async def test_reads_back_exactly_what_was_stored(self) -> None:
        stored = RelationOverviewScope(sections=[OverviewSection.EMAILS], max_items=2)
        user = SimpleNamespace(relation_overview_scope=stored.model_dump(mode="json"))
        patcher, _ = self._patch_user(user)
        with patcher:
            scope = await RelationsService(user_id=uuid4()).get_overview_scope()
        assert scope == stored

    async def test_writes_a_NEW_dict_and_commits(self) -> None:
        """A JSONB column mutated in place is an UPDATE SQLAlchemy skips —
        the write would look successful and change nothing."""
        original = {"sections": ["calls"], "max_items": 9}
        user = SimpleNamespace(relation_overview_scope=original)
        patcher, db = self._patch_user(user)
        payload = RelationOverviewScope(sections=[OverviewSection.CONTACT], max_items=3)
        with patcher:
            await RelationsService(user_id=uuid4()).set_overview_scope(payload)
        assert user.relation_overview_scope is not original
        assert user.relation_overview_scope["sections"] == ["contact"]
        db.commit.assert_awaited_once()

    async def test_a_json_safe_payload_is_stored(self) -> None:
        """Enums must reach the column as their VALUES: a stored ``<enum ...>``
        repr is a scope no later read can parse."""
        user = SimpleNamespace(relation_overview_scope=None)
        patcher, _ = self._patch_user(user)
        with patcher:
            await RelationsService(user_id=uuid4()).set_overview_scope(
                RelationOverviewScope.default()
            )
        stored = user.relation_overview_scope
        assert all(isinstance(section, str) for section in stored["sections"])
        assert RelationOverviewScope.from_stored(stored) == RelationOverviewScope.default()

    async def test_a_vanished_user_is_a_no_op_not_a_crash(self) -> None:
        patcher, db = self._patch_user(None)
        with patcher:
            await RelationsService(user_id=uuid4()).set_overview_scope(
                RelationOverviewScope.default()
            )
        db.commit.assert_not_awaited()
