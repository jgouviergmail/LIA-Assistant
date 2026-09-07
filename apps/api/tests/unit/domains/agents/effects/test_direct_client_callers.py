"""No module reaches an external service without saying what that means.

Four surfaces were found one after another — the briefing, the relationship
debrief, the heartbeat sweep, the interest sweep — each because a person
noticed an absence rather than because a test did. They are the same family:
a module that calls a client from ``domains/connectors/clients`` directly never
meets the tool gate, so the capability it used is recorded nowhere.

The owner named the family on 2026-09-07: « une notification centre d'intérêt
exécute des outils ! ce n'est pas que de la génération de texte sur aucune
base ». This guard is the answer — the list is enumerable, so it is enumerated,
and a twenty-third module cannot be added without classifying it.

The list it walks is the IMPORT graph, which is complete by construction: a
module cannot call a client it has not imported.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.domains.agents.effects.direct_client_callers import (
    AWAITING_RECORDING,
    CLIENT_CALL_RECORDERS,
    NOT_A_CAPABILITY_READ,
)

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[5] / "src"

#: The tool layer meets the gate by construction; the connector layer IS the
#: client layer. Everything else must declare itself.
_EXEMPT_PREFIXES = ("domains/agents/tools/", "domains/connectors/")

_IMPORT = re.compile(r"from src\.domains\.connectors\.clients\.(\w+) import")

#: What a recorder names when the read happens INSIDE a turn: the authorship
#: comes from the runtime context, so there is no fixed-source surface.
IN_TURN = "in-turn"


def _callers() -> dict[str, set[str]]:
    """Every module outside the exempt layers that imports a client."""
    found: dict[str, set[str]] = {}
    for path in _SRC.rglob("*.py"):
        relative = path.relative_to(_SRC).as_posix()
        if any(relative.startswith(prefix) for prefix in _EXEMPT_PREFIXES):
            continue
        clients = set(_IMPORT.findall(path.read_text(encoding="utf-8", errors="ignore")))
        if clients:
            found[relative] = clients
    return found


def _declared() -> set[str]:
    return set(CLIENT_CALL_RECORDERS) | set(NOT_A_CAPABILITY_READ) | set(AWAITING_RECORDING)


class TestEveryDirectCallerIsClassified:
    """The property that turns four discoveries into one method."""

    def test_no_caller_is_unclassified(self) -> None:
        unclassified = sorted(set(_callers()) - _declared())
        assert not unclassified, (
            f"modules calling an external client with nothing said about it: "
            f"{unclassified} — declare each in CLIENT_CALL_RECORDERS (naming "
            "the surface that records it), in NOT_A_CAPABILITY_READ (with the "
            "reason it reads nobody's data), or in AWAITING_RECORDING (with "
            "what it reads)"
        )

    def test_no_classification_outlives_its_module(self) -> None:
        """A declaration for a module that stopped calling a client is stale."""
        stale = sorted(_declared() - set(_callers()))
        assert not stale, f"declared but no longer imports a client: {stale}"

    @pytest.mark.parametrize(
        "table",
        [CLIENT_CALL_RECORDERS, NOT_A_CAPABILITY_READ, AWAITING_RECORDING],
        ids=["recorders", "not-a-read", "awaiting"],
    )
    def test_a_module_appears_in_one_table_only(self, table: dict[str, str]) -> None:
        others = [
            t
            for t in (CLIENT_CALL_RECORDERS, NOT_A_CAPABILITY_READ, AWAITING_RECORDING)
            if t is not table
        ]
        for other in others:
            overlap = sorted(set(table) & set(other))
            assert not overlap, f"classified twice: {overlap}"


class TestTheDeclarationsSayEnoughToBeChecked:
    """A one-word reason is a box ticked, not a decision made."""

    def test_every_recorder_names_a_real_surface(self) -> None:
        """Either an out-of-turn surface, or the in-turn capability table."""
        from src.domains.shared.consultation_surfaces import CONSULTATION_SURFACES

        for module, surface in CLIENT_CALL_RECORDERS.items():
            if surface == IN_TURN:
                continue
            assert surface in CONSULTATION_SURFACES, (
                f"{module} says it records through {surface!r}, which declares " "no vocabulary"
            )

    def test_every_in_turn_recorder_actually_records(self) -> None:
        """A pointer to a module that records nothing certifies a gap.

        Read as an AST CALL, never a substring: a docstring saying a module
        records is not a module that records, and that confusion is exactly
        what this family of defects is made of.
        """
        import ast

        for module, surface in CLIENT_CALL_RECORDERS.items():
            if surface != IN_TURN:
                continue
            tree = ast.parse((_SRC / module).read_text(encoding="utf-8"))
            called = {
                node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
            }
            assert "record_treatment" in called, (
                f"{module} is declared an in-turn recorder but never calls " "record_treatment"
            )

    def test_every_in_turn_capability_is_declared_and_readable(self) -> None:
        """The name a node records under must resolve to a real noun."""
        from src.domains.agents.effects.treatment_labels import UNKNOWN_DOMAIN, treatment_domain
        from src.domains.shared.consultation_surfaces import IN_TURN_CAPABILITIES

        assert IN_TURN_CAPABILITIES, "no in-turn capability declared"
        for capability, domain in IN_TURN_CAPABILITIES.items():
            resolved = treatment_domain(capability)
            assert resolved != UNKNOWN_DOMAIN, f"{capability} headlines as Unknown"
            assert resolved == domain

    @pytest.mark.parametrize(
        "table",
        [NOT_A_CAPABILITY_READ, AWAITING_RECORDING],
        ids=["not-a-read", "awaiting"],
    )
    def test_every_reason_is_an_argument(self, table: dict[str, str]) -> None:
        for module, reason in table.items():
            assert len(reason.strip()) > 40, (
                f"{module}: « {reason} » is not an argument. The point of this "
                "field is that someone had to think about it."
            )


class TestTheDebtIsMeasuredRatherThanHidden:
    """``AWAITING_RECORDING`` is a declared gap, and it must only shrink."""

    #: What the audit of 2026-09-07 found. Shrink-only, like every other
    #: ratchet in this codebase: a module leaves this table when it starts
    #: recording, and nothing may be added without the count moving the wrong
    #: way in a review.
    BASELINE = 0

    def test_the_backlog_never_grows(self) -> None:
        assert len(AWAITING_RECORDING) <= self.BASELINE, (
            f"{len(AWAITING_RECORDING)} modules read without recording, against "
            f"{self.BASELINE} when the family was enumerated. A new one is a "
            "new silent surface — record it instead."
        )

    def test_a_module_that_started_recording_left_the_backlog(self) -> None:
        overlap = sorted(set(AWAITING_RECORDING) & set(CLIENT_CALL_RECORDERS))
        assert not overlap, f"records AND declared as not recording: {overlap}"
