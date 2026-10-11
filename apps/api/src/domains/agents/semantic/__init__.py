"""
Semantic Type System Module

The complete semantic type system of LIA.

Uses a schema.org-inspired hierarchy, validated relation metadata and explicit
tool contracts. Runtime linking matches exact semantic types and JSON shapes
within the account's available catalogue; it does not perform OWL reasoning.

Components:
- SemanticType: dataclass defining a semantic type
- TypeCategory: enum of the type categories
- TypeRegistry: central registry with hierarchy and lookups
- core_types, entity_types, native_types: the declared ontology
- manifest_semantics: available contracts and reference compatibility
- expansion_service: semantic expansion service

Usage:
    >>> from src.domains.agents.semantic import get_registry, load_core_types
    >>> registry = get_registry()
    >>> load_core_types(registry)
    >>> email_type = registry.get("email_address")
    >>> email_type.source_domains
    ['contact', 'email', 'event']
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
