"""Paid synthetic replay through the production projection, prompt and qualification.

No live account records or ledger are touched. Run from apps/api with PYTHONPATH=.
and --prompt-key. Unknown is an abstention; a confident wrong verdict is an error.
"""

import argparse
import asyncio
import getpass
import json
from pathlib import Path
from statistics import median
from time import perf_counter
from unittest.mock import patch
from uuid import UUID

import httpx

from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType
from src.domains.agents.display import jev_qualification
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.typesafe_client import TypeSafeClient, TypeSafeError


async def measure(
    output: Path, key: str, repetitions: int, cases_path: Path, model: str = "jev-1.13.0"
) -> None:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    records = []
    async with httpx.AsyncClient() as http:
        client = TypeSafeClient(http, key)
        for repeat in range(repetitions):
            for case in cases:
                row = {"id": case["id"], "repeat": repeat}

                async def native(*, record=row, **kwargs):
                    try:
                        result = await client.choose_many(
                            model=model,
                            state=kwargs["state"],
                            questions=kwargs["questions"],
                            timeout_seconds=5,
                        )
                        record["tokens"] = result.usage.model_dump()
                        record["answers"] = {
                            name: value.model_dump() for name, value in result.answers.items()
                        }
                        return DecisionAttempt(outcome="success", answers=result.answers)
                    except TypeSafeError as exc:
                        record["error"] = exc.code
                        if exc.usage is not None:
                            record["tokens"] = exc.usage.model_dump()
                        return DecisionAttempt(outcome=exc.code)

                items = [
                    RegistryItem(
                        id=item["id"],
                        type=RegistryItemType(item["type"]),
                        payload=item["payload"],
                        meta=RegistryItemMeta(
                            source=item.get("source", "synthetic"), domain="test"
                        ),
                    )
                    for item in case["items"]
                ]
                started = perf_counter()
                with patch.object(jev_qualification, "choose_many_with_jev", native):
                    result = await jev_qualification.qualify_collection(
                        user_id=UUID(int=1), run_id="synthetic", query=case["query"], items=items
                    )
                row["latency_ms"] = round((perf_counter() - started) * 1000, 2)
                expected = {
                    item["id"]: {"no_match": "non_match", "insufficient": "unknown"}.get(
                        item["gold"], item["gold"]
                    )
                    for item in case["items"]
                }
                row["judgments"] = (
                    [
                        {"id": item.id, "predicted": item.verdict, "expected": expected[item.id]}
                        for item in result.items
                    ]
                    if result
                    else []
                )
                records.append(row)
                output.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    judgments = [item for row in records for item in row["judgments"]]
    print(
        json.dumps(
            {
                "calls": len(records),
                "judgments": len(judgments),
                "firm": sum(item["predicted"] != "unknown" for item in judgments),
                "wrong_firm": [
                    item
                    for item in judgments
                    if item["predicted"] != "unknown" and item["predicted"] != item["expected"]
                ],
                "median_ms": median(row["latency_ms"] for row in records),
                "input_tokens": sum(
                    row.get("tokens", {}).get("input_tokens", 0) for row in records
                ),
            }
        )
    )


async def configured_measure(args):
    from src.core.config import settings
    from src.domains.llm_config.jev_registry import JevUsage
    from src.domains.llm_config.jev_settings import read_configuration
    from src.infrastructure.database import get_db_context
    from src.infrastructure.database.registry import import_all_models

    if settings.environment != "development":
        raise RuntimeError("Paid synthetic probe requires development configuration")
    import_all_models()
    async with get_db_context() as db:
        _, config = await read_configuration(db, JevUsage.FILTER_REMINDER)
    assert config
    await measure(
        args.output, config.api_key.get_secret_value(), args.repetitions, args.cases, config.model
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(__file__).parents[1] / "tests/fixtures/jev_collection_cases.json",
    )
    parser.add_argument("--repetitions", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--configured-dev", action="store_true")
    args = parser.parse_args()
    if args.configured_dev:
        asyncio.run(configured_measure(args))
    else:
        asyncio.run(
            measure(
                args.output,
                getpass.getpass("TypeSafe key (not stored): "),
                args.repetitions,
                args.cases,
            )
        )
