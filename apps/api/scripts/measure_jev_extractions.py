"""Synthetic, no-write comparison using the shipped extraction policies."""

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

import httpx

from src.core.config import settings
from src.core.llm_config_helper import get_llm_config_for_agent
from src.core.prompt_layout import single_call_messages
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.open_loop_extractor import OpenLoopExtraction
from src.domains.interests.services.extraction_service import _render_extraction_prompt
from src.domains.journals.prompt_builders import build_introspection_prompt
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_settings import read_configuration
from src.infrastructure.database import get_db_context
from src.infrastructure.database.registry import import_all_models
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.structured_output import get_structured_output
from src.infrastructure.llm.typesafe_client import ChoiceQuestion, TypeSafeClient, TypeSafeError


def prompts(message):
    conversation = "USER: " + message + "\nASSISTANT: Understood."
    return {
        "memory": load_prompt("memory_extraction_prompt").format(
            conversation=conversation,
            existing_memories="None",
            current_datetime="29/09/2026 12:00",
            known_relationships="None",
            health_context="",
        ),
        "interests": _render_extraction_prompt(conversation, [], "en"),
        "journal": build_introspection_prompt(
            conversation=conversation,
            existing_entries="None",
            current_chars=0,
            max_chars=20000,
            size_warning="",
            language_name="English",
            max_entry_chars=2000,
            health_context="",
            inner_state_section="",
            previous_turn_directives_section="",
            personality_code=None,
        ),
        "open_loops": load_prompt("open_loop_extraction_prompt").format(
            current_datetime="29/09/2026 12:00", max_items=5
        )
        + "\nCURRENT OPEN LOOPS: []\nCONVERSATION TAIL:\n"
        + conversation,
    }


async def main(output: Path):
    if settings.environment != "development":
        raise RuntimeError("This paid synthetic probe requires development configuration")
    import_all_models()
    async with get_db_context() as db:
        _, native_config = await read_configuration(db, JevUsage.OBSERVE_MEMORY)
        await LLMConfigOverrideCache.load_from_db(db)
        await ModelCapabilitiesCache.load_from_db(db)
    assert native_config
    rows = []
    question = ChoiceQuestion.model_validate_json(
        load_prompt("jev_extraction_question", version="v1")
    )
    slots = {
        "memory": "memory_extraction",
        "interests": "interest_extraction",
        "journal": "journal_extraction",
        "open_loops": "open_loop_extraction",
    }
    async with httpx.AsyncClient() as http:
        client = TypeSafeClient(http, native_config.api_key.get_secret_value())
        for index, message in enumerate(
            [
                "I have practised pottery every weekend for ten years and I love it.",
                "Thanks.",
                "I need to call the plumber tomorrow. Please remember to follow up.",
            ]
        ):
            for kind, prompt in prompts(message).items():
                row = {"case": index, "kind": kind, "prompt_characters": len(prompt)}
                started = perf_counter()
                try:
                    result = await client.choose(
                        model=native_config.model,
                        state={"extraction_kind": "observe_" + kind, "extractor_prompt": prompt},
                        question=question,
                        timeout_seconds=3,
                    )
                    row["jev"] = result.answer.model_dump()
                    row["jev_tokens"] = result.usage.model_dump()
                except TypeSafeError as exc:
                    row["jev_error"] = exc.code
                row["jev_ms"] = round((perf_counter() - started) * 1000, 2)
                slot = slots[kind]
                config = get_llm_config_for_agent(settings, slot)
                row["baseline_model"] = config.model
                started = perf_counter()
                try:
                    if kind == "open_loops":
                        result = await get_structured_output(
                            get_llm(slot),
                            single_call_messages(prompt),
                            OpenLoopExtraction,
                            provider=config.provider,
                            node_name=slot,
                        )
                        row["baseline_output"] = result.model_dump()
                    else:
                        result = await get_llm(slot).ainvoke(single_call_messages(prompt))
                        row["baseline_output"] = result.text
                        row["baseline_usage"] = result.usage_metadata
                except Exception as exc:
                    row["baseline_error"] = type(exc).__name__
                row["baseline_ms"] = round((perf_counter() - started) * 1000, 2)
                rows.append(row)
                output.write_text(
                    json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
    print(
        json.dumps(
            {
                "cases": len(rows),
                "native_errors": sum("jev_error" in r for r in rows),
                "baseline_errors": sum("baseline_error" in r for r in rows),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--configured-dev",
        action="store_true",
        help="Use the stored development provider keys for paid synthetic calls.",
    )
    args = parser.parse_args()
    if not args.configured_dev:
        parser.error("explicit --configured-dev is required")
    asyncio.run(main(args.output))
