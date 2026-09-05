"""A third-party MCP tool's policy is DERIVED, never asserted (ADR-263 + ADR-255).

The MCP specification is normative: *"For trust & safety and security, clients
MUST consider tool annotations to be untrusted unless they come from trusted
servers."* So the derivation is asymmetric, exactly like
``declared_tool_category`` next to it:

- a declared MUTATION is acted upon — the worst a lying server buys itself is
  one confirmation too many;
- a declared read-only is NOT believed — it would remove the tool from the
  safety nets on the word of a third party.

Returning None is therefore the safe answer, not a failure: the tool simply
declares no policy, and the native completeness guard skips ``mcp_`` names.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.infrastructure.mcp.registration import derive_mcp_mutation_policy

pytestmark = [pytest.mark.unit]


class TestTheServerHitlSettingWins:
    """A server whose owner asked for confirmation gets it, whatever it annotates."""

    def test_hitl_required_yields_confirm(self) -> None:
        assert derive_mcp_mutation_policy(True, None) == "confirm"

    def test_hitl_required_beats_a_read_only_claim(self) -> None:
        """The user's setting is authority; the server's claim is not."""
        assert derive_mcp_mutation_policy(True, {"read_only_hint": True}) == "confirm"


class TestTheDeclarationTightensOnly:
    @pytest.mark.parametrize(
        ("annotations", "expected"),
        [
            # Declared destructive: confirm, per the spec's own default.
            ({"destructive_hint": True}, "confirm"),
            # "not read-only" with destructive left unsaid: destructiveHint
            # DEFAULTS to true in the spec, so the safe reading is confirm.
            ({"read_only_hint": False}, "confirm"),
            # Explicitly additive-only: a mutation that does not destroy.
            ({"read_only_hint": False, "destructive_hint": False}, "reversible"),
            # A read-only CLAIM is never believed: no policy, name heuristic keeps its job.
            ({"read_only_hint": True}, None),
            # Nothing said, or nonsense: nothing derived.
            ({}, None),
            (None, None),
            ("garbage", None),
            (42, None),
        ],
    )
    def test_derivation(self, annotations: Any, expected: str | None) -> None:
        assert derive_mcp_mutation_policy(False, annotations) == expected

    def test_a_derived_reversible_carries_a_reason(self) -> None:
        """``reversible`` exempts from a confirmation, so it must say why."""
        from src.infrastructure.mcp.registration import derive_mcp_mutation_policy_reason

        reason = derive_mcp_mutation_policy_reason("reversible")
        assert reason and reason.strip().endswith(".")
        assert derive_mcp_mutation_policy_reason("confirm") is None
        assert derive_mcp_mutation_policy_reason(None) is None
