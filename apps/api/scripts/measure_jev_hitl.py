"""Replay synthetic exclusions through the real native consumer, without applying them."""

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import httpx

from src.core.config import settings
from src.domains.agents.services.hitl import jev_item_filter as module
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_settings import read_configuration
from src.infrastructure.database import get_db_context
from src.infrastructure.database.registry import import_all_models
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.typesafe_client import TypeSafeClient, TypeSafeError


async def main(cases_path: Path, output: Path):
    if settings.environment != "development":
        raise RuntimeError("Paid synthetic probe requires development configuration")
    import_all_models()
    async with get_db_context() as db:
        _, config = await read_configuration(db, JevUsage.HITL_EXCLUSION)
    assert config
    rows = []
    async with httpx.AsyncClient() as http:
        client = TypeSafeClient(http, config.api_key.get_secret_value())
        for repeat in range(2):
            for case in json.loads(cases_path.read_text(encoding="utf-8")):
                row = {"id": case["id"], "repeat": repeat, "expected": case["keep"]}

                async def choose(row=row, **kwargs):
                    try:
                        result = await client.choose_many(
                            model=config.model,
                            state=kwargs["state"],
                            questions=kwargs["questions"],
                            timeout_seconds=3,
                        )
                        row["answers"] = {k: v.model_dump() for k, v in result.answers.items()}
                        row["usage"] = result.usage.model_dump()
                        return DecisionAttempt(outcome="success", answers=result.answers)
                    except TypeSafeError as exc:
                        row["error"] = exc.code
                        return DecisionAttempt(outcome=exc.code)

                started = perf_counter()
                with (
                    patch.object(
                        module,
                        "runtime_context_if_running",
                        return_value=SimpleNamespace(user_id=UUID(int=1)),
                    ),
                    patch.object(module, "choose_many_with_jev", choose),
                ):
                    keep = await module.try_filter_items(
                        case["items"], case["criterion"], "synthetic"
                    )
                row.update(
                    keep=keep,
                    wrong=keep is not None and keep != case["keep"],
                    latency_ms=round((perf_counter() - started) * 1000, 2),
                )
                rows.append(row)
                output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "cases": len(rows),
                "accepted": sum(r["keep"] is not None for r in rows),
                "wrong": sum(r["wrong"] for r in rows),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Paid synthetic HITL qualification, no user mutation"
    )
    parser.add_argument("--configured-dev", action="store_true", required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(main(args.cases, args.output))
