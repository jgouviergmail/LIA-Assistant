"""Shipped question vs its reversed-option twin vs the aligned candidate, on the usage's own corpora.

Inside the dev API container, explicitly opted in (paid, a few cents):
    python -m scripts.jev_alignment.compare --usage memory_presence
Every state is CAPTURED from the product function that builds it (the native
call is intercepted), then the three variants are asked on that same state
through the documented request. Rows land in /app/.tmp/jev-alignment/.
"""

import argparse
import asyncio
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from uuid import UUID

from scripts.jev_alignment import candidates as cand
from scripts.jev_semantic.engines import SpendLedger
from scripts.jev_semantic.run_v2 import NativeJevEngine

OUT = Path("/app/.tmp/jev-alignment")
CORPORA = OUT / "corpora"
FIXTURES = Path("/app/tests/fixtures")
OWNER = UUID(int=1)


@dataclass
class Item:
    """One judged state with its three question variants and its gold."""

    usage: str
    id: str
    split: str
    state: Any
    current: dict[str, dict[str, Any]]
    candidate: dict[str, dict[str, Any]]
    candidate_state: Any = None
    gold: dict[str, Any] = field(default_factory=dict)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(question: Any) -> dict[str, Any]:
    return (
        {"type": "choice", **question.model_dump()}
        if hasattr(question, "model_dump")
        else dict(question)
    )


def reversed_specs(specs: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The same questions with every Choice's options in reverse order."""
    out = {}
    for key, spec in specs.items():
        if spec.get("type", "choice") == "choice":
            spec = {**spec, "criteria": dict(reversed(list(spec["criteria"].items())))}
        out[key] = spec
    return out


class Capture:
    """Stands in for the native call: records what the product would send."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def one(self, **kwargs: Any) -> Any:
        from src.infrastructure.llm.decision_types import DecisionAttempt

        self.calls.append(
            {
                "state": kwargs["state"],
                "questions": {"selection": kwargs["question"]},
                "usage": kwargs.get("usage"),
            }
        )
        return DecisionAttempt(outcome="captured")

    async def many(self, **kwargs: Any) -> Any:
        from src.infrastructure.llm.decision_types import DecisionAttempt

        self.calls.append(
            {
                "state": kwargs["state"],
                "questions": kwargs["questions"],
                "usage": kwargs.get("usage"),
            }
        )
        return DecisionAttempt(outcome="captured")


async def _noop(*args: Any, **kwargs: Any) -> None:
    return None


# ------------------------------------------------------------------ adapters
def memory_presence() -> list[Item]:
    from src.domains.agents.prompts.prompt_loader import load_prompt

    current = {
        "selection": json.loads(load_prompt("jev_memory_reference_presence_question", version="v1"))
    }
    items = []
    for split, name in (
        ("calibration", "jev-memory-presence-calibration.json"),
        ("holdout", "jev-memory-presence-independent.json"),
    ):
        for case in _load(CORPORA / name)["cases"]:
            items.append(
                Item(
                    "memory_presence",
                    case["id"],
                    split,
                    {"query": case["state"]["query"], "account_owner_identity_known": True},
                    current,
                    cand.memory_presence(),
                    gold={"absent": case["expected"] == "absent"},
                )
            )
    return items


def hitl_rejection() -> list[Item]:
    from src.domains.agents.prompts.prompt_loader import load_prompt

    current = {"selection": json.loads(load_prompt("jev_hitl_rejection_question", version="v1"))}
    return [
        Item(
            "hitl_rejection",
            case["id"],
            "calibration" if case["split"] == "calibration" else "holdout",
            case["state"],
            current,
            cand.hitl_rejection(),
            gold={"reject": bool(case["expected_rejection"]), "category": case["category"]},
        )
        for case in _load(CORPORA / "jev-hitl-rejection-corpus.json")["cases"]
    ]


async def initiative() -> list[Item]:
    from scripts.measure_jev_gates import initiative_prompt
    from src.domains.agents.nodes import jev_initiative

    items = []
    for split, name in (
        ("calibration", "jev_gate_cases.json"),
        ("holdout", "jev_gate_holdout.json"),
    ):
        for case in _load(FIXTURES / name)["initiative"]:
            capture = Capture()
            with (
                patch.object(jev_initiative, "choose_with_jev", capture.one),
                patch.object(jev_initiative, "_incomplete_attempt", capture.one),
                patch.object(jev_initiative, "record_action", _noop),
            ):
                await jev_initiative.choose_empty_initiative(
                    initiative_prompt(case), str(OWNER), "alignment"
                )
            call = capture.calls[0]
            items.append(
                Item(
                    "initiative",
                    f"{split}:{case['id']}",
                    split,
                    call["state"],
                    {k: _dump(q) for k, q in call["questions"].items()},
                    cand.initiative(),
                    gold={"utility": bool(case["utility"])},
                )
            )
    return items


def initiative_structured() -> list[Item]:
    """The production state shape (`initiative_policy` + `context`), one split only.

    The 30 structured cases were built for an earlier format study and carry no
    calibration split of their own; with the 4 canonical states (the exact shape
    `named_initiative_state` produces), they VERIFY the threshold chosen on the
    legacy-shape calibration, they never choose one.
    """
    from src.domains.agents.prompts.prompt_loader import load_prompt

    current = {"selection": json.loads(load_prompt("jev_initiative_question", version="v1"))}
    items = [
        Item(
            "initiative",
            f"structured:{case['id']}",
            "holdout",
            case["candidate_state"],
            current,
            cand.initiative(),
            gold={"utility": case["expected_answers"]["selection"] != "no_utility"},
        )
        for case in _load(CORPORA / "jev-initiative-structured-cases.json")["cases"]
    ]
    items += [
        Item(
            "initiative",
            f"canonical:{case['id']}",
            "holdout",
            case["native_state"],
            current,
            cand.initiative(),
            gold={"utility": bool(case["useful"])},
        )
        for case in _load(CORPORA / "jev-initiative-canonical-cases.json")["cases"]
    ]
    return items


async def consultation() -> list[Item]:
    from src.core.time_utils import now_utc
    from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
    from src.domains.agents.context.runtime_context import LiaRuntimeContext
    from src.domains.agents.services.planner import jev_consultation
    from src.domains.agents.services.planner.jev_bounded_consultation import (
        bounded_paths,
        wants_bounded_path,
    )
    from src.domains.agents.services.smart_catalogue_service import FilteredCatalogue

    items = []
    corpora = (
        ("calibration", "jev_gate_cases.json"),
        ("calibration", "jev_bounded_cases.json"),
        ("holdout", "jev_gate_holdout.json"),
        ("holdout", "jev_bounded_holdout.json"),
    )
    for split, name in corpora:
        for case in _load(FIXTURES / name)["consultation"]:
            qi = QueryIntelligence(
                original_query=case["query"],
                english_query=case["query"],
                immediate_intent="search",
                immediate_confidence=0.99,
                user_goal=UserGoal.FIND_INFORMATION,
                goal_reasoning="Read",
                domains=[case["domain"]],
                primary_domain=case["domain"],
                confidence=0.99,
                has_temporal_reference=case.get("temporal", False),
            )
            paths = {
                k: v for k, v in jev_consultation.READ_PATHS.items() if v.domain == case["domain"]
            }
            if wants_bounded_path(qi):
                paths = bounded_paths(qi, "Europe/Paris", now_utc())
            catalogue = FilteredCatalogue(
                [{"name": v.tool} for v in paths.values()],
                len(paths),
                0,
                [case["domain"]],
                ["search"],
            )
            capture = Capture()
            context = LiaRuntimeContext(
                user_id=OWNER, thread_id="t", conversation_id="t", timezone="Europe/Paris"
            )
            with (
                patch.object(jev_consultation, "runtime_context_if_running", return_value=context),
                patch.object(jev_consultation, "available_paths", return_value=paths),
                patch.object(jev_consultation, "choose_with_jev", capture.one),
                patch.object(jev_consultation, "_record_outcome", _noop),
            ):
                await jev_consultation.try_consultation_plan(qi, {}, catalogue, journal_context="")
            if not capture.calls:
                continue  # the product offers no candidate: no native call to compare
            call = capture.calls[0]
            question = call["questions"]["selection"]
            offered = {k: v for k, v in question.criteria.items() if k != "other"}
            bounded = str(call["usage"]).endswith("consultation_bounded")
            items.append(
                Item(
                    "consultation",
                    f"{name}:{case['id']}",
                    split,
                    call["state"],
                    {"selection": _dump(question)},
                    cand.consultation(offered),
                    candidate_state=cand.consultation_state(call["state"]),
                    gold={"expected": case["expected"], "bounded": bounded},
                )
            )
    return items


def radio() -> list[Item]:
    from src.domains.radio.facts import FactKind, FactPack, RadioFact, Sensitivity, SourceRef
    from src.domains.radio.formats import RadioFormat, RadioRole
    from src.domains.radio.jev_checker import verifier_request
    from src.domains.radio.script import LineKind, RadioDelivery, ScriptPart
    from src.domains.radio.verification import VerifiedLine

    items = []
    for split, name in (
        ("calibration", "jev_radio_cases.json"),
        ("holdout", "jev_radio_holdout.json"),
    ):
        for case in _load(FIXTURES / name):
            pack = FactPack(
                format=RadioFormat.BULLETIN,
                facts=tuple(
                    RadioFact(
                        **fact,
                        key=f"synthetic:{fact['id']}",
                        kind=FactKind.NEWS,
                        sensitivity=Sensitivity.PUBLIC,
                        source=SourceRef(label="Example News"),
                    )
                    for fact in case["facts"]
                ),
            )
            lines = tuple(
                VerifiedLine(
                    RadioRole.ANCHOR,
                    ScriptPart.BODY,
                    LineKind(line["kind"]),
                    line["text"],
                    RadioDelivery(),
                    tuple(line["refs"]),
                )
                for line in case["lines"]
            )
            request = verifier_request(lines, pack, "Radio 42")
            if request is None:
                continue
            state, questions = request
            items.append(
                Item(
                    "radio",
                    f"{split}:{case['id']}",
                    split,
                    state,
                    {k: _dump(q) for k, q in questions.items()},
                    cand.radio(list(questions)),
                    gold={"unsupported": sorted(f"line{i}" for i in case["expected_unsupported"])},
                )
            )
    return items


async def collections() -> list[Item]:
    from src.domains.agents.data_registry.models import (
        RegistryItem,
        RegistryItemMeta,
        RegistryItemType,
    )
    from src.domains.agents.display import jev_qualification

    items = []
    corpora = (
        ("calibration", "jev_collection_cases.json"),
        ("calibration", "jev_extra_collection_cases.json"),
        ("holdout", "jev_extra_collection_holdout.json"),
    )
    gold_map = {"no_match": "non_match", "insufficient": "unknown"}
    for split, name in corpora:
        for case in _load(FIXTURES / name):
            registry = [
                RegistryItem(
                    id=item["id"],
                    type=RegistryItemType(item["type"]),
                    payload=item["payload"],
                    meta=RegistryItemMeta(source=item.get("source", "synthetic"), domain="test"),
                )
                for item in case["items"]
            ]
            capture = Capture()
            with patch.object(jev_qualification, "choose_many_with_jev", capture.many):
                await jev_qualification.qualify_collection(
                    user_id=OWNER, run_id="alignment", query=case["query"], items=registry
                )
            for batch_index, call in enumerate(capture.calls):
                keys = list(call["questions"])
                document = any(
                    "document_excerpt" in json.dumps(q.instructions)
                    for q in call["questions"].values()
                )
                items.append(
                    Item(
                        "collections",
                        f"{name}:{case['id']}:{batch_index}",
                        split,
                        call["state"],
                        {k: _dump(q) for k, q in call["questions"].items()},
                        cand.collection(keys, document),
                        gold={
                            k: gold_map.get(
                                case["items"][int(k[1:])]["gold"], case["items"][int(k[1:])]["gold"]
                            )
                            for k in keys
                        },
                    )
                )
    return items


async def hitl_exclusion() -> list[Item]:
    from src.domains.agents.services.hitl import jev_item_filter as module

    items = []

    async def capture_case(
        item_list: list[dict[str, Any]], criterion: str
    ) -> dict[str, Any] | None:
        capture = Capture()
        with (
            patch.object(
                module, "runtime_context_if_running", return_value=SimpleNamespace(user_id=OWNER)
            ),
            patch.object(module, "choose_many_with_jev", capture.many),
            patch.object(module, "_record_result", _noop),
        ):
            await module.try_filter_items(item_list, criterion, "alignment")
        return capture.calls[0] if capture.calls else None

    for split, name in (
        ("calibration", "jev_hitl_cases.json"),
        ("holdout", "jev_hitl_holdout.json"),
    ):
        for case in _load(FIXTURES / name):
            call = await capture_case(case["items"], case["criterion"])
            if call is None:
                continue
            keys = [k for k in call["questions"] if k.startswith("item_")]
            items.append(
                Item(
                    "hitl_exclusion",
                    f"{name}:{case['id']}",
                    split,
                    call["state"],
                    {k: _dump(q) for k, q in call["questions"].items()},
                    cand.hitl_exclusion(keys),
                    gold={"keep": case["keep"]},
                )
            )
    for case in _load(CORPORA / "jev-hitl-scope-heldout.json")["cases"]:
        state = case["state"]
        ordered = [state["items"][f"item_{i}"] for i in range(len(state["items"]))]
        call = await capture_case(ordered, state["exclude_criteria"])
        if call is None:
            continue
        expected = case["expected_answers"]
        keys = [k for k in call["questions"] if k.startswith("item_")]
        firm = expected["reference_scope"] == "clear" and all(
            expected[k] in {"keep", "exclude"} for k in keys
        )
        items.append(
            Item(
                "hitl_exclusion",
                f"scope:{case['id']}",
                "holdout",
                call["state"],
                {k: _dump(q) for k, q in call["questions"].items()},
                cand.hitl_exclusion(keys),
                gold={
                    "keep": (
                        [i for i, k in enumerate(keys) if expected[k] == "keep"] if firm else None
                    )
                },
            )
        )
    return items


ADAPTERS: dict[str, Callable[[], Any]] = {
    "memory_presence": memory_presence,
    "hitl_rejection": hitl_rejection,
    "initiative": initiative,
    "initiative_structured": initiative_structured,
    "consultation": consultation,
    "radio": radio,
    "collections": collections,
    "hitl_exclusion": hitl_exclusion,
}


async def main(args: argparse.Namespace) -> None:
    from src.infrastructure.database.registry import import_all_models
    from src.infrastructure.startup.caches import (
        init_config_caches,
        init_pricing_caches,
        init_redis,
    )

    import_all_models()
    await init_redis()
    await init_pricing_caches()
    await init_config_caches()
    built = ADAPTERS[args.usage]()
    items: list[Item] = await built if asyncio.iscoroutine(built) else built
    items = items[: args.limit or None]
    print(f"{args.usage}: {len(items)} states ({sum(i.split == 'holdout' for i in items)} holdout)")
    if args.dry_run:
        print(json.dumps(asdict(items[0]), ensure_ascii=False, default=str)[:3000])
        return
    ledger = SpendLedger(OUT / "spend.json", args.ceiling_eur)
    output = OUT / f"rows-{args.usage}.json"
    rows: list[dict[str, Any]] = []
    async with NativeJevEngine(ledger) as engine:
        for item in items:
            variants = {
                "current": (item.state, item.current),
                "current_rev": (item.state, reversed_specs(item.current)),
                "candidate": (
                    item.candidate_state if item.candidate_state is not None else item.state,
                    item.candidate,
                ),
            }
            for repeat in range(args.repetitions):
                for variant, (state, specs) in variants.items():
                    answer = await engine.decide(specs, state, item.id)
                    rows.append(
                        {
                            "usage": item.usage,
                            "id": item.id,
                            "split": item.split,
                            "variant": variant,
                            "repeat": repeat,
                            "gold": item.gold,
                            "keys": list(specs),
                            **asdict(answer),
                        }
                    )
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(
                    {"saved_at": datetime.now(UTC).isoformat(), "rows": rows},
                    ensure_ascii=False,
                    indent=1,
                )
                + "\n",
                encoding="utf-8",
            )
    print(f"saved {output} — alignment spend {ledger.spent:.4f} EUR")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usage", choices=sorted(ADAPTERS), required=True)
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--ceiling-eur", type=float, default=1.0)
    parser.add_argument("--dry-run", action="store_true")
    asyncio.run(main(parser.parse_args()))
