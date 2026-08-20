"""The capability map — what it offers, what it hides, and what it refuses to say.

The starter checklist probes seven capabilities client-side, through seven
hooks. A living map of everything LIA can do would fire a dozen requests at
mount and give a dozen chances for one answer to disagree with another about
whether voice is on. This resolves them in ONE pass, server-side.

Three properties are load-bearing:

- a subsystem the INSTANCE disabled is absent from the payload, never a greyed
  node (gate-keeper, ADR-061): a control the product cannot honour is worse
  than an absent one;
- a probe that fails degrades to "not ready" — a map that refuses to draw
  because one table was unreachable is worse than a map with one dim node;
- nothing published is a level, a percentage of completion or a comparison.
  "Three connectors linked" is a fact; "62 % complete" invites a competition
  nobody asked to enter.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.capabilities.router import get_capability_map
from src.domains.capabilities.service import (
    COUNTED_NODES,
    MAP_NODE_KEYS,
    SWITCH_NODE_KEYS,
    CapabilityProbe,
    _counted,
    _from_user,
)
from src.domains.feature_switches.registry import PlatformCapability

pytestmark = pytest.mark.unit


def _user(**over: object) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.voice_enabled = False
    user.voice_mode_enabled = False
    user.heartbeat_enabled = False
    user.personality_id = None
    user.image_generation_enabled = False
    for key, value in over.items():
        setattr(user, key, value)
    return user


def _switches(
    user: MagicMock, disabled: frozenset[PlatformCapability] = frozenset()
) -> dict[str, CapabilityProbe]:
    """The switch-shaped probes, keyed — the shape every caller here asserts on."""
    return {probe.key: probe for probe in _from_user(user, disabled)}


def _never() -> Any:
    raise AssertionError("an unavailable capability must not be queried at all")


async def _map(probes: list[CapabilityProbe]):
    with patch(
        "src.domains.capabilities.router.resolve_capabilities",
        AsyncMock(return_value=probes),
    ):
        return await get_capability_map(user=_user())


class TestWhatTheMapPublishes:
    async def test_a_capability_the_instance_disabled_is_absent(self) -> None:
        """Gate-keeper: absent, never greyed out."""
        result = await _map(
            [
                CapabilityProbe("memory", available=True, active=True, detail=12),
                CapabilityProbe("spaces", available=False, active=False),
            ]
        )

        assert [node.key for node in result.nodes] == ["memory"]
        assert result.total == 1

    async def test_the_counts_describe_the_offered_nodes_only(self) -> None:
        """`live`/`total` and `nodes` must never disagree with each other."""
        result = await _map(
            [
                CapabilityProbe("memory", available=True, active=True),
                CapabilityProbe("voice", available=True, active=False),
                CapabilityProbe("peers", available=False, active=False),
            ]
        )

        assert result.total == len(result.nodes) == 2
        assert result.live == 1

    async def test_a_live_capability_carries_a_verifiable_count(self) -> None:
        result = await _map([CapabilityProbe("connectors", available=True, active=True, detail=3)])

        assert result.nodes[0].detail == 3

    async def test_a_dormant_capability_carries_no_invented_number(self) -> None:
        result = await _map([CapabilityProbe("channels", available=True, active=False)])

        assert result.nodes[0].active is False
        assert result.nodes[0].detail is None

    async def test_nothing_published_is_a_level_or_a_percentage(self) -> None:
        """Explicit product rule: no XP, no level, no social comparison."""
        result = await _map([CapabilityProbe("memory", available=True, active=True)])
        fields = set(type(result).model_fields) | set(type(result.nodes[0]).model_fields)

        forbidden = {"level", "xp", "score", "percent", "progress", "rank", "badge", "streak"}
        assert not (fields & forbidden)

    async def test_an_empty_instance_still_answers(self) -> None:
        """No capability offered is a state, not an error."""
        result = await _map([])

        assert result.nodes == []
        assert result.live == 0
        assert result.total == 0


class TestTheProbesDegradeRatherThanFail:
    async def test_an_unreadable_table_counts_as_not_ready(self) -> None:
        """One unreachable table must not blank the whole map."""
        from src.domains.capabilities.service import _count

        class _Boom:
            __name__ = "Boom"

            def __getattr__(self, _name: str) -> object:
                raise RuntimeError("db went away")

        assert await _count(_Boom(), uuid.uuid4()) == 0

    async def test_the_user_row_answers_the_capabilities_it_already_holds(self) -> None:
        """Re-querying what the authenticated row states would let the map
        disagree with every other surface about the same fact."""
        probes = _switches(_user(voice_enabled=True))

        assert probes["voice"].active is True
        assert probes["personality"].active is False

    async def test_voice_counts_either_of_its_two_switches(self) -> None:
        probes = _switches(_user(voice_mode_enabled=True))

        assert probes["voice"].active is True


class TestTheMapFollowsTheOperatorsSwitches:
    """An administrator may switch a capability off at runtime, inside the
    deployment's ceiling. A map reading the raw environment flag would keep
    announcing what the operator turned off an hour ago."""

    async def test_a_switched_off_capability_is_not_offered(self) -> None:
        probes = _switches(
            _user(image_generation_enabled=True),
            disabled=frozenset({PlatformCapability.IMAGE_GENERATION}),
        )

        assert probes["images"].available is False
        assert probes["images"].active is False

    async def test_a_counted_capability_that_is_off_is_never_even_queried(self) -> None:
        """Not just absent from the payload: no SQL at all — the router drops
        it anyway, so a query would be pure cost."""
        node = next(n for n in COUNTED_NODES if n.key == "mcp_servers")
        exploding = replace(node, load_model=_never)

        probe = await _counted(exploding, uuid.uuid4(), frozenset({PlatformCapability.MCP}))

        assert probe == CapabilityProbe("mcp_servers", available=False, active=False)

    async def test_speech_survives_as_long_as_one_of_its_two_switches_holds(self) -> None:
        probes = _switches(_user(voice_enabled=True), disabled=frozenset({PlatformCapability.STT}))

        assert probes["voice"].available is True


class TestTheMapCoversWhatTheProductShips:
    """The drift this closes: features shipped (documents v1.30.8, plugins
    v1.30.7, habits v1.28.0) while "what your assistant can do" kept
    describing an older product."""

    @pytest.mark.parametrize(
        "key", ["images", "documents", "plugins", "habits", "mcp_servers", "telephony"]
    )
    def test_the_recent_capabilities_have_a_node(self, key: str) -> None:
        assert key in MAP_NODE_KEYS

    def test_document_generation_is_live_wherever_it_is_offered(self) -> None:
        """It has no per-account opt-in — claiming a dormant state would send
        the reader hunting for a switch that does not exist."""
        probes = _switches(_user())

        assert probes["documents"].available is True
        assert probes["documents"].active is True

    def test_a_switch_capability_never_invents_a_tally(self) -> None:
        """ADR-185: a count is exact or it does not exist."""
        probes = _switches(_user())

        assert {key: probes[key].detail for key in SWITCH_NODE_KEYS} == dict.fromkeys(
            SWITCH_NODE_KEYS, None
        )


@pytest.mark.unit
class TestMemoryNodeCountsActiveOnly:
    """ADR-235 companion: invalidated memories STAY in the table (supersession
    trail), so the memory node must count the ACTIVE set — the same figure the
    memories panel shows. Found by the capability-map audit of 2026-08-20."""

    async def test_memory_probe_filters_the_supersession_trail(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from uuid import uuid4

        from sqlalchemy.dialects import postgresql

        from src.domains.capabilities import service as svc

        node = next(n for n in svc.COUNTED_NODES if n.key == "memory")
        captured: list = []

        async def _execute(stmt):
            captured.append(stmt)
            result = MagicMock()
            result.scalar.return_value = 0
            return result

        db = MagicMock()
        db.execute = AsyncMock(side_effect=_execute)

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _ctx():
            yield db

        with patch.object(svc, "get_db_context", _ctx):
            filters = node.load_filters() if node.load_filters else {}
            await svc._count(node.load_model(), uuid4(), **filters)

        sql = str(captured[0].compile(dialect=postgresql.dialect())).lower()
        assert "invalidated_at is null" in sql
