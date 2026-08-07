"""Skill description translation helpers.

Extracted from ``skills/router.py`` (file-size ratchet): translating a
description into the six supported languages and writing the result next to
the skill is a cohesive unit, used by two routes and by nothing else in the
router's request handling.

Created: 2026-08-06
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def _translate_description_all_langs(
    description: str,
    invoke_config: Any,
) -> dict[str, str]:
    """Call LLM to translate a skill description into all 6 supported languages."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from src.domains.agents.prompts import load_prompt
    from src.domains.agents.utils.json_parser import extract_json_from_llm_response
    from src.infrastructure.llm.factory import get_llm

    system_prompt = load_prompt("skill_description_translation_prompt", version="v1")
    llm = get_llm("skill_description_translator")
    response = await llm.ainvoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=description)],
        config=invoke_config,
    )
    content = response.content if hasattr(response, "content") else str(response)
    # Central parser handles fences, trailing commas and // comments. Callers
    # catch (json.JSONDecodeError, ValueError) together, so raising ValueError
    # on a parse failure is transparent to them.
    parse_result = extract_json_from_llm_response(
        str(content), expected_type=dict, context="skill_description_translation"
    )
    if not parse_result.success or not isinstance(parse_result.data, dict):
        raise ValueError("LLM returned invalid translation format")
    translations: dict[str, str] = parse_result.data
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in translations.items()):
        raise ValueError("LLM returned invalid translation format")
    return translations


def _save_translations(skill_dir: Path, translations: dict[str, str]) -> None:
    """Write (or overwrite) translations.json next to SKILL.md."""
    (skill_dir / "translations.json").write_text(
        json.dumps(translations, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
