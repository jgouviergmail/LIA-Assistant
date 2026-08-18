"""The capability map may not silently fall behind the product.

Every capability LIA ships has to appear on the user-facing map, or be
explicitly recorded as deliberately absent WITH a reason. The failure this
prevents is the quiet one: a feature ships (documents, plugins, habits…),
nobody remembers the map exists, and "what your assistant can do" keeps
describing the product of six months ago. The owner asked for exactly that
never to happen again.

Two mechanisms, on purpose:

- ``PLATFORM_CAPABILITY_NODES`` / ``CAPABILITIES_OFF_THE_MAP`` partition the
  ``PlatformCapability`` enum, and ``service.py`` asserts the partition AT
  IMPORT (ADR-085 doctrine: the app refuses to boot on a missing entry), so
  a new capability cannot reach production undecided;
- this guard pins the properties the assert cannot express — that every
  exclusion carries a written reason, that every counted model really
  resolves, and that the three CLIENT surfaces (the chart's slots, the "next
  step" links, the six locales) can each handle every key the payload can
  contain. A guard watching only Python would have missed the half of this
  drift that lives in TypeScript.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.domains.capabilities.service import (
    CAPABILITIES_OFF_THE_MAP,
    COUNTED_NODES,
    MAP_NODE_KEYS,
    PLATFORM_CAPABILITY_NODES,
)
from src.domains.feature_switches.registry import PlatformCapability

pytestmark = pytest.mark.unit

_WEB = Path(__file__).resolve().parents[5] / "web"
_LOCALES = _WEB / "locales"

#: Nodes with no settings section of their own, each for a stated reason.
#: Shrink-only: a node lands here because the product has nowhere to send the
#: reader, never because wiring the link was skipped.
NODES_WITHOUT_A_SETTINGS_DESTINATION = {
    # Document generation is an instance-level capability with no per-account
    # setting — there is no switch for a reader to find.
    "documents",
}


class TestEveryCapabilityHasBeenDecided:
    def test_the_enum_is_partitioned_between_mapped_and_excluded(self) -> None:
        decided = set(PLATFORM_CAPABILITY_NODES) | set(CAPABILITIES_OFF_THE_MAP)

        assert decided == set(PlatformCapability), (
            "a new PlatformCapability must either draw a node on the map or be "
            "listed in CAPABILITIES_OFF_THE_MAP with a reason: "
            f"{sorted(c.value for c in set(PlatformCapability) - decided)}"
        )

    def test_no_capability_is_both_mapped_and_excluded(self) -> None:
        assert not set(PLATFORM_CAPABILITY_NODES) & set(CAPABILITIES_OFF_THE_MAP)

    def test_every_exclusion_states_why(self) -> None:
        """A bare allowlist rots — the next reader must be able to challenge it."""
        for capability, reason in CAPABILITIES_OFF_THE_MAP.items():
            assert len(reason.strip()) >= 30, f"{capability.value} has no real reason"

    def test_every_mapped_capability_points_at_a_real_node(self) -> None:
        for capability, key in PLATFORM_CAPABILITY_NODES.items():
            assert key in MAP_NODE_KEYS, f"{capability.value} -> unknown node '{key}'"


class TestEveryCountedNodeCanActuallyCount:
    """`_counted` swallows an import error and reports 0, so a typo in a module
    path would show as "you have nothing" rather than as a crash — the worst
    kind of failure this map can have. Resolve every model here instead."""

    @pytest.mark.parametrize(
        "node",
        [node for node in COUNTED_NODES if node.load_model],
        ids=lambda node: node.key,
    )
    def test_the_model_resolves_and_is_user_scoped(self, node: object) -> None:
        model = node.load_model()  # type: ignore[attr-defined]

        assert hasattr(model, "user_id"), f"{model} carries no user_id column"

    @pytest.mark.parametrize(
        "node",
        [node for node in COUNTED_NODES if node.load_filters],
        ids=lambda node: node.key,
    )
    def test_declared_filters_name_real_columns(self, node: object) -> None:
        model = node.load_model()  # type: ignore[attr-defined]

        for column in node.load_filters():  # type: ignore[attr-defined]
            assert hasattr(model, column), f"{model} has no column '{column}'"

    def test_declared_environment_flags_exist(self) -> None:
        """A typo'd flag name reads False through `getattr(..., False)`, so the
        capability would be silently absent from every account's map — the same
        quiet failure the partition assert exists to prevent, one layer down."""
        from src.core.config import settings

        unknown = sorted(
            node.env_flag
            for node in COUNTED_NODES
            if node.env_flag and not hasattr(settings, node.env_flag)
        )

        assert not unknown, f"COUNTED_NODES names settings that do not exist: {unknown}"

    @pytest.mark.parametrize("node", COUNTED_NODES, ids=lambda node: node.key)
    def test_every_node_declares_exactly_one_way_to_count(self, node: object) -> None:
        """A row with neither would report an empty capability forever; a row
        with both would have two answers to the same question."""
        ways = [node.load_model, node.count_with]  # type: ignore[attr-defined]

        assert sum(way is not None for way in ways) == 1, f"{node.key} — {ways}"  # type: ignore[attr-defined]


class TestTheChartCanDrawEveryNode:
    """`layoutCapabilities` DROPS a key its table does not know — an
    unlabelled dot would be worse than an absent one — so a node shipped
    without a slot is invisible rather than broken. Read the frontend tables
    from here: they are the other half of this contract, and a guard that only
    watched Python would have missed exactly the drift this closes."""

    def test_every_node_has_a_slot_on_the_constellation(self) -> None:
        source = (_WEB / "src/components/capabilities/constellation-layout.ts").read_text(
            encoding="utf-8"
        )
        placed = set(re.findall(r"\{ key: '([a-z_]+)', ring: '(?:inner|outer)' \}", source))

        assert MAP_NODE_KEYS <= placed, (
            "CAPABILITY_ORDER has no slot for "
            f"{sorted(MAP_NODE_KEYS - placed)} — the chart would silently drop them"
        )
        assert (
            placed <= MAP_NODE_KEYS
        ), f"slots for nodes nothing publishes: {sorted(placed - MAP_NODE_KEYS)}"

    def test_every_node_offers_a_next_step_or_is_exempt(self) -> None:
        """A dormant star exists to carry ONE next step, and the settings
        overview quotes the same pairing in reverse. Falling back to the
        settings root is acceptable only where no section exists at all."""
        source = (_WEB / "src/lib/capability-sections.ts").read_text(encoding="utf-8")
        block = source.split("CAPABILITY_SECTION", 1)[1].split("};", 1)[0]
        routed = set(re.findall(r"^\s{2}([a-z_]+): '", block, re.M))

        assert MAP_NODE_KEYS - routed == NODES_WITHOUT_A_SETTINGS_DESTINATION, (
            "a capability node gained or lost its settings destination: "
            f"unrouted={sorted(MAP_NODE_KEYS - routed)}"
        )


class TestTheClientCanNameEveryNode:
    """A node whose label is missing renders as a raw key, or as nothing."""

    @pytest.mark.parametrize("lng", ["en", "fr", "de", "es", "it", "zh"])
    def test_every_node_key_is_translated(self, lng: str) -> None:
        path = _LOCALES / lng / "translation.json"
        labels = json.loads(path.read_text(encoding="utf-8"))["capabilities"]["nodes"]

        missing = sorted(key for key in MAP_NODE_KEYS if not labels.get(key))
        assert not missing, f"{lng}: capabilities.nodes.* missing {missing}"

    def test_no_orphan_label_survives_a_removed_capability(self) -> None:
        labels = json.loads((_LOCALES / "en" / "translation.json").read_text(encoding="utf-8"))
        orphans = sorted(set(labels["capabilities"]["nodes"]) - set(MAP_NODE_KEYS))

        assert not orphans, f"capabilities.nodes.* labels nothing draws: {orphans}"
