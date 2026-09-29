"""Paid synthetic replay of the configured legacy HITL filter, without applying results."""

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter
from unittest.mock import AsyncMock, patch

from src.core.config import settings
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.agents.services.hitl.item_filter import ItemFilterService
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.infrastructure.database import get_db_context
from src.infrastructure.database.registry import import_all_models
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache


async def main(cases: Path, output: Path) -> None:
    if settings.environment != "development":
        raise RuntimeError("Paid synthetic probe requires development configuration")
    import_all_models()
    async with get_db_context() as db:
        await LLMConfigOverrideCache.load_from_db(db)
        await ModelCapabilitiesCache.load_from_db(db)
    service = ItemFilterService()
    config = get_llm_config_for_agent(settings, "hitl_classifier")
    rows = []
    with patch(
        "src.domains.agents.services.hitl.jev_item_filter.try_filter_items",
        AsyncMock(return_value=None),
    ):
        for case in json.loads(cases.read_text(encoding="utf-8")):
            row = {"id": case["id"], "expected": case["keep"], "model": config.model}
            started = perf_counter()
            try:
                row["keep"] = await service.filter(
                    case["items"], case["criterion"], "synthetic-baseline"
                )
            except Exception as exc:
                row["error"] = type(exc).__name__
            row["latency_ms"] = round((perf_counter() - started) * 1000, 2)
            rows.append(row)
            output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"cases": len(rows), "errors": sum("error" in r for r in rows)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configured-dev", action="store_true", required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(main(args.cases, args.output))
