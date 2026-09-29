"""Optional native verifier; an uncertain batch delegates the complete original script."""

import json
from collections.abc import Sequence
from time import perf_counter
from uuid import UUID

from pydantic import JsonValue

from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.radio.checking import checked_positions
from src.domains.radio.facts import FactPack
from src.domains.radio.production import LineChecker
from src.domains.radio.verification import VerifiedLine
from src.infrastructure.llm.jev_debug_store import record_action
from src.infrastructure.llm.jev_runtime import choose_many_with_jev
from src.infrastructure.llm.typesafe_client import MAX_QUESTIONS, MAX_REQUEST_BYTES, ChoiceQuestion
from src.infrastructure.observability.metrics_jev import (
    jev_decision_duration_seconds,
    jev_decisions_total,
)

# Calibrated on 30 synthetic scripts, then held out on 24 new, longer stories.
# This is concentration, not a correctness guarantee; every ambiguous batch falls back.
MIN_CONFIDENCE = 0.95


def verifier_request(
    lines: Sequence[VerifiedLine], pack: FactPack, station: str
) -> tuple[JsonValue, dict[str, ChoiceQuestion]] | None:
    """No truncation: a script that does not fit uses the existing verifier."""
    positions = checked_positions(lines)
    if not 1 <= len(positions) <= MAX_QUESTIONS:
        return None
    cited = {ref for line in lines for ref in line.refs}
    if not cited.issubset(pack.by_id()):
        return None
    state: JsonValue = {
        "station": station,
        "facts": [fact.model_dump(mode="json") for fact in pack.facts if fact.id in cited],
        "script": {
            f"line{index}": {"text": line.text, "kind": line.kind.value, "refs": list(line.refs)}
            for index, line in enumerate(lines)
        },
    }
    question = ChoiceQuestion.model_validate_json(load_prompt("jev_radio_question", version="v1"))
    questions = {
        f"line{index}": question.model_copy(
            update={"instructions": question.instructions.format(line_key=f"line{index}")}
        )
        for index in positions
    }
    encoded = json.dumps(
        {
            "model": "界" * 100,
            "state": state,
            "questions": {key: value.model_dump() for key, value in questions.items()},
        },
        ensure_ascii=False,
    )
    return (state, questions) if len(encoded.encode()) <= MAX_REQUEST_BYTES else None


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
        positions = checked_positions(lines)
        if not positions:
            return frozenset()
        request = verifier_request(lines, pack, self._station_name)
        if request is None:
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
            and set(attempt.answers) == set(questions)
            and all(
                answer.confidence >= MIN_CONFIDENCE
                and answer.choice in {"supported", "unsupported"}
                for answer in attempt.answers.values()
            )
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
        jev_decisions_total.labels(usage=JevUsage.RADIO_VERIFICATION, outcome=outcome).inc()
        jev_decision_duration_seconds.labels(
            usage=JevUsage.RADIO_VERIFICATION, outcome=outcome
        ).observe(perf_counter() - started)
        if not accepted:
            return await self._fallback.unsupported(lines, pack)
        return frozenset(
            index for index in positions if attempt.answers[f"line{index}"].choice == "unsupported"
        )
