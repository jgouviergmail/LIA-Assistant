"""Version 2 of the qualification: the vendor's documented practice, judged on fresh corpora.

Inside the dev API container, explicitly opted in (paid):
    python -m scripts.jev_semantic.run_v2 --decision d5 --split independent --ceiling-eur 5
d1 runs twice (``v2`` and ``v2rev``, the options in reverse order) to measure
Choice's documented first-option bias. d3, d4 and d5 are judged on the fresh
independent corpora (``corpus_v2``), calibrated on version 1's calibration split.
Rows land beside version 1's, in /app/.tmp/jev-semantic/, variant ``v2``/``v2rev``.
"""

import argparse
import asyncio
import json
import time
from collections.abc import Mapping
from contextlib import AsyncExitStack, ExitStack
from datetime import UTC, datetime
from typing import Any

import httpx

from scripts.jev_semantic import corpus_d1, corpus_d2, corpus_d3, corpus_d4, corpus_d5, corpus_v2
from scripts.jev_semantic import questions_v2 as q2
from scripts.jev_semantic.cases import Case, Split, validate
from scripts.jev_semantic.engines import (
    SURFACE,
    Answer,
    CurrentEngine,
    GenerativeEngine,
    SpendLedger,
    fold,
)
from scripts.jev_semantic.native import NativeError, system_one
from scripts.jev_semantic.run import RESULTS, _save, registry_vocabulary, row

#: The application client's own per-request bound; a larger set is split only if refused.
SPLIT_SIZE = 24


class NativeJevEngine:
    """The decision provider through the documented request (Choice and Noul)."""

    name = "jev"

    def __init__(self, ledger: SpendLedger) -> None:
        self.ledger = ledger
        self.config: Any = None
        self.http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> NativeJevEngine:
        from src.domains.llm_config.jev_registry import JevUsage
        from src.domains.llm_config.jev_settings import read_configuration
        from src.infrastructure.database import get_db_context

        async with get_db_context() as db:
            readiness, config = await read_configuration(db, JevUsage.MEMORY_REFERENCE_PRESENCE)
        if config is None:
            raise SystemExit(f"JEV is not ready on this deployment: {readiness}")
        self.config = config
        self.http = httpx.AsyncClient()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self.http is not None:
            await self.http.aclose()

    def describe(self) -> dict[str, object]:
        """What ran (no secret)."""
        return {
            "model": self.config.model,
            "timeout_seconds": self.config.timeout_seconds,
            "request": "documented System One, Choice and Noul",
        }

    def _upper_eur(self, specs: Mapping[str, q2.Spec], state: object) -> float:
        from src.infrastructure.cache.pricing_cache import get_cached_usd_eur_rate

        body = json.dumps({"state": state, "questions": specs}, ensure_ascii=False).encode()
        price = self.config.price
        usd = (
            len(body) * float(price.input_price) + 64 * len(specs) * float(price.output_price)
        ) / 1e6
        return usd * get_cached_usd_eur_rate()

    async def _charge(self, tokens_in: int, tokens_out: int) -> float:
        from src.domains.llm.pricing_service import token_cost_usd
        from src.domains.usage_limits.instance_spend import record_instance_llm_spend
        from src.infrastructure.cache.pricing_cache import get_cached_usd_eur_rate

        usd = token_cost_usd(self.config.price, tokens_in, tokens_out, 0, datetime.now(UTC))
        eur = usd * get_cached_usd_eur_rate()
        await record_instance_llm_spend(
            surface=SURFACE,
            model_name=self.config.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        self.ledger.add(eur)
        return eur

    async def _request(self, specs: dict[str, q2.Spec], state: object, answer: Answer) -> None:
        from src.infrastructure.llm.usage_guard import enforce_usage_limit

        assert self.http is not None
        self.ledger.check(self._upper_eur(specs, state))
        await enforce_usage_limit(None, layer=SURFACE)
        answer.calls += 1
        try:
            result = await system_one(
                self.http,
                self.config.api_key.get_secret_value(),
                self.config.model,
                state,
                specs,
                self.config.timeout_seconds,
            )
        except NativeError as exc:
            if exc.input_tokens or exc.output_tokens:
                answer.input_tokens += exc.input_tokens
                answer.output_tokens += exc.output_tokens
                answer.cost_eur += await self._charge(exc.input_tokens, exc.output_tokens)
            if exc.code.startswith("http_4") and len(specs) > SPLIT_SIZE:
                keys = list(specs)
                parts = [
                    {k: specs[k] for k in keys[i : i + SPLIT_SIZE]}
                    for i in range(0, len(keys), SPLIT_SIZE)
                ]
                answer.error = f"split_after_{exc.code}"
                await asyncio.gather(*(self._request(part, state, answer) for part in parts))
                return
            answer.error = answer.error or exc.code
            return
        answer.input_tokens += result.input_tokens
        answer.output_tokens += result.output_tokens
        answer.cost_eur += await self._charge(result.input_tokens, result.output_tokens)
        for key, raw in result.answers.items():
            if raw.get("type") == "noul" and isinstance(raw.get("noul"), int | float):
                p = float(raw["noul"])  # type: ignore[arg-type]
                answer.labels[key] = "yes" if p >= 0.5 else "no"
                answer.confidence[key] = abs(2 * p - 1)
                answer.confidence[f"{key}__p"] = p
            elif raw.get("type") == "choice" and isinstance(raw.get("choice"), str):
                answer.labels[key] = str(raw["choice"])
                answer.confidence[key] = float(raw.get("confidence") or 0.0)  # type: ignore[arg-type]
            else:
                answer.error = answer.error or f"unreadable_{key}"

    async def decide(self, specs: dict[str, q2.Spec], state: object, case_id: str) -> Answer:
        """Every question in ONE request (the documented function-calling layout)."""
        del case_id
        answer = Answer()
        started = time.perf_counter()
        await self._request(specs, state, answer)
        answer.latency_ms = (time.perf_counter() - started) * 1000
        return answer


class GenerativeV2(GenerativeEngine):
    """The configured generative slot, asked the SAME specs rendered as text."""

    async def decide(self, specs: dict[str, q2.Spec], state: object, case_id: str) -> Answer:  # type: ignore[override]
        """One forced tool call restricted to each question's allowed answers."""
        self.ledger.check(0.0)
        args, answer = await self.invoke_tool(
            self.slot, q2.render_prompt(specs, state), q2.answer_tool(specs), "answer", case_id
        )
        if args is not None:
            for key, spec in specs.items():
                allowed = ("yes", "no") if spec["type"] == "noul" else tuple(spec["criteria"])  # type: ignore[arg-type]
                value = args.get(key)
                if isinstance(value, str) and value in allowed:
                    answer.labels[key] = value
                else:
                    answer.error = answer.error or "invalid_answer"
        return answer


# ------------------------------------------------------------------ derivations
D5_KEYS = ("kind_verdict", "noul_verdict", "both_verdict")


def derive_d5(answer: Answer, case: Case) -> Answer:
    """The code's verdict from the judged kind, the direct Noul, and both (disagreement abstains)."""
    parameter_key = str(case.meta["parameter_key"])
    kind_verdict = q2.d5_kind_verdict(answer.labels.get("kind"), parameter_key)
    noul_verdict = answer.labels.get("fits")
    if kind_verdict is not None:
        answer.labels["kind_verdict"] = kind_verdict
        if "kind" in answer.confidence:
            answer.confidence["kind_verdict"] = answer.confidence["kind"]
    if noul_verdict is not None:
        answer.labels["noul_verdict"] = noul_verdict
        if "fits" in answer.confidence:
            answer.confidence["noul_verdict"] = answer.confidence["fits"]
    if kind_verdict is not None and noul_verdict is not None:
        answer.labels["both_verdict"] = kind_verdict
        agree = kind_verdict == noul_verdict
        if "kind" in answer.confidence and "fits" in answer.confidence:
            answer.confidence["both_verdict"] = (
                min(answer.confidence["kind"], answer.confidence["fits"]) if agree else 0.0
            )
        elif not agree:
            answer.confidence["both_verdict"] = 0.0
    return answer


def replay_d5(case: Case, planned: bool) -> Answer:
    """Today's guard, or the planned typed guard with PERFECT typing (an upper bound).

    The planned guard (Lot B) refuses a value equal to a resolved value TYPED as a
    person's name. The corpus states which resolved values are people only through
    the family, so this replay is an oracle: it is what Lot B can reach at best.
    """
    resolved = case.meta.get("resolved_values") or []
    value = fold(str(case.state.get("value", "")))
    equal = isinstance(resolved, list) and value in {fold(str(v)) for v in resolved}
    if planned:
        refused = equal and case.family in {"person_resolved", "homonym_person"}
    else:
        refused = equal
    verdict = "no" if refused else "yes"
    return Answer(labels=dict.fromkeys(D5_KEYS, verdict))


def derive_d2(answer: Answer, parents: Mapping[str, str | None]) -> Answer:
    """The chosen type's parent, for the confidence fallback to the category."""
    chosen = answer.labels.get("answer")
    parent = parents.get(chosen) if chosen else None
    if parent:
        answer.labels["answer_parent"] = parent
    return answer


# ------------------------------------------------------------------- the cases
def cases_for(decision: str, split: Split, menu: list[dict[str, str]] | None) -> tuple[Case, ...]:
    """Version 1's calibration split everywhere; fresh independent corpora for d3, d4, d5."""
    if decision == "d1":
        cases = corpus_d1.build(split)
        validate(cases, corpus_d1.LABELS)
        return cases
    if decision == "d2":
        _, _, parents = registry_vocabulary(aligned=False)
        cases = corpus_d2.build(split, parents)
        validate(cases, frozenset(parents))
        return cases
    if split == "calibration":
        if decision == "d3":
            cases = corpus_d3.build(split)
        elif decision == "d4":
            cases = corpus_d4.build(split)
        else:
            cases = tuple(
                Case(**{**c.__dict__, "meta": {**c.meta, "parameter_key": key}})
                for c, key in zip(
                    corpus_d5.build(split), (r[3] for r in corpus_d5.CALIBRATION), strict=True
                )
            )
    else:
        cases = corpus_v2.build(decision)  # type: ignore[arg-type]
    if decision == "d3":
        assert menu is not None
        validate(cases, frozenset(item["name"] for item in menu))
    elif decision == "d4":
        validate(cases, corpus_d4.LABELS)
    else:
        validate(cases, corpus_d5.LABELS)
    return cases


def specs_for(
    decision: str, menu: list[dict[str, str]] | None, reverse: bool = False
) -> dict[str, q2.Spec]:
    """The decision's version 2 questions."""
    if decision == "d1":
        return q2.d1_specs(reverse)
    if decision == "d2":
        concrete, _, _ = registry_vocabulary(aligned=False)
        return q2.d2_specs(concrete)
    if decision == "d3":
        assert menu is not None
        return q2.d3_specs(menu)
    if decision == "d4":
        return q2.d4_specs()
    return q2.d5_specs()


async def main(args: argparse.Namespace) -> None:
    """Run version 2 over one split, saving after every case."""
    from src.infrastructure.database.registry import import_all_models
    from src.infrastructure.startup.caches import (
        init_config_caches,
        init_pricing_caches,
        init_redis,
    )

    import_all_models()
    engines = [e for e in args.engines.split(",") if e]
    variant = "v2rev" if args.reverse else "v2"
    with ExitStack() as menus:
        menu: list[dict[str, str]] | None = None
        if args.decision == "d3":
            from scripts.semantic_simulation.taxonomy_fixtures import full_domain_menu

            menu = list(menus.enter_context(full_domain_menu("native")))
        cases = cases_for(args.decision, args.split, menu)[: args.limit or None]
        specs = specs_for(args.decision, menu, args.reverse)
        size = len(json.dumps(specs, ensure_ascii=False).encode())
        print(
            f"{args.decision}/{args.split}/{variant}: {len(cases)} cases, {len(specs)} questions, ~{size} bytes"
        )
        if args.dry_run:
            return
        _, _, parents = (
            registry_vocabulary(aligned=False) if args.decision == "d2" else (None, None, {})
        )
        await init_redis()
        await init_pricing_caches()
        await init_config_caches()
        ledger = SpendLedger(RESULTS / args.ledger, args.ceiling_eur)
        output = RESULTS / f"{args.decision}-{args.split}-{variant}-{'-'.join(engines)}.json"
        report: dict[str, object] = {
            "started_at": datetime.now(UTC).isoformat(),
            "decision": args.decision,
            "split": args.split,
            "variant": variant,
            "corpus": (
                "corpus_v2"
                if args.split == "independent" and args.decision in {"d3", "d4", "d5"}
                else "v1"
            ),
            "engines": {},
            "rows": [],
        }
        rows: list[dict[str, object]] = report["rows"]  # type: ignore[assignment]
        async with AsyncExitStack() as stack:
            jev = (
                await stack.enter_async_context(NativeJevEngine(ledger))
                if "jev" in engines
                else None
            )
            needs_generative = "generative" in engines or (
                "current" in engines and args.decision in {"d3", "d4"}
            )
            generative = (
                await stack.enter_async_context(GenerativeV2(ledger)) if needs_generative else None
            )
            current = CurrentEngine(generative) if "current" in engines else None  # type: ignore[arg-type]
            if jev is not None:
                report["engines"]["jev"] = jev.describe()  # type: ignore[index]
            if generative is not None and "generative" in engines:
                report["engines"]["generative"] = generative.describe()  # type: ignore[index]
            if current is not None:
                report["engines"]["current"] = current.describe()  # type: ignore[index]
            for case in cases:
                passes = [(jev, args.repetitions)] if jev else []
                if generative is not None and "generative" in engines:
                    passes.append((generative, 1))
                for engine, repetitions in passes:
                    for repeat in range(repetitions):
                        answer = await engine.decide(specs, case.state, case.id)  # type: ignore[union-attr]
                        if args.decision == "d5":
                            answer = derive_d5(answer, case)
                        elif args.decision == "d2":
                            answer = derive_d2(answer, parents)  # type: ignore[arg-type]
                        rows.append(row(case, engine.name, variant, repeat, answer))  # type: ignore[union-attr]
                if current is not None and args.decision != "d2" and not args.reverse:
                    if args.decision == "d1":
                        rows.append(row(case, "current", variant, 0, current.d1(case.state)))
                    elif args.decision == "d5":
                        rows.append(
                            row(case, "current", variant, 0, replay_d5(case, planned=False))
                        )
                        rows.append(row(case, "lot_b", variant, 0, replay_d5(case, planned=True)))
                    elif args.decision == "d3":
                        assert menu is not None
                        rows.append(row(case, "current", variant, 0, await current.d3(case, menu)))
                    else:
                        rows.append(row(case, "current", variant, 0, await current.d4(case)))
                report["spent_eur_cumulative"] = ledger.spent
                _save(output, report)
        print(f"saved {output} — cumulative spend {ledger.spent:.4f} EUR")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision", choices=("d1", "d2", "d3", "d4", "d5"), required=True)
    parser.add_argument("--split", choices=("calibration", "independent"), required=True)
    parser.add_argument("--engines", default="jev,generative,current")
    parser.add_argument(
        "--repetitions", type=int, default=2, help="JEV repetitions (generative: 1)"
    )
    parser.add_argument("--reverse", action="store_true", help="d1: the options in reverse order")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--ceiling-eur", type=float, default=5.0)
    parser.add_argument(
        "--ledger",
        default="spend.json",
        help="spend file; version 2 keeps its own (spend_v2.json) so it may run beside version 1",
    )
    parser.add_argument("--dry-run", action="store_true")
    asyncio.run(main(parser.parse_args()))
