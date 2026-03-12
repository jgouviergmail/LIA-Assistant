"""
Rejection Decision Builder Policy.

This policy builds rejection decisions with metrics tracking and i18n messages.

Architecture:
- Builds structured rejection decisions from classification results
- Infers rejection type (explicit_no, low_confidence, implicit_no)
- Tracks metrics for rejection reasons and types
- Generates i18n rejection messages in 6 languages
"""

from typing import TYPE_CHECKING, Any

from structlog import get_logger

if TYPE_CHECKING:
    from src.domains.agents.services.hitl.validator import HitlValidator

logger = get_logger(__name__)


class RejectionDecisionBuilder:
    """
    Policy class for building rejection decisions.

    Handles rejection decision construction with metrics tracking,
    rejection type inference, and i18n message generation.
    """

    def __init__(self, agent_type: str = "generic"):
        """
        Initialize rejection builder.

        Args:
            agent_type: Agent type label for metrics (e.g., "contacts_agent")
        """
        self.agent_type = agent_type

    def build(
        self,
        action: dict[str, Any],
        reasoning: str,
        user_response: str,
        classification: Any,
        validator: "HitlValidator",
        user_language: str = "en",
    ) -> dict[str, Any]:
        """
        Build rejection decision with metrics tracking and i18n message.

        Args:
            action: Tool action to reject
            reasoning: Classification reasoning
            user_response: User's original natural language response
            classification: ClassificationResult or dict
            validator: HitlValidator instance for tool extraction
            user_language: User's language code (e.g., "fr", "en"). Default: "en"

        Returns:
            Decision dict with type="reject" and message

        Example:
            >>> builder = RejectionDecisionBuilder(agent_type="contacts_agent")
            >>> decision = builder.build(
            ...     action={"name": "delete_contact", "args": {"id": "123"}},
            ...     reasoning="User explicitly rejected",
            ...     user_response="non annule ça",
            ...     classification=classification_result,
            ...     validator=validator,
            ...     user_language="fr"
            ... )
            >>> decision["type"]  # "reject"
        """
        from src.domains.agents.api.error_messages import SSEErrorMessages, SupportedLanguage
        from src.infrastructure.observability.metrics_agents import (
            hitl_rejection_type_total,
            hitl_tool_rejections_by_reason,
        )

        # Extract tool name
        try:
            tool_name = validator.extract_tool_name(action)
        except ValueError:
            tool_name = "unknown"

        # Track metrics
        rejection_type = self.infer_rejection_type(user_response, classification)
        hitl_tool_rejections_by_reason.labels(
            tool_name=tool_name,
            rejection_type=rejection_type,
        ).inc()

        hitl_rejection_type_total.labels(
            rejection_type=rejection_type,
            agent_type=self.agent_type,
        ).inc()

        logger.debug(
            "hitl_tool_rejection_tracked",
            tool_name=tool_name,
            rejection_type=rejection_type,
            agent_type=self.agent_type,
            reasoning=reasoning,
        )

        # Build i18n rejection message
        # Validate language is supported, fallback to "fr"
        supported_langs: set[SupportedLanguage] = {"fr", "en", "es", "de", "it", "zh-CN"}
        lang: SupportedLanguage = "fr"
        if user_language in supported_langs:
            lang = user_language  # type: ignore[assignment]
        rejection_msg = SSEErrorMessages.hitl_rejection_message(
            reasoning=reasoning,
            language=lang,
        )

        return {
            "type": "reject",
            "message": rejection_msg,
        }

    @staticmethod
    def infer_rejection_type(user_response: str, classification: dict[str, Any] | Any) -> str:
        """
        Infer the type of rejection from user response and classification.

        Categorizes rejections into:
        - explicit_no: User explicitly said no/annule/stop
        - low_confidence: Classification had low confidence
        - implicit_no: User reformulated/corrected without explicit rejection

        Args:
            user_response: User's natural language response
            classification: Classification result with confidence and reasoning

        Returns:
            Rejection type string for metrics labeling

        Example:
            >>> RejectionDecisionBuilder.infer_rejection_type("non annule ça", classification)
            'explicit_no'
            >>> RejectionDecisionBuilder.infer_rejection_type("plutôt paul durand", classification)
            'implicit_no'
        """
        user_lower = user_response.lower()

        # Explicit rejection keywords (i18n: fr, en, es, de, it, zh-CN)
        explicit_keywords = [
            # fr
            "non",
            "annule",
            "stop",
            "arrête",
            "arrêté",
            "refuse",
            "jamais",
            "pas",
            "annuler",
            "refuser",
            "ne pas",
            "n'envoie pas",
            # en
            "no",
            "cancel",
            "stop",
            "refuse",
            "never",
            "don't",
            "do not",
            "nope",
            "abort",
            "reject",
            "decline",
            # es
            "no",
            "cancelar",
            "parar",
            "detener",
            "rechazar",
            "nunca",
            "anular",
            # de
            "nein",
            "abbrechen",
            "stopp",
            "ablehnen",
            "niemals",
            "nicht",
            # it
            "no",
            "annulla",
            "ferma",
            "rifiuta",
            "mai",
            "non",
            # zh-CN
            "不",
            "取消",
            "停止",
            "拒绝",
            "不要",
            "否",
        ]

        if any(keyword in user_lower for keyword in explicit_keywords):
            return "explicit_no"

        # Low confidence classification - handle both object and dict
        from src.core.config import get_settings

        settings = get_settings()
        confidence = (
            classification.confidence
            if hasattr(classification, "confidence")
            else classification.get("confidence", 1.0)
        )
        if confidence < settings.hitl_low_confidence_threshold:
            return "low_confidence"

        # Default: Implicit rejection (reformulation, correction)
        return "implicit_no"


__all__ = [
    "RejectionDecisionBuilder",
]
