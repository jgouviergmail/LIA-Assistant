"""
Automatic translation service for personality titles and descriptions.

Uses the ``personality_translation`` LLM slot (LLM_TYPES_REGISTRY): defaults
come from LLM_DEFAULTS and can be overridden from the admin LLM
Configuration UI (audit wave 3, N-219.1).
"""

import json

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from src.core.config import settings
from src.core.i18n_types import LANGUAGE_NAMES
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.message_text import coerce_content_to_text

logger = structlog.get_logger(__name__)

# In-memory cache for translations
# Key: "{code}_{source}_{target}" -> {"title": ..., "description": ...}
_translation_cache: dict[str, dict[str, str]] = {}


class PersonalityTranslationService:
    """
    Cost-effective translation service for personality titles/descriptions.

    Model, temperature and token budget come from the registered
    ``personality_translation`` LLM slot (code defaults + admin DB override).

    Features:
    - In-memory caching to avoid redundant API calls
    - Batch translation to all supported languages
    - JSON-based structured output
    """

    @staticmethod
    async def translate_personality(
        source_title: str,
        source_description: str,
        source_language: str,
        target_language: str,
        personality_code: str,
    ) -> dict[str, str]:
        """
        Translate title and description to target language.

        Args:
            source_title: Title in source language
            source_description: Description in source language
            source_language: Source language code
            target_language: Target language code
            personality_code: Personality code for cache key

        Returns:
            Dict with 'title' and 'description' keys

        Raises:
            Exception: If translation fails
        """
        # Check cache
        cache_key = f"{personality_code}_{source_language}_{target_language}"
        if cache_key in _translation_cache:
            logger.debug(
                "translation_cache_hit",
                personality_code=personality_code,
                target_language=target_language,
            )
            return _translation_cache[cache_key]

        # Skip if same language
        if source_language == target_language:
            result = {"title": source_title, "description": source_description}
            _translation_cache[cache_key] = result
            return result

        # Get language names
        source_name = LANGUAGE_NAMES.get(source_language, source_language)
        target_name = LANGUAGE_NAMES.get(target_language, target_language)

        # Build prompts (system prompt is versioned in prompts/v1/)
        system_prompt = load_prompt("personality_translation_prompt", version="v1").format(
            source_language=source_name,
            target_language=target_name,
        )

        user_prompt = f"""Title: {source_title}
Description: {source_description}"""

        try:
            # Registered LLM slot: code defaults + admin DB override
            llm = get_llm("personality_translation")

            from src.infrastructure.llm.invoke_helpers import (
                enrich_config_with_node_metadata,
            )

            invoke_config = enrich_config_with_node_metadata(None, "personality_translation")
            response = await llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ],
                config=invoke_config,
            )

            # Parse response. Gemini 3.x returns content as list[dict] blocks;
            # coerce to text so .startswith()/json.loads below stay str-safe.
            content = coerce_content_to_text(response.content).strip()

            # Handle markdown code blocks
            if content.startswith("```"):
                lines = content.split("\n")
                # Remove first and last lines (``` markers)
                content = "\n".join(lines[1:-1])
                if content.startswith("json"):
                    content = content[4:].strip()

            # Parse JSON
            data = json.loads(content)
            result = {
                "title": data["title"],
                "description": data["description"],
            }

            # Cache result
            _translation_cache[cache_key] = result

            logger.info(
                "personality_translated",
                personality_code=personality_code,
                source_language=source_language,
                target_language=target_language,
            )

            return result

        except json.JSONDecodeError as e:
            logger.error(
                "translation_json_parse_error",
                personality_code=personality_code,
                target_language=target_language,
                error=str(e),
                response_content=content[:200] if content else None,
            )
            raise ValueError(f"Failed to parse translation response: {e}") from e

        except Exception as e:
            logger.error(
                "translation_failed",
                personality_code=personality_code,
                target_language=target_language,
                error=str(e),
            )
            raise

    @staticmethod
    async def translate_to_all_languages(
        source_title: str,
        source_description: str,
        source_language: str,
        personality_code: str,
    ) -> dict[str, dict[str, str]]:
        """
        Translate to all supported languages.

        Args:
            source_title: Title in source language
            source_description: Description in source language
            source_language: Source language code
            personality_code: Personality code for logging

        Returns:
            Dict mapping language code to {title, description}
        """
        translations = {}

        for lang in settings.supported_languages:
            if lang == source_language:
                # Keep source as-is
                translations[lang] = {
                    "title": source_title,
                    "description": source_description,
                }
            else:
                try:
                    translations[lang] = await PersonalityTranslationService.translate_personality(
                        source_title=source_title,
                        source_description=source_description,
                        source_language=source_language,
                        target_language=lang,
                        personality_code=personality_code,
                    )
                except Exception as e:
                    logger.warning(
                        "translation_skipped",
                        personality_code=personality_code,
                        language=lang,
                        error=str(e),
                    )
                    # Skip failed translations

        return translations


def clear_translation_cache() -> None:
    """
    Clear the translation cache.

    Useful for testing or manual cache invalidation.
    """
    global _translation_cache
    _translation_cache = {}
    logger.info("translation_cache_cleared")


def get_cache_size() -> int:
    """Get current cache size."""
    return len(_translation_cache)
