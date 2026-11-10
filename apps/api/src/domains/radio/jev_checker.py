"""Optional native verifier; an uncertain batch delegates the complete original script.

One Noul per checked line: "this line makes a claim its cited facts do not
support". A batch is accepted only when EVERY line is decided — its probability at
most the ``line_margin`` gate (supported) or at least ``1 - line_margin``
(unsupported), compared exactly (``jev_gates.py``); anything in between hands the
whole script to the existing verifier.
"""

import json
from collections.abc import Sequence
from decimal import Decimal
from time import perf_counter
from typing import Literal
from uuid import UUID

from pydantic import JsonValue

from src.core.constants import JEV_SHARED_STATE_BATCH_BYTES
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.llm_config.jev_gates import gate_passes, threshold_for
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_statistics_sink import count_jev_outcome
from src.domains.radio.checking import checked_positions
from src.domains.radio.facts import FactPack
from src.domains.radio.production import LineChecker
from src.domains.radio.sms_context import sms_pack_current
from src.domains.radio.verification import VerifiedLine
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.jev_debug_store import record_action
from src.infrastructure.llm.jev_runtime import choose_many_with_jev
from src.infrastructure.llm.typesafe_client import NoulQuestion
from src.infrastructure.observability.metrics_jev import (
    jev_decision_duration_seconds,
)

# Chosen on the 30 synthetic calibration scripts (no wrong acceptance), verified on
# the 24 held-out stories (no wrong acceptance; 94 % of the scripts decided natively
# against 77 % for the former three-way Choice), 2026-10-11.
DECISION_MARGIN = 0.16
# The script shape those corpora measured: at most this many checked lines.
MAX_CHECKED_LINES = 24

LocalRefusal = Literal["too_many_lines", "missing_references", "request_too_large"]


def _verifier_request(
    lines: Sequence[VerifiedLine], pack: FactPack, station: str
) -> tuple[JsonValue, dict[str, NoulQuestion]] | LocalRefusal:
    positions = checked_positions(lines)
    if not 1 <= len(positions) <= MAX_CHECKED_LINES:
        return "too_many_lines"
    cited = {ref for line in lines for ref in line.refs}
    if not cited.issubset(pack.by_id()):
        return "missing_references"
    state: JsonValue = {
        "station": station,
        "facts": [fact.model_dump(mode="json") for fact in pack.facts if fact.id in cited],
        "script": {
            f"line{index}": {"text": line.text, "kind": line.kind.value, "refs": list(line.refs)}
            for index, line in enumerate(lines)
        },
    }
    question = NoulQuestion.model_validate_json(load_prompt("jev_radio_question", version="v1"))
    questions = {f"line{index}": question.filled(line_key=f"line{index}") for index in positions}
    encoded = json.dumps(
        {
            "model": "界" * 100,
            "state": state,
            "questions": {key: value.model_dump() for key, value in questions.items()},
        },
        ensure_ascii=False,
    )
    if len(encoded.encode()) > JEV_SHARED_STATE_BATCH_BYTES:
        return "request_too_large"
    return state, questions


def verifier_request(
    lines: Sequence[VerifiedLine], pack: FactPack, station: str
) -> tuple[JsonValue, dict[str, NoulQuestion]] | None:
    """No truncation: a script that does not fit uses the existing verifier."""
    request = _verifier_request(lines, pack, station)
    return None if isinstance(request, str) else request


def _decided(attempt: DecisionAttempt, probability: float) -> bool:
    return gate_passes(attempt.thresholds, JevUsage.RADIO_VERIFICATION, "line_margin", probability)


def _flagged(attempt: DecisionAttempt, probability: float) -> bool:
    """A decided line at or above ``1 - margin`` makes a claim its facts do not support."""
    margin = threshold_for(attempt.thresholds, JevUsage.RADIO_VERIFICATION, "line_margin")
    return Decimal(str(probability)) >= 1 - margin


class JevLineChecker:
    """Keep the deterministic editor and user-selected verification formats intact."""

    def __init__(
        self, fallback: LineChecker, *, user_id: UUID, run_id: str, station_name: str
    ) -> None:
        self._fallback = fallback
        self._user_id = user_id
        self._run_id = run_id
        self._station_name = station_name

    async def unsupported(
        self, lines: Sequence[VerifiedLine], pack: FactPack
    ) -> frozenset[int] | None:
        if not await sms_pack_current(pack):
            return None
        positions = checked_positions(lines)
        if not positions:
            return frozenset()
        request = _verifier_request(lines, pack, self._station_name)
        if isinstance(request, str):
            # Counted: a script handed back before any call used to leave no trace.
            count_jev_outcome(JevUsage.RADIO_VERIFICATION, request)
            return await self._fallback.unsupported(lines, pack)
        state, questions = request
        started = perf_counter()
        attempt = await choose_many_with_jev(
            usage=JevUsage.RADIO_VERIFICATION,
            user_id=self._user_id,
            run_id=self._run_id,
            state=state,
            questions=questions,
        )
        accepted = (
            attempt.outcome == "success"
            and set(attempt.nouls) == set(questions)
            and all(_decided(attempt, answer.noul) for answer in attempt.nouls.values())
        )
        outcome = (
            "verified"
            if accepted
            else ("uncertain" if attempt.outcome == "success" else attempt.outcome)
        )
        await record_action(
            self._user_id,
            attempt.diagnostic,
            action="selected" if accepted else "fallback",
            outcome=outcome,
            target="radio_editor" if accepted else "radio_verifier",
        )
        count_jev_outcome(JevUsage.RADIO_VERIFICATION, outcome)
        jev_decision_duration_seconds.labels(
            usage=JevUsage.RADIO_VERIFICATION, outcome=outcome
        ).observe(perf_counter() - started)
        if not accepted:
            return await self._fallback.unsupported(lines, pack)
        return frozenset(
            index for index in positions if _flagged(attempt, attempt.nouls[f"line{index}"].noul)
        )
