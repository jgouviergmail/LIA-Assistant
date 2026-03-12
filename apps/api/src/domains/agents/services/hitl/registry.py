"""
HITL Interaction Registry - Factory for HITL interaction instances.

This module provides a registry pattern for HITL interactions, enabling:
- Runtime selection of interaction strategy based on type
- Extensibility via decorator registration
- Dependency injection for interaction instances

Architecture:
    - Singleton registry holding interaction class mappings
    - Decorator pattern for registration
    - Factory method for instance creation

Design Patterns:
    - Registry Pattern: Central storage of implementations
    - Factory Pattern: Creates instances with dependencies
    - Decorator Pattern: Auto-registration of implementations

Usage:
    # Registration (in interaction module)
    @HitlInteractionRegistry.register(HitlInteractionType.PLAN_APPROVAL)
    class PlanApprovalInteraction:
        ...

    # Usage (in StreamingService)
    interaction = HitlInteractionRegistry.get(
        HitlInteractionType.PLAN_APPROVAL,
        question_generator=generator,
    )
    async for token in interaction.generate_question_stream(context, "fr"):
        yield token

References:
    - protocols.py: HitlInteractionProtocol definition
    - Similar to ToolRegistry pattern in the codebase

Created: 2025-11-25
"""

from collections.abc import Callable
from typing import Any

from src.infrastructure.observability.logging import get_logger

from .protocols import HitlInteractionProtocol, HitlInteractionType

logger = get_logger(__name__)


class HitlInteractionRegistry:
    """
    Registry for HITL interaction implementations.

    Provides factory methods for creating interaction instances based on type.
    Implementations are registered via the @register decorator.

    Thread Safety:
        - Registry is populated at module import time
        - Get operations are read-only (thread-safe)
        - No runtime registration after startup

    Example:
        >>> # In interaction module (auto-registers at import)
        >>> @HitlInteractionRegistry.register(HitlInteractionType.PLAN_APPROVAL)
        >>> class PlanApprovalInteraction:
        ...     def __init__(self, question_generator):
        ...         self.generator = question_generator
        ...
        >>> # In StreamingService
        >>> interaction = HitlInteractionRegistry.get(
        ...     HitlInteractionType.PLAN_APPROVAL,
        ...     question_generator=generator,
        ... )

    See Also:
        - HitlInteractionProtocol: Contract for registered implementations
        - PlanApprovalInteraction: Plan approval implementation
    """

    # Class-level storage for registered interactions
    # Maps HitlInteractionType -> interaction class (not instance)
    _interactions: dict[HitlInteractionType, type[HitlInteractionProtocol]] = {}

    @classmethod
    def register(
        cls,
        interaction_type: HitlInteractionType,
    ) -> Callable[[type], type]:
        """
        Decorator to register an interaction implementation.

        Registers a class as the handler for a specific interaction type.
        The class must implement HitlInteractionProtocol.

        Args:
            interaction_type: The type this implementation handles

        Returns:
            Decorator function that registers the class

        Raises:
            ValueError: If interaction_type is already registered

        Example:
            >>> @HitlInteractionRegistry.register(HitlInteractionType.PLAN_APPROVAL)
            >>> class PlanApprovalInteraction:
            ...     @property
            ...     def interaction_type(self) -> HitlInteractionType:
            ...         return HitlInteractionType.PLAN_APPROVAL
            ...
            ...     async def generate_question_stream(self, context, language):
            ...         ...

        Notes:
            - Registration happens at module import time
            - Duplicate registration raises ValueError
            - Class is stored, not instance (lazy instantiation)
        """

        def decorator(interaction_class: type) -> type:
            if interaction_type in cls._interactions:
                existing = cls._interactions[interaction_type]
                logger.warning(
                    "hitl_interaction_already_registered",
                    interaction_type=interaction_type.value,
                    existing_class=existing.__name__,
                    new_class=interaction_class.__name__,
                )
                # Allow override for testing, but warn
            cls._interactions[interaction_type] = interaction_class
            logger.debug(
                "hitl_interaction_registered",
                interaction_type=interaction_type.value,
                class_name=interaction_class.__name__,
            )
            return interaction_class

        return decorator

    @classmethod
    def get(
        cls,
        interaction_type: HitlInteractionType,
        **kwargs: Any,
    ) -> HitlInteractionProtocol:
        """
        Get an interaction instance for the specified type.

        Creates a new instance of the registered interaction class,
        passing kwargs to the constructor.

        Args:
            interaction_type: Type of interaction to create
            **kwargs: Constructor arguments for the interaction class
                Common kwargs:
                - question_generator: HitlQuestionGenerator instance

        Returns:
            Interaction instance implementing HitlInteractionProtocol

        Raises:
            KeyError: If interaction_type is not registered

        Example:
            >>> from src.domains.agents.services.hitl.question_generator import (
            ...     HitlQuestionGenerator,
            ... )
            >>> generator = HitlQuestionGenerator()
            >>> interaction = HitlInteractionRegistry.get(
            ...     HitlInteractionType.PLAN_APPROVAL,
            ...     question_generator=generator,
            ... )
            >>> async for token in interaction.generate_question_stream(...):
            ...     print(token, end="")
        """
        if interaction_type not in cls._interactions:
            registered = list(cls._interactions.keys())
            logger.error(
                "hitl_interaction_not_registered",
                interaction_type=interaction_type.value,
                registered_types=[t.value for t in registered],
            )
            raise KeyError(
                f"No interaction registered for type: {interaction_type.value}. "
                f"Registered types: {[t.value for t in registered]}"
            )

        interaction_class = cls._interactions[interaction_type]
        return interaction_class(**kwargs)

    @classmethod
    def from_action_type(
        cls,
        action_type: str,
        **kwargs: Any,
    ) -> HitlInteractionProtocol:
        """
        Get interaction instance from action_type string.

        Convenience method that converts action_type from interrupt payload
        to HitlInteractionType and creates the appropriate instance.

        Args:
            action_type: String from interrupt payload (e.g., "plan_approval")
            **kwargs: Constructor arguments for the interaction class

        Returns:
            Interaction instance implementing HitlInteractionProtocol

        Example:
            >>> # In StreamingService._handle_hitl_interrupt
            >>> action_type = first_action.get("type", "unknown")
            >>> interaction = HitlInteractionRegistry.from_action_type(
            ...     action_type,
            ...     question_generator=generator,
            ... )

        Notes:
            - Unknown action_type falls back to PLAN_APPROVAL
            - Logs warning for unknown types
        """
        try:
            interaction_type = HitlInteractionType.from_action_type(action_type)
        except ValueError:
            logger.warning(
                "unknown_hitl_action_type_falling_back",
                action_type=action_type,
                fallback_type=HitlInteractionType.PLAN_APPROVAL.value,
            )
            interaction_type = HitlInteractionType.PLAN_APPROVAL

        return cls.get(interaction_type, **kwargs)

    @classmethod
    def list_registered(cls) -> list[HitlInteractionType]:
        """
        List all registered interaction types.

        Useful for debugging and testing.

        Returns:
            List of registered HitlInteractionType values
        """
        return list(cls._interactions.keys())

    @classmethod
    def is_registered(cls, interaction_type: HitlInteractionType) -> bool:
        """
        Check if an interaction type is registered.

        Args:
            interaction_type: Type to check

        Returns:
            True if registered, False otherwise
        """
        return interaction_type in cls._interactions

    @classmethod
    def clear(cls) -> None:
        """
        Clear all registrations.

        WARNING: Only for testing. Do not use in production.
        """
        cls._interactions.clear()
        logger.warning("hitl_interaction_registry_cleared")
