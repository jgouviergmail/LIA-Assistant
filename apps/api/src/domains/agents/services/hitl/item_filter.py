"""
Item Filter Service - Filters items based on user exclusion criteria.

This service handles the EDIT action in for_each_confirmation HITL flow.
When user asks to exclude specific items (e.g., "retire les emails de Guy Savoy"),
this service:
1. Takes the item previews
2. Takes the user's exclusion criteria
3. Uses LLM to determine which items match the criteria
4. Returns indices of items to KEEP (not matching criteria)

Architecture:
    OrchestrationService detects EDIT intent via HitlResponseClassifier
    → task_orchestrator_node calls ItemFilterService.filter()
    → LLM determines which items match exclusion criteria
    → Filtered items used in re-interrupt() for user validation

Generic Design:
    - Domain-agnostic: works with any item type (email, contact, event, task, file)
    - Uses item previews which contain key fields for each domain
    - LLM makes semantic matching decisions (handles typos, synonyms, partial matches)

Created: 2026-01-30
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.instrumentation import create_instrumented_config
from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata

logger = structlog.get_logger(__name__)


class ItemFilterService:
    """
    Service for filtering items based on user exclusion criteria.

    Uses LLM to semantically match items against user criteria,
    handling typos, partial matches, and synonyms.

    Example:
        >>> service = ItemFilterService()
        >>> items_to_keep = await service.filter(
        ...     item_previews=[
        ...         {"subject": "Newsletter Carrefour", "from": "news@carrefour.fr"},
        ...         {"subject": "Meeting tomorrow", "from": "guy.savoy@restaurant.com"},
        ...         {"subject": "Invoice", "from": "billing@company.com"},
        ...     ],
        ...     exclude_criteria="Guy Savoy",
        ...     user_language="fr",
        ... )
        >>> print(items_to_keep)
        [0, 2]  # Indices of items NOT matching "Guy Savoy"
    """

    def __init__(self) -> None:
        """Initialize the service with LLM."""
        # Use low temperature for deterministic matching
        self.llm = get_llm(
            llm_type="hitl_classifier",  # Reuse classifier LLM config
            config_override={"temperature": 0.0},  # Deterministic for filtering
        )

    async def filter(
        self,
        item_previews: list[dict[str, Any]],
        exclude_criteria: str,
        user_language: str = "fr",
        run_id: str | None = None,
    ) -> list[int]:
        """
        Filter items based on exclusion criteria.

        Args:
            item_previews: List of item preview dicts with key fields
            exclude_criteria: User's criteria for items to EXCLUDE
            user_language: Language for understanding criteria
            run_id: Optional run ID for logging

        Returns:
            List of indices of items to KEEP (not matching criteria)

        Raises:
            Exception: If LLM invocation fails
        """
        if not item_previews:
            return []

        if not exclude_criteria.strip():
            # No criteria - keep all items
            return list(range(len(item_previews)))

        logger.info(
            "item_filter_started",
            run_id=run_id,
            item_count=len(item_previews),
            exclude_criteria=exclude_criteria[:100],
        )

        # Build the prompt
        prompt = self._build_filter_prompt(
            item_previews=item_previews,
            exclude_criteria=exclude_criteria,
            user_language=user_language,
        )

        # Create instrumented config
        config = create_instrumented_config(
            llm_type="item_filter",
            tags=["hitl", "item_filter", "for_each"],
            metadata={
                "item_count": len(item_previews),
                "criteria_length": len(exclude_criteria),
                "run_id": run_id,
            },
        )
        config = enrich_config_with_node_metadata(config, "item_filter")

        try:
            # Call LLM
            result = await self.llm.ainvoke(prompt, config=config)
            content = result.content if isinstance(result.content, str) else str(result.content)

            # Parse the response
            indices_to_exclude = self._parse_filter_response(content, len(item_previews))

            # Return indices to KEEP (inverse of exclude)
            indices_to_keep = [i for i in range(len(item_previews)) if i not in indices_to_exclude]

            logger.info(
                "item_filter_completed",
                run_id=run_id,
                total_items=len(item_previews),
                excluded_count=len(indices_to_exclude),
                kept_count=len(indices_to_keep),
                excluded_indices=indices_to_exclude,
            )

            return indices_to_keep

        except Exception as e:
            logger.error(
                "item_filter_error",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    def _build_filter_prompt(
        self,
        item_previews: list[dict[str, Any]],
        exclude_criteria: str,
        user_language: str,  # noqa: ARG002 - Reserved for future i18n support
    ) -> str:
        """Build prompt for item filtering."""
        # Note: user_language reserved for future prompt localization
        # Format items as numbered list
        items_text = []
        for i, preview in enumerate(item_previews):
            # Build readable preview from fields
            preview_parts = []
            for key, value in preview.items():
                if value is not None:
                    str_value = str(value)
                    if len(str_value) > 50:
                        str_value = str_value[:47] + "..."
                    preview_parts.append(f"{key}: {str_value}")
            item_text = " | ".join(preview_parts) if preview_parts else "(empty)"
            items_text.append(f"{i}. {item_text}")

        items_list = "\n".join(items_text)

        return f"""You are an item filter assistant. Your task is to identify which items should be EXCLUDED based on the user's criteria.

User's exclusion criteria: "{exclude_criteria}"

Items to filter:
{items_list}

Instructions:
1. Analyze each item against the user's exclusion criteria
2. An item should be EXCLUDED if it matches the criteria (sender, subject, content, name, etc.)
3. Use semantic matching: handle typos, partial matches, synonyms
4. Return ONLY the indices of items to EXCLUDE as a JSON array

Response format (JSON array of integers):
[0, 2]  // means exclude items at indices 0 and 2

If NO items match the criteria, return: []
If ALL items match the criteria, return: [0, 1, 2, ...]

Important:
- Return ONLY the JSON array, no explanation
- Indices are 0-based
- Be inclusive in matching: "Guy Savoy" matches "guy.savoy@..." or "Guy S."

Response:"""

    def _parse_filter_response(self, response: str, max_index: int) -> list[int]:
        """Parse LLM response to extract indices to exclude."""
        # Clean response
        content = response.strip()

        # Remove markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            indices = json.loads(content)

            # Validate it's a list of integers within range
            if not isinstance(indices, list):
                logger.warning(
                    "item_filter_response_not_list",
                    content=content[:100],
                    parsed_type=type(indices).__name__,
                )
                return []

            valid_indices = []
            for idx in indices:
                if isinstance(idx, int) and 0 <= idx < max_index:
                    valid_indices.append(idx)
                else:
                    logger.warning(
                        "item_filter_invalid_index",
                        index=idx,
                        max_index=max_index,
                    )

            return valid_indices

        except json.JSONDecodeError as e:
            logger.error(
                "item_filter_json_parse_error",
                error=str(e),
                content=content[:200],
            )
            # Fallback: try to extract numbers from response
            import re

            numbers = re.findall(r"\b(\d+)\b", content)
            valid_indices = []
            for num_str in numbers:
                try:
                    idx = int(num_str)
                    if 0 <= idx < max_index:
                        valid_indices.append(idx)
                except ValueError:
                    pass
            return valid_indices


# Singleton pattern for reuse
_item_filter_service: ItemFilterService | None = None


def get_item_filter_service() -> ItemFilterService:
    """Get singleton ItemFilterService instance."""
    global _item_filter_service
    if _item_filter_service is None:
        _item_filter_service = ItemFilterService()
    return _item_filter_service
