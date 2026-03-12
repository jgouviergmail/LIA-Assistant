"""
Semantic Type System Module

Système de typage sémantique complet pour LIA.

Remplace les patterns hardcodés par un système structuré inspiré de:
- schema.org (hiérarchie de classes)
- RDF (relations sémantiques)
- SKOS (labels multi-lingues)
- OWL (subsomption reasoning)

Composants:
- SemanticType: Dataclass pour définir un type sémantique
- TypeCategory: Enum des catégories de types
- TypeRegistry: Registry central avec hiérarchie et lookups
- core_types: Catalogue des 96+ types identifiés
- expansion_service: Service d'expansion sémantique

Usage:
    >>> from src.domains.agents.semantic import get_registry, load_core_types
    >>> registry = get_registry()
    >>> load_core_types(registry)
    >>> email_type = registry.get("email_address")
    >>> email_type.source_domains
    ['contacts', 'emails', 'calendar']
"""

from src.domains.agents.semantic.core_types import load_core_types
from src.domains.agents.semantic.expansion_service import (
    generate_semantic_dependencies_for_prompt,
    get_expansion_service,
    reset_expansion_service,
)
from src.domains.agents.semantic.semantic_type import SemanticType, TypeCategory
from src.domains.agents.semantic.type_registry import (
    TypeRegistry,
    get_registry,
    reset_registry,
)

__all__ = [
    # Core classes
    "SemanticType",
    "TypeCategory",
    "TypeRegistry",
    # Registry functions
    "get_registry",
    "reset_registry",
    "load_core_types",
    # Expansion service
    "get_expansion_service",
    "reset_expansion_service",
    "generate_semantic_dependencies_for_prompt",
]
