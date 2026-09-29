"""Replay the synthetic radio corpus through the actual configured verifier.

Run explicitly in the dev API container. Reads configuration in a READ ONLY
transaction; no account records are read and no ledger is written. Paid calls
use the shipped structured-output path and its unmodified evidence-first prompt.
"""

import argparse
import asyncio
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.messages import BaseMessage
from pydantic import BaseModel
from sqlalchemy import text

from src.core.config import settings
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.radio.facts import FactKind, FactPack, RadioFact, Sensitivity, SourceRef
from src.domains.radio.formats import RadioFormat, RadioRole
from src.domains.radio.prompting import StationVoice, load_templates
from src.domains.radio.script import LineKind, RadioDelivery, ScriptPart
from src.domains.radio.verification import VerifiedLine
from src.domains.radio.writing import ModelLineChecker
from src.infrastructure.database import get_db_context
from src.infrastructure.database.registry import import_all_models
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.structured_output import get_structured_output


async def measure(output: Path, repetitions: int, corpus: Path) -> None:
    import_all_models()
    async with get_db_context() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        await LLMConfigOverrideCache.load_from_db(db)
        await ModelCapabilitiesCache.load_from_db(db)
    config = get_llm_config_for_agent(settings, "radio_verifier")
    cases = json.loads(corpus.read_text(encoding="utf-8"))
    records = []
    semaphore = asyncio.Semaphore(2)

    async def one(case, repeat):
        async with semaphore:
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
            usage = UsageMetadataCallbackHandler()
            llm = get_llm("radio_verifier")

            async def call[M: BaseModel](messages: list[BaseMessage], schema: type[M]) -> M:
                return await get_structured_output(
                    llm,
                    messages,
                    schema,
                    provider=config.provider,
                    node_name="radio_verifier",
                    config={"callbacks": [usage]},
                )

            checker = ModelLineChecker(
                template=load_templates().verifier,
                station=StationVoice("Radio 42", case["language"], "Calm and factual."),
                call=call,
            )
            started = perf_counter()
            row = {
                "id": case["id"],
                "repeat": repeat,
                "model": config.model,
                "provider": config.provider,
            }
            try:
                verdict = await asyncio.wait_for(checker.unsupported(lines, pack), 45)
                row.update(
                    predicted=sorted(verdict) if verdict is not None else None,
                    correct=verdict == frozenset(case["expected_unsupported"]),
                    tokens=usage.usage_metadata,
                )
            except Exception as exc:
                row.update(error=type(exc).__name__)
            row["latency_ms"] = round((perf_counter() - started) * 1000, 2)
            records.append(row)
            output.write_text(
                json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

    await asyncio.gather(*(one(case, repeat) for repeat in range(repetitions) for case in cases))
    print(
        json.dumps(
            {
                "scripts": len(records),
                "correct": sum(row.get("correct", False) for row in records),
                "errors": sum("error" in row for row in records),
                "median_ms": median(row["latency_ms"] for row in records),
                "model": config.model,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path(__file__).parents[1] / "tests/fixtures/jev_radio_cases.json",
    )
    args = parser.parse_args()
    asyncio.run(measure(args.output, args.repetitions, args.corpus))
