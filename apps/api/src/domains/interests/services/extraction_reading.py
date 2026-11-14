"""What the interest extractor reads, and how its answer is read back.

Two pure helpers of ``extraction_service``: the conversation as the extractor
sees it (only the person and LIA, each message stamped in the person's zone,
ADR-381 amendment) and the parsing of its JSON answer, under the confidence
floor. Neither reads the database, a cache or a model.
"""

from datetime import tzinfo

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from src.core.config import settings
from src.core.constants import INTEREST_EXTRACTION_QUERY_TRUNCATION_LENGTH
from src.domains.agents.utils.json_parser import extract_json_from_llm_response
from src.domains.interests.schemas import ExtractedInterest
from src.domains.shared.extraction_targets import is_synthetic_message
from src.infrastructure.llm.message_view import written_prefix
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def format_messages_for_extraction(messages: list[BaseMessage], *, zone: tzinfo) -> str:
    """
    Format messages for extraction prompt.

    Converts LangChain messages to readable conversation format. Only the
    conversation itself is kept: tool results and system scaffolding are
    dropped, mirroring the journals extractor
    (``domains/journals/extraction_service``), which has always skipped them.

    They used to reach the prompt under a ``SYSTEM`` label. The context window
    is the four messages preceding the new user message, so right after a tool
    call it carried a raw tool payload — a contact list, a message body — into
    a prompt whose only question is "what does the USER care about". That both
    invited an interest inferred from data the user never mentioned, and copied
    personal data into a prompt that has no use for it.

    Args:
        messages: List of conversation messages
        zone: The person's display zone: a message carrying the instant it was
            written starts with it, in that zone (ADR-381 amendment).

    Returns:
        Formatted conversation string
    """
    lines = []
    max_chars = INTEREST_EXTRACTION_QUERY_TRUNCATION_LENGTH

    for msg in messages:
        if isinstance(msg, HumanMessage):
            # System-fabricated HITL scaffolding is not conversation.
            if is_synthetic_message(msg):
                continue
            prefix = "USER"
        elif isinstance(msg, AIMessage):
            # Skip proactive notifications (interest/heartbeat) — not user-generated content
            if msg.additional_kwargs.get("proactive_notification"):
                continue
            prefix = "ASSISTANT"
        else:
            continue  # Skip tool messages, system messages

        content = str(msg.text)
        # Truncate very long messages
        if len(content) > max_chars:
            content = content[:max_chars] + "..."

        lines.append(f"{prefix}: {written_prefix(msg, zone)}{content}")

    return "\n".join(lines)


def parse_extraction_result(result_text: str) -> list[ExtractedInterest]:
    """
    Parse LLM extraction result into ExtractedInterest objects.

    Handles common JSON parsing issues (markdown fences, whitespace, comments).

    Args:
        result_text: Raw LLM output

    Returns:
        List of validated ExtractedInterest objects
    """

    def _parse_items(data: list) -> list[ExtractedInterest]:
        interests: list[ExtractedInterest] = []
        for item in data:
            try:
                action = item.get("action", "create")

                # Filter by minimum confidence (only for create actions)
                if action == "create":
                    confidence = item.get("confidence", 0)
                    if confidence < settings.interest_extraction_min_confidence:
                        logger.debug(
                            "interest_extraction_low_confidence",
                            topic=item.get("topic", "")[:50],
                            confidence=confidence,
                        )
                        continue

                interest = ExtractedInterest(**item)
                interests.append(interest)
            except Exception as e:
                logger.debug(
                    "interest_item_validation_failed",
                    item=item,
                    error=str(e),
                )
                continue
        return interests

    # Central parser handles fences, array extraction, trailing commas and //
    # comments (strict-first, instrumented via json_parse_* with this context).
    result = extract_json_from_llm_response(
        result_text, expected_type=list, context="interest_extraction"
    )
    if not result.success or not isinstance(result.data, list):
        return []
    return _parse_items(result.data)
