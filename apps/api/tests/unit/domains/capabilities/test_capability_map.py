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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.capabilities.router import get_capability_map
from src.domains.capabilities.service import CapabilityProbe

pytestmark = pytest.mark.unit


def _user(**over: object) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.voice_enabled = False
    user.voice_mode_enabled = False
    user.heartbeat_enabled = False
    user.personality_id = None
    for key, value in over.items():
        setattr(user, key, value)
    return user


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
        from src.domains.capabilities.service import _from_user

        probes = {probe.key: probe for probe in _from_user(_user(voice_enabled=True))}

        assert probes["voice"].active is True
        assert probes["personality"].active is False

    async def test_voice_counts_either_of_its_two_switches(self) -> None:
        from src.domains.capabilities.service import _from_user

        probes = {probe.key: probe for probe in _from_user(_user(voice_mode_enabled=True))}

        assert probes["voice"].active is True
