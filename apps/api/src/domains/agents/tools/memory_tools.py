"""
Memory Schema for Long-Term User Profiling.

Provides the MemorySchema used by the background memory extraction system.

Architecture:
    The memory system builds a psychological profile of the user, not just a list of facts.
    Each memory includes:
    - content: The factual information
    - category: Classification (preference, personal, relationship, event, pattern, sensitivity)
    - emotional_weight: -10 (trauma) to +10 (joy) for emotional calibration
    - trigger_topic: Keywords that should activate this memory
    - usage_nuance: How the assistant should use this information

Example:
    >>> from src.domains.agents.tools.memory_tools import MemorySchema
    >>> memory = MemorySchema(
    ...     content="J'aime le café",
    ...     category="preference",
    ...     emotional_weight=5,
    ... )
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Memory categories following the psychological profile approach
MemoryCategoryType = Literal[
    "preference",  # User preferences and tastes
    "personal",  # Identity info (work, family, location)
    "relationship",  # People the user knows
    "event",  # Significant events and milestones
    "pattern",  # Behavioral patterns
    "sensitivity",  # Sensitive topics (trauma, conflicts)
]


class MemorySchema(BaseModel):
    """
    Schema for structured user memory with psychological profiling.

    This is not a simple key-value store - each memory captures:
    - WHAT: The factual content
    - HOW IMPORTANT: Emotional weight
    - WHEN TO USE: Trigger topics
    - HOW TO USE: Usage nuances for the assistant's personality

    Attributes:
        content: The factual information in one concise sentence
        category: Classification for organization and prioritization
        emotional_weight: Emotional calibration from -10 (trauma) to +10 (joy)
        trigger_topic: Keywords that should activate this memory in conversations
        usage_nuance: Instructions for the assistant on how to leverage this info
        importance: Priority score for retrieval ranking (0.0-1.0)
    """

    content: str = Field(
        ...,
        description="Le fait ou l'information en une phrase concise",
        min_length=3,
        max_length=500,
    )

    category: MemoryCategoryType = Field(
        ...,
        description=(
            "Catégorie de la mémoire: "
            "preference (goûts), personal (identité), relationship (relations), "
            "event (événements), pattern (comportements), sensitivity (sujets sensibles)"
        ),
    )

    emotional_weight: int = Field(
        default=0,
        ge=-10,
        le=10,
        description=(
            "Poids émotionnel de -10 (trauma/douleur profonde) à +10 (joie/fierté). "
            "0 = neutre. Permet de calibrer la sensibilité du sujet. "
            "IMPORTANT: ne pas laisser à 0 si une émotion est clairement détectée."
        ),
    )

    trigger_topic: str = Field(
        default="",
        description=(
            "Le sujet ou mot-clé qui doit activer ce souvenir dans les conversations. "
            "Ex: 'voiture', 'père', 'travail', 'vacances', 'réunion'"
        ),
        max_length=100,
    )

    usage_nuance: str = Field(
        default="",
        description=(
            "Comment utiliser cette information selon la personnalité de l'assistant. "
            "Ex: 'Sujet sensible, pas de blague', "
            "'À utiliser avec humour noir si ambiance le permet', "
            "'Fierté évidente, peut être complimenté', "
            "'Zone sensible, ne pas creuser sauf si l'utilisateur en parle'"
        ),
        max_length=300,
    )

    importance: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description=(
            "Score d'importance pour prioritisation dans la recherche. "
            "0.9+ pour préférences explicites, 0.5 pour faits anecdotiques"
        ),
    )

    # ===== CHAMPS PURGE AUTOMATIQUE =====

    usage_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Nombre de fois où cette mémoire a été récupérée avec pertinence "
            "(score >= seuil configuré). Incrémenté automatiquement."
        ),
    )

    last_accessed_at: datetime | None = Field(
        default=None,
        description=(
            "Dernière date d'accès pertinent. None si jamais accédée depuis création. "
            "Mis à jour automatiquement lors de la récupération pertinente."
        ),
    )

    pinned: bool = Field(
        default=False,
        description=(
            "Si True, cette mémoire ne sera JAMAIS supprimée automatiquement "
            "par le processus de purge, peu importe son âge ou son usage."
        ),
    )


def get_memory_categories() -> list[dict[str, str]]:
    """
    Get list of memory categories with descriptions.

    Useful for UI display and API documentation.

    Returns:
        List of category dicts with name and description
    """
    return [
        {
            "name": "preference",
            "label": "Préférences",
            "description": "Goûts, préférences, habitudes de l'utilisateur",
            "icon": "heart",
        },
        {
            "name": "personal",
            "label": "Personnel",
            "description": "Informations d'identité (travail, famille, lieu de vie)",
            "icon": "user",
        },
        {
            "name": "relationship",
            "label": "Relations",
            "description": "Personnes mentionnées et nature des relations",
            "icon": "users",
        },
        {
            "name": "event",
            "label": "Événements",
            "description": "Événements significatifs et dates importantes",
            "icon": "calendar",
        },
        {
            "name": "pattern",
            "label": "Patterns",
            "description": "Comportements et habitudes récurrents",
            "icon": "repeat",
        },
        {
            "name": "sensitivity",
            "label": "Zones sensibles",
            "description": "Sujets délicats nécessitant une approche prudente",
            "icon": "alert-triangle",
        },
    ]
