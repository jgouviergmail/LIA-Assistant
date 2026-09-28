"""A draft refused where nobody can confirm names the tool that CAN act (ADR-314, amended).

Measured on production, 2026-09-27. Five morning routines were told to « e-mail
it to me ». Four called ``send_email_to_me_tool``, which needs no confirmation
and runs unattended; one called ``send_email_tool``, whose draft nobody can
confirm in a routine. The gate refused it — rightly — and told the loop only
that the action waits for the user: the loop reported it and sent nothing,
while the tool that would have worked was bound in the same turn.

So the confirmation-free tool DECLARES which draft it stands in for, and in
which case; the draft's unattended refusal names it (``effects/runtime.py``);
and the boot refuses a declaration that would send the loop into a second
refusal, name a tool that does not exist, or never apply.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.domains.agents.effects.gate import assert_unattended_stand_ins
from src.domains.agents.registry.catalogue import ToolManifest, UnattendedStandIn

pytestmark = [pytest.mark.unit]


class TestTheCatalogueDeclaresIt:
    def test_the_self_send_stands_in_for_the_draft_send(
        self, manifests: dict[str, ToolManifest]
    ) -> None:
        stand_in = manifests["send_email_to_me_tool"].stands_in_unattended_for

        assert stand_in is not None
        assert stand_in.tool == "send_email_tool"
        assert "user themselves" in stand_in.when

    def test_the_real_catalogue_passes_the_boot_check(
        self, manifests: dict[str, ToolManifest]
    ) -> None:
        assert_unattended_stand_ins(manifests.values())


def _manifest(name: str, policy: str | None, stand_in: UnattendedStandIn | None = None) -> Any:
    return SimpleNamespace(name=name, mutation_policy=policy, stands_in_unattended_for=stand_in)


class TestTheBootRefusesAStandInThatCannotHelp:
    def test_a_valid_declaration_passes(self) -> None:
        assert_unattended_stand_ins(
            [
                _manifest("send_tool", "draft"),
                _manifest("self_tool", "reversible", UnattendedStandIn("send_tool", "to oneself")),
            ]
        )

    @pytest.mark.parametrize(
        ("catalogue", "problem"),
        [
            (
                [_manifest("self_tool", "reversible", UnattendedStandIn("ghost_tool", "x"))],
                "unknown tool 'ghost_tool'",
            ),
            (
                [
                    _manifest("send_tool", "reversible"),
                    _manifest("self_tool", "reversible", UnattendedStandIn("send_tool", "x")),
                ],
                "never refused unattended",
            ),
            (
                [
                    _manifest("send_tool", "draft"),
                    _manifest("self_tool", "confirm", UnattendedStandIn("send_tool", "x")),
                ],
                "needs a confirmation itself",
            ),
            (
                [
                    _manifest("send_tool", "draft"),
                    _manifest("self_tool", "reversible", UnattendedStandIn("send_tool", "  ")),
                ],
                "states no case",
            ),
        ],
        ids=["unknown-target", "target-never-refused", "stand-in-refused-too", "no-case"],
    )
    def test_each_useless_declaration_is_refused(self, catalogue: list[Any], problem: str) -> None:
        with pytest.raises(AssertionError, match=problem):
            assert_unattended_stand_ins(catalogue)

    def test_two_stand_ins_for_one_draft_are_refused(self) -> None:
        """The refusal can name ONE tool: two would be a coin toss."""
        with pytest.raises(AssertionError, match="two stand-ins"):
            assert_unattended_stand_ins(
                [
                    _manifest("send_tool", "draft"),
                    _manifest("a_tool", "reversible", UnattendedStandIn("send_tool", "x")),
                    _manifest("b_tool", "reversible", UnattendedStandIn("send_tool", "y")),
                ]
            )

    def test_every_problem_is_listed_at_once(self) -> None:
        with pytest.raises(AssertionError) as refused:
            assert_unattended_stand_ins(
                [
                    _manifest("a_tool", "reversible", UnattendedStandIn("ghost_tool", "x")),
                    _manifest("b_tool", "draft", UnattendedStandIn("ghost_tool", "")),
                ]
            )

        message = str(refused.value)
        assert "a_tool" in message and "b_tool" in message
