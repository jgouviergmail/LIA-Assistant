"""The engines answering the questions: JEV, the configured generative slot, the current mechanism.

Every paid call is pinned to the database configuration, checked against the
qualification's cumulative euro ceiling BEFORE it is sent, and settled in the
instance ledger after it (no account pays for a qualification).
"""

import asyncio
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from scripts.jev_semantic.questions import answer_tool, render_prompt
from src.core.prompt_layout import single_call_messages
from src.infrastructure.llm.typesafe_client import (
    MAX_QUESTIONS,
    ChoiceQuestion,
    DecisionUsage,
    TypeSafeClient,
    TypeSafeError,
)

SURFACE = "jev_semantic_qualification"


@dataclass
class Answer:
    """One engine's answer to one case."""

    labels: dict[str, str] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)
    latency_ms: float = 0.0
    cost_eur: float = 0.0
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None


class SpendLedger:
    """Cumulative spend of the whole qualification; nothing is sent past the ceiling."""

    def __init__(self, path: Path, ceiling_eur: float) -> None:
        self.path = path
        self.ceiling = ceiling_eur
        self.spent = float(json.loads(path.read_text())["spent_eur"]) if path.exists() else 0.0

    def remaining(self) -> float:
        """Euros still authorised."""
        return max(0.0, self.ceiling - self.spent)

    def check(self, upper_eur: float) -> None:
        """Refuse a call whose upper bound would cross the ceiling."""
        if self.spent + upper_eur > self.ceiling:
            raise SystemExit(
                f"STOP: the {self.ceiling} EUR ceiling would be crossed (spent {self.spent:.4f})"
            )

    def add(self, eur: float) -> None:
        """Record settled spend durably."""
        self.spent += eur
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"spent_eur": self.spent, "updated_at": datetime.now(UTC).isoformat()})
        )


class JevEngine:
    """The native decision provider, configured exactly as the application reads it."""

    name = "jev"

    def __init__(self, ledger: SpendLedger) -> None:
        self.ledger = ledger
        self.config: Any = None
        self.http: httpx.AsyncClient | None = None
        self.client: TypeSafeClient | None = None

    async def __aenter__(self) -> JevEngine:
        from src.domains.llm_config.jev_registry import JevUsage
        from src.domains.llm_config.jev_settings import read_configuration
        from src.infrastructure.database import get_db_context

        # The deployment's decision model, key and tariff, read through the
        # application's own resolver (an existing usage's slot, switches ignored).
        async with get_db_context() as db:
            readiness, config = await read_configuration(db, JevUsage.MEMORY_REFERENCE_PRESENCE)
        if config is None:
            raise SystemExit(f"JEV is not ready on this deployment: {readiness}")
        self.config = config
        self.http = httpx.AsyncClient()
        self.client = TypeSafeClient(self.http, config.api_key.get_secret_value())
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self.http is not None:
            await self.http.aclose()

    def describe(self) -> dict[str, object]:
        """What ran, for the evidence file (no secret)."""
        return {"model": self.config.model, "timeout_seconds": self.config.timeout_seconds}

    def _upper_eur(self, questions: Mapping[str, ChoiceQuestion], state: object) -> float:
        from src.infrastructure.cache.pricing_cache import get_cached_usd_eur_rate

        body = json.dumps(
            {"state": state, "questions": {k: q.model_dump() for k, q in questions.items()}},
            ensure_ascii=False,
        ).encode("utf-8")
        price = self.config.price
        # One token per byte in, 64 tokens out per question: deliberately pessimistic.
        usd = (
            len(body) * float(price.input_price) + 64 * len(questions) * float(price.output_price)
        ) / 1e6
        return usd * get_cached_usd_eur_rate()

    async def _charge(self, usage: DecisionUsage) -> float:
        from src.domains.llm.pricing_service import token_cost_usd
        from src.domains.usage_limits.instance_spend import record_instance_llm_spend
        from src.infrastructure.cache.pricing_cache import get_cached_usd_eur_rate

        usd = token_cost_usd(
            self.config.price, usage.input_tokens, usage.output_tokens, 0, datetime.now(UTC)
        )
        eur = usd * get_cached_usd_eur_rate()
        await record_instance_llm_spend(
            surface=SURFACE,
            model_name=self.config.model,
            tokens_in=usage.input_tokens,
            tokens_out=usage.output_tokens,
        )
        self.ledger.add(eur)
        return eur

    async def _batch(
        self, questions: Mapping[str, ChoiceQuestion], state: object, answer: Answer
    ) -> None:
        from src.infrastructure.llm.usage_guard import enforce_usage_limit

        assert self.client is not None
        self.ledger.check(self._upper_eur(questions, state))
        await enforce_usage_limit(None, layer=SURFACE)
        usage: DecisionUsage | None = None
        try:
            result = await self.client.choose_many(
                model=self.config.model,
                state=state,
                questions=dict(questions),
                timeout_seconds=self.config.timeout_seconds,
            )
            usage = result.usage
            for key, choice in result.answers.items():
                answer.labels[key] = choice.choice
                answer.confidence[key] = float(choice.confidence)
        except TypeSafeError as exc:
            usage = exc.usage
            answer.error = answer.error or exc.code
        answer.calls += 1
        if usage is not None:
            answer.input_tokens += usage.input_tokens
            answer.output_tokens += usage.output_tokens
            answer.cost_eur += await self._charge(usage)

    async def decide(
        self, questions: Mapping[str, ChoiceQuestion], state: object, case_id: str
    ) -> Answer:
        """Answer every question; batches of the same state are sent concurrently."""
        del case_id
        answer = Answer()
        keys = list(questions)
        batches = [
            {key: questions[key] for key in keys[i : i + MAX_QUESTIONS]}
            for i in range(0, len(keys), MAX_QUESTIONS)
        ]
        started = time.perf_counter()
        await asyncio.gather(*(self._batch(batch, state, answer) for batch in batches))
        answer.latency_ms = (time.perf_counter() - started) * 1000
        return answer


class GenerativeEngine:
    """The deployment's configured generative slot, through the semantic simulation probe."""

    name = "generative"

    def __init__(self, ledger: SpendLedger, slot: str = "query_analyzer") -> None:
        self.ledger = ledger
        self.slot = slot
        self.probe: Any = None
        self.runtime: Any = None

    async def __aenter__(self) -> GenerativeEngine:
        from scripts.semantic_simulation import runtime as probe

        # The current mechanism replays the personal-reference extractor too.
        probe.SLOTS = tuple(dict.fromkeys((*probe.SLOTS, "memory_reference_extraction")))
        self.probe = probe
        self.runtime = await probe.prepare(self.ledger.remaining())
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def describe(self) -> dict[str, object]:
        """What ran, read from the database configuration."""
        return {"slot": self.slot, **self.runtime.configuration[self.slot]}

    async def invoke_tool(
        self,
        slot: str,
        prompt: str,
        tool: dict[str, object],
        tool_name: str,
        case_id: str,
    ) -> tuple[dict[str, object] | None, Answer]:
        """One forced tool call; the spend delta is settled in the cumulative ledger."""
        answer = Answer(calls=1)
        before = self.runtime.spent_eur
        # The probe refuses a call whose upper bound crosses ITS budget: keep that
        # budget equal to what the whole qualification still has (JEV spends too).
        self.runtime.budget_eur = self.runtime.spent_eur + self.ledger.remaining()
        started = time.perf_counter()
        args: dict[str, object] | None = None
        try:
            response = await self.probe.invoke(
                self.runtime,
                slot,
                single_call_messages(prompt),
                case=case_id,
                tools=[tool],
                tool_choice=tool_name,
            )
            calls = response.tool_calls or []
            raw = calls[0].get("args") if calls else None
            args = raw if isinstance(raw, dict) else None
            if args is None:
                answer.error = "no_tool_call"
        except Exception as exc:  # noqa: BLE001 - a measurement records every failure
            answer.error = type(exc).__name__
        answer.latency_ms = (time.perf_counter() - started) * 1000
        answer.cost_eur = self.runtime.spent_eur - before
        self.ledger.add(answer.cost_eur)
        return args, answer

    async def decide(
        self, questions: Mapping[str, ChoiceQuestion], state: object, case_id: str
    ) -> Answer:
        """Answer every question in one forced tool call with the same allowed keys."""
        self.ledger.check(0.0)
        args, answer = await self.invoke_tool(
            self.slot, render_prompt(questions, state), answer_tool(questions), "answer", case_id
        )
        if args is not None:
            for key, question in questions.items():
                value = args.get(key)
                if isinstance(value, str) and value in question.criteria:
                    answer.labels[key] = value
                else:
                    answer.error = answer.error or "invalid_answer"
        return answer


def fold(text: str) -> str:
    """The guard's comparison form (whitespace collapsed, case folded)."""
    return " ".join(text.split()).casefold()


class CurrentEngine:
    """What LIA does today for each decision, replayed on the same cases."""

    name = "current"

    def __init__(self, generative: GenerativeEngine) -> None:
        self.generative = generative

    def describe(self) -> dict[str, object]:
        """The mechanisms replayed."""
        return {
            "d1": "every resolved value is read as a person's name (param_guard before ADR-120 amendment)",
            "d3": "the real query analyzer prompt and schema over the full native menu",
            "d4": "Contact only: the real personal-reference extraction (non-empty means Contact)",
            "d5": "the guard before the amendment: refused iff the value equals a resolved value",
        }

    @staticmethod
    def d1(case_state: Mapping[str, object]) -> Answer:
        """Today every resolved value is a person's name for the guard."""
        del case_state
        return Answer(labels={"answer": "person_name"})

    @staticmethod
    def d5(case: Any) -> Answer:
        """Today the guard refuses a value equal to any value resolved this turn."""
        resolved = case.meta.get("resolved_values") or []
        value = str(case.state.get("value", ""))
        refused = isinstance(resolved, list) and fold(value) in {fold(str(v)) for v in resolved}
        return Answer(labels={"answer": "no" if refused else "yes"})

    async def d3(self, case: Any, menu: Sequence[Mapping[str, str]]) -> Answer:
        """The real analyzer decision, as the taxonomy qualification replays it."""
        from scripts.semantic_simulation.taxonomy_corpus import TaxonomyRoutingCase
        from scripts.semantic_simulation.taxonomy_run import _decision

        routing_case = TaxonomyRoutingCase(
            name=case.id,
            query=str(case.state["query"]),
            required_domains=tuple(sorted(case.required)),
            acceptable_domains=tuple(sorted(case.optional)),
            expected_primary=case.gold,
            # The backend's canonical Chinese code (normalize_language).
            language="zh-CN" if case.language == "zh" else case.language,  # type: ignore[arg-type]
        )
        self.generative.ledger.check(0.0)
        before = self.generative.runtime.spent_eur
        started = time.perf_counter()
        answer = Answer(calls=1)
        try:
            decision = await _decision(self.generative.runtime, routing_case, list(menu))
        except Exception as exc:  # noqa: BLE001 - a measurement records every failure
            decision = {"failures": [type(exc).__name__]}
        answer.latency_ms = (time.perf_counter() - started) * 1000
        answer.cost_eur = self.generative.runtime.spent_eur - before
        self.generative.ledger.add(answer.cost_eur)
        primary = decision.get("primary")
        if not isinstance(primary, str):
            answer.error = ",".join(map(str, decision.get("failures") or ["no_primary"]))
            return answer
        selected = {primary, *[str(d) for d in decision.get("secondary") or []]}
        answer.labels["primary"] = primary
        for item in menu:
            name = str(item["name"])
            answer.labels[f"rel_{name}"] = "yes" if name in selected else "no"
        return answer

    async def d4(self, case: Any) -> Answer:
        """Contact evidence from the real extractor: a non-empty extraction means Contact."""
        from langchain_core.utils.function_calling import convert_to_openai_tool

        from src.domains.agents.prompts.prompt_loader import load_prompt
        from src.domains.agents.services.analysis.memory_resolver import _ReferenceList

        prompt = str(load_prompt("memory_reference_extraction_prompt", version="v1")).format(
            query=str(case.state["query"])
        )
        tool = convert_to_openai_tool(_ReferenceList, strict=False)
        tool_name = str(tool["function"]["name"])
        self.generative.ledger.check(0.0)
        args, answer = await self.generative.invoke_tool(
            "memory_reference_extraction", prompt, tool, tool_name, case.id
        )
        if args is not None:
            references = args.get("references")
            found = isinstance(references, list) and any(
                isinstance(r, str) and r.strip() for r in references
            )
            answer.labels["needs_Contact"] = "yes" if found else "no"
        return answer
