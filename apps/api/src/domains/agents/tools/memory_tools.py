"""Memory category vocabulary for long-term user profiling.

The categories themselves are stored as ``MemoryCategory``
(``domains/memories/models.py``). This module holds the two faces the rest of
the stack needs and cannot derive from that enum:

- ``MemoryCategoryType`` — the literal type the save-memory tool exposes to the
  model, and the one ``ExtractedMemory`` validates against;
- ``get_memory_categories()`` — the catalogue ``GET /memories/categories``
  publishes so a client can describe each category.

Both restate one closed set, so both are asserted at boot (ADR-085): a category
present in the enum and missing from a restatement disappears from the product
in silence. Measured 2026-08-28 — ``procedural`` (ADR-236) was rejected by the
extraction parser and absent from this catalogue, so the "rules & directives"
memories could never be created and their group never appeared in the UI.
"""

from typing import Literal

# Memory categories following the psychological profile approach
# The SAME vocabulary as the database enum — see
# domains/memories/schemas.py for why it is never restated by hand.
MemoryCategoryType = Literal[
    "preference",  # User preferences and tastes
    "personal",  # Identity info (work, family, location)
    "relationship",  # People the user knows
    "event",  # Significant events and milestones
    "pattern",  # Behavioral patterns
    "sensitivity",  # Sensitive topics (trauma, conflicts)
    "procedural",  # Standing instructions about HOW to work (ADR-236)
]


def get_memory_categories() -> list[dict[str, str]]:
    """Publish the memory categories a client may display or filter on.

    Served by ``GET /memories/categories``. The web UI renders its own
    localized labels (``memories.categories.*``, six locales) and reads ``name``
    only — the ``label``/``description`` here are the API's own description of
    each category, for clients that have no translation catalogue.

    Every stored category MUST appear: the settings screen groups what the
    catalogue publishes, so an omission hides a whole family of memories.
    Asserted at boot by ``assert_category_vocabulary_completeness``.

    Returns:
        One dict per category, with ``name``, ``label``, ``description``, ``icon``.
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
        {
            "name": "procedural",
            "label": "Règles et directives",
            "description": "Consignes durables sur la manière de travailler (ADR-236)",
            "icon": "pin",
        },
    ]
