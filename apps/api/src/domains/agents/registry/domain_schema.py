"""Immutable declaration shared by the domain taxonomy and its extensions."""

from dataclasses import dataclass, field

from pydantic import JsonValue


@dataclass(frozen=True)
class DomainConfig:
    """
    Configuration for a single domain in the multi-agent system.

    Attributes:
        name: Internal domain identifier (e.g., "contacts", "email")
        display_name: Human-readable domain name (e.g., "Google Contacts")
        description: Brief description of domain capabilities
        agent_names: List of agent identifiers in this domain (e.g., ["contact_agent"])
        result_key: Canonical key for step results in $steps references (e.g., "contacts", "weathers").
                    This is THE source of truth for result naming - used by executor, prompts, and tools.
        related_domains: Domains often used together (for smart expansion)
        is_routable: Whether this domain can be selected by router
        metadata: Additional domain-specific metadata

    Design Notes:
        - Frozen dataclass ensures immutability (thread-safe)
        - v3.1: Domain detection handled by QueryAnalyzerService LLM
        - Related domains enable smart expansion (e.g., contacts → email)
        - result_key is the SINGLE source of truth for naming step results
    """

    name: str
    display_name: str
    description: str
    agent_names: list[str]
    result_key: str  # Canonical key for $steps.STEP_ID.{result_key} references
    related_domains: list[str] = field(default_factory=list)
    is_routable: bool = True  # Can be selected by router (False for internal/technical domains)
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate domain configuration."""
        if not self.name:
            raise ValueError("Domain name cannot be empty")
        if not self.agent_names:
            raise ValueError(f"Domain '{self.name}' must have at least one agent")
        if not self.result_key:
            raise ValueError(f"Domain '{self.name}' must have a result_key")
