"""
Semantic Type System Module

The complete semantic type system of LIA.

Replaces hardcoded patterns by a structured system inspired by:
- schema.org (class hierarchy)
- RDF (semantic relations)
- SKOS (broader/narrower/related)
- OWL (subsumption reasoning)

Components:
- SemanticType: dataclass defining a semantic type
- TypeCategory: enum of the type categories
- TypeRegistry: central registry with hierarchy and lookups
- core_types: catalogue of the 96+ identified types
- expansion_service: semantic expansion service

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
