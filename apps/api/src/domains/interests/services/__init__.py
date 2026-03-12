"""
Interest Learning System Services.

Provides:
- InterestExtractionService: Fire-and-forget extraction from conversations
- Weight calculations (in repository)
- Content generation (future phases)

Architecture:
    response_node -> safe_fire_and_forget(extract_interests_background(...))
                                          |
                         [Background Task - Non-blocking]
                                          |
                         LLM analysis -> new interests -> store in DB

"""

from src.domains.interests.services.extraction_service import (
    analyze_interests_for_debug,
    extract_interests_background,
    get_user_interests_for_debug,
)

__all__ = [
    "analyze_interests_for_debug",
    "extract_interests_background",
    "get_user_interests_for_debug",
]
