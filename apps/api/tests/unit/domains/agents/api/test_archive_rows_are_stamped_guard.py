"""Every row a TURN archives carries the out-of-turn stamp (ADR-276).

A turn archives up to three rows — the person's question, the answer, and, when
it stops on a HITL interrupt, the question LIA asked INSTEAD of answering — and
an out-of-turn run needs the stamp on all of them: the read keeps them out of
the chat, and the retention sweep finds them by it.

Measured 2026-09-09 on the dev account, from a real ticket run: the HITL
question was assembled as a dict literal at its call site, so a workboard run
that stopped on a confirmation archived its full draft preview as an ORDINARY
assistant message (``hidden=False``, no stamp) — the person read « Êtes-vous
sûr de vouloir supprimer définitivement ce ticket ? » in their chat, where
answering it does nothing, and the row could never be purged (the sweep matches
``hidden`` AND the stamp). The path had been unreachable until lot 7 let a
ticket run ask a question at all, so lot 2's « both rows » was true when it was
written and became false three lots later.

Three assertions, closing the loop:

- no archive call site of this package builds its metadata inline;
- every ``build_*_metadata`` of the module stamps when a run is driving;
- the second list is COMPLETE — a new builder cannot be added without being
  proven, which is the only thing that keeps the first assertion meaningful.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from src.core.field_names import FIELD_HIDDEN
from src.domains.agents.api import archive_metadata
from src.domains.agents.api.archive_metadata import (
    build_assistant_metadata,
    build_hitl_question_metadata,
    build_interrupted_stream_metadata,
)
from src.domains.agents.api.run_origin import RunOrigin, out_of_turn_origin_ctx

pytestmark = pytest.mark.unit

#: The package a TURN archives its rows from. The proactive and reminder paths
#: archive a NOTIFICATION, which is meant to be read — a different act, and
#: deliberately outside this rule.
API_PACKAGE = Path(archive_metadata.__file__).parent

#: Position of ``metadata`` in ``ConversationService.archive_message``.
METADATA_ARGUMENT = 3


class _Capture:
    def __init__(self, steps: list[dict[str, Any]] | None = None) -> None:
        self._steps = steps or []

    def snapshot(self) -> list[dict[str, Any]]:
        return self._steps


def _builders() -> dict[str, dict[str, Any]]:
    """Every builder, with arguments plausible enough to run it."""
    return {
        "build_assistant_metadata": lambda: build_assistant_metadata(
            {},
            widgets=None,
            trace_capture=_Capture(),
            duration_ms=12,
            run_id="run-1",
            followup_suggestions=None,
            initiative_motivation=None,
            effects=None,
        ),
        "build_hitl_question_metadata": lambda: build_hitl_question_metadata(
            run_id="run-1", intention="workboard"
        ),
        "build_interrupted_stream_metadata": lambda: build_interrupted_stream_metadata(
            run_id="run-1", reason="client_gone"
        ),
    }


def _inline_metadata_call_sites() -> list[str]:
    """Archive calls whose metadata is assembled at the call site."""
    offenders: list[str] = []
    for path in sorted(API_PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = node.func
            if not (isinstance(called, ast.Attribute) and called.attr == "archive_message"):
                continue
            metadata = node.args[METADATA_ARGUMENT] if len(node.args) > METADATA_ARGUMENT else None
            for keyword in node.keywords:
                if keyword.arg == "metadata":
                    metadata = keyword.value
            if isinstance(metadata, ast.Dict | ast.DictComp):
                offenders.append(f"{path.name}:{node.lineno}")
    return offenders


class TestTheStampReachesEveryRowOfATurn:
    def test_no_archive_call_site_builds_its_metadata_inline(self) -> None:
        offenders = _inline_metadata_call_sites()

        assert not offenders, (
            "these archive calls assemble their metadata at the call site, so the "
            f"out-of-turn stamp cannot reach them: {offenders}. Build it with a "
            "``build_*_metadata`` of api/archive_metadata.py — a dict literal here "
            "is how a ticket run's confirmation question landed in the chat."
        )

    @pytest.mark.parametrize("name", sorted(_builders()))
    def test_every_builder_stamps_when_a_run_is_driving(self, name: str) -> None:
        token = out_of_turn_origin_ctx.set(
            RunOrigin(kind="workboard", ticket_id="t-1", run_id="run-1")
        )
        try:
            produced = _builders()[name]()
        finally:
            out_of_turn_origin_ctx.reset(token)

        assert produced[FIELD_HIDDEN] is True, name
        assert produced["workboard"] == {"ticket_id": "t-1", "run_id": "run-1"}, name

    @pytest.mark.parametrize("name", sorted(_builders()))
    def test_an_ordinary_chat_turn_is_untouched(self, name: str) -> None:
        produced = _builders()[name]()

        assert FIELD_HIDDEN not in produced, name
        assert "workboard" not in produced, name

    def test_the_proven_list_is_every_builder_the_module_has(self) -> None:
        """A builder nobody proves is a builder that may forget the stamp."""
        declared = {
            name
            for name in vars(archive_metadata)
            if name.startswith("build_") and name.endswith("_metadata")
        }

        assert declared == set(_builders()), (
            "add the new builder to this guard's table: the « no inline dict » rule "
            "only means something while every builder is proven to stamp."
        )
