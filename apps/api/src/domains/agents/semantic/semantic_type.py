"""
Semantic Type System - Core Type Definitions

This module defines the semantic type system inspired by:
- schema.org for hierarchy and properties
- RDF (Resource Description Framework) for relations
- SKOS (Simple Knowledge Organization System) for multilingual labels
- OWL (Web Ontology Language) for subsumption

Professional architecture to replace hardcoded patterns
with a structured and exploitable type system.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TypeCategory(Enum):
    """
    Primary categories of semantic types.

    Inspired by schema.org Thing and its main subclasses.
    Groups the 96+ types identified in the codebase.
    """

    IDENTITY = "identity"
    """Identity types: Person, Organization, Contact, etc.

    Examples: person_name, email_address, phone_number, contact_id
    """

    LOCATION = "location"
    """Location types: Place, PostalAddress, GeoCoordinates, etc.

    Examples: physical_address, coordinate, place_id, postal_code
    """

    TEMPORAL = "temporal"
    """Temporal types: Date, Time, Duration, etc.

    Examples: datetime, timezone, duration, birthday, trigger_datetime
    """

    RESOURCE_ID = "resource_id"
    """Resource identifiers: event_id, file_id, message_id, etc.

    Examples: calendar_id, contact_id, task_id, thread_id
    """

    CONTENT = "content"
    """Content types: Text, Media, Document, etc.

    Examples: email_body, markdown_text, file_content, message_snippet
    """

    MEASUREMENT = "measurement"
    """Quantitative values: distance, temperature, rating, etc.

    Examples: temperature, wind_speed, rating, file_size, confidence_score
    """

    STATUS = "status"
    """States and statuses: Enumeration, State, Condition, etc.

    Examples: task_status, traffic_condition, business_status, shared_status
    """

    CATEGORY = "category"
    """Categories and classifications: Type, Mode, Filter, etc.

    Examples: travel_mode, language_code, place_type, search_mode
    """


@dataclass(frozen=True)
class SemanticType:
    """
    Complete semantic type with rich metadata.

    This class is at the core of the semantic type system.
    It models the 96+ types identified with:
    - Hierarchy (parent/children)
    - Semantic relations (related, broader, narrower)
    - Typed properties
    - Multilingual labels
    - Provenance (domains, tools)
    - Validation constraints

    Inspirations:
    - schema.org: class hierarchy and typed properties
    - RDF: URIs, triple relations (subject-predicate-object)
    - SKOS: broader/narrower/related, multilingual labels
    - OWL: subsumption (subClassOf), properties

    Attributes:
        name: Unique type name (e.g., "physical_address", "email_address")
        category: Primary category (IDENTITY, LOCATION, etc.)
        uri: Optional unique URI for RDF interoperability
        parent: Parent type in hierarchy (subClassOf in OWL)
        children: List of direct subtypes
        description: Textual description of the type
        examples: Typical value examples
        labels: Multilingual labels {lang_code: label} (SKOS)
        properties: Typed properties {prop_name: prop_type} (schema.org)
        related_types: Semantically related types (skos:related)
        broader_types: More generic types (skos:broader)
        narrower_types: More specific types (skos:narrower)
        source_domains: Source domains providing this type
        used_in_tools: Tools using this type (inputs/outputs)
        format_pattern: Regex pattern for validation
        validation_rules: Additional validation rules

    Example:
        >>> email_type = SemanticType(
        ...     name="email_address",
        ...     category=TypeCategory.IDENTITY,
        ...     parent="ContactPoint",
        ...     description="Email address (RFC 5322)",
        ...     labels={"fr": "Adresse email", "en": "Email address"},
        ...     format_pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$",
        ...     related_types=["contact_id", "person_name"],
        ...     source_domains=["contacts", "emails", "calendar"],
        ...     used_in_tools=["get_contacts_tool", "send_email_tool"]
        ... )
    """

    # ===== Identity =====
    name: str
    """Unique type name (e.g., "physical_address")."""

    category: TypeCategory
    """Primary type category."""

    uri: str | None = None
    """Optional unique URI for RDF interoperability (e.g., "http://schema.org/PostalAddress")."""

    # ===== Hierarchy (OWL-inspired) =====
    parent: str | None = None
    """Parent type in the hierarchy (subClassOf relation in OWL).

    Enables building a DAG (Directed Acyclic Graph) of types.
    Example: "PostalAddress" is parent of "physical_address"
    """

    children: list[str] = field(default_factory=list)
    """List of direct subtypes.

    Inverse of parent. Automatically computed by TypeRegistry.
    """

    # ===== Description =====
    description: str = ""
    """Textual description of the type and its usage."""

    examples: list[str] = field(default_factory=list)
    """Typical value examples for this type.

    Useful for documentation and validation.
    Example for email_address: ["john@example.com", "user+tag@domain.co.uk"]
    """

    # ===== Multilingual labels (SKOS-inspired) =====
    labels: dict[str, str] = field(default_factory=dict)
    """Labels in different languages {lang_code: label}.

    Inspired by skos:prefLabel. Enables internationalization.
    Example: {"fr": "Adresse physique", "en": "Physical address", "de": "Physische Adresse"}
    """

    # ===== Properties (schema.org-inspired) =====
    properties: dict[str, str] = field(default_factory=dict)
    """Typed properties of this type {prop_name: prop_type}.

    Inspired by schema.org properties with domain/range.
    Example for PostalAddress:
    {
        "streetAddress": "str",
        "addressLocality": "locality",
        "addressCountry": "country_code",
        "postalCode": "postal_code"
    }
    """

    # ===== Semantic relations (RDF/SKOS-inspired) =====
    related_types: list[str] = field(default_factory=list)
    """Semantically related types (skos:related relation).

    Non-hierarchical relations between types.
    Example: email_address is related to contact_id, person_name, message_id
    """

    broader_types: list[str] = field(default_factory=list)
    """More generic types (skos:broader relation).

    Generalization/specialization relation.
    Example: physical_address has broader types "PostalAddress", "Place"
    """

    narrower_types: list[str] = field(default_factory=list)
    """More specific types (skos:narrower relation).

    Inverse of broader_types.
    """

    # ===== Provenance =====
    source_domains: list[str] = field(default_factory=list)
    """Domains providing this semantic type.

    Indicates which domains can provide values of this type.
    Example: physical_address is provided by ["contacts", "places", "calendar", "routes"]

    CRUCIAL for iso-functional semantic expansion.
    """

    used_in_tools: list[str] = field(default_factory=list)
    """Tools using this type in their inputs or outputs.

    Enables tracing the effective usage of the type in the codebase.
    Example: email_address is used in ["get_contacts_tool", "send_email_tool", "create_event_tool"]
    """

    # ===== Constraints and validation =====
    format_pattern: str | None = None
    """Regex pattern for format validation.

    Validates the form of values.
    Example for email_address: r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
    """

    validation_rules: list[str] = field(default_factory=list)
    """Additional validation rules (textual).

    Constraints that cannot be expressed as regex.
    Example: ["Must be a valid ISO 8601 datetime", "Timezone must be IANA identifier"]
    """

    def __post_init__(self) -> None:
        """Validation post-initialisation."""
        if not self.name:
            raise ValueError("SemanticType name cannot be empty")

        # Validate that name doesn't contain spaces (use underscores)
        if " " in self.name:
            raise ValueError(
                f"SemanticType name '{self.name}' cannot contain spaces (use underscores)"
            )

    def get_label(self, lang: str = "en") -> str:
        """
        Return the label in the requested language, with fallback.

        Args:
            lang: ISO 639-1 language code (e.g., "fr", "en", "de")

        Returns:
            Label in the requested language, or type name if not available

        Example:
            >>> type_def.get_label("fr")
            "Adresse physique"
            >>> type_def.get_label("es")  # Not available, fallback to en
            "Physical address"
            >>> type_def.get_label("it")  # Not available, fallback to name
            "physical_address"
        """
        if lang in self.labels:
            return self.labels[lang]

        # Fallback to English if available
        if lang != "en" and "en" in self.labels:
            return self.labels["en"]

        # Ultimate fallback to name
        return self.name

    def is_subtype_of(self, other_type_name: str) -> bool:
        """
        Check if this type is a subtype of other_type_name.

        This method only checks the direct parent relation.
        For full (transitive) subsumption, use TypeRegistry.is_subtype_of().

        Args:
            other_type_name: Name of the potential parent type

        Returns:
            True if this type has other_type_name as direct parent
        """
        return self.parent == other_type_name

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize the type to a dictionary.

        Useful for JSON export, logging, debugging.

        Returns:
            Dictionary representing the type
        """
        return {
            "name": self.name,
            "category": self.category.value,
            "uri": self.uri,
            "parent": self.parent,
            "children": self.children,
            "description": self.description,
            "examples": self.examples,
            "labels": self.labels,
            "properties": self.properties,
            "related_types": self.related_types,
            "broader_types": self.broader_types,
            "narrower_types": self.narrower_types,
            "source_domains": self.source_domains,
            "used_in_tools": self.used_in_tools,
            "format_pattern": self.format_pattern,
            "validation_rules": self.validation_rules,
        }

    def __repr__(self) -> str:
        """Concise representation for debugging."""
        parent_str = f", parent={self.parent}" if self.parent else ""
        domains_str = f", domains={self.source_domains}" if self.source_domains else ""
        return f"SemanticType(name={self.name}, category={self.category.value}{parent_str}{domains_str})"
