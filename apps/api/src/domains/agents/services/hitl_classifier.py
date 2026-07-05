"""
HITL Response Classifier with Multi-Provider Support.

Classifies user natural language responses into approve/reject/edit/ambiguous
for conversational Human-in-the-Loop interactions.

Multi-Provider Support:
- Uses factory pattern for provider-agnostic LLM creation
- Configurable via HITL_CLASSIFIER_LLM_PROVIDER in .env
- Supports OpenAI, Anthropic, DeepSeek, Perplexity, Ollama

Usage:
    >>> classifier = HitlResponseClassifier()
    >>> result = await classifier.classify(
    ...     user_response="oui",
    ...     action_context=[{"tool_name": "search_contacts", "tool_args": {"query": "jean"}}]
    ... )
    >>> print(result.decision)  # "APPROVE"
"""

import json
from functools import lru_cache
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.field_names import FIELD_QUERY
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.agents.constants import (
    ACTION_TYPE_CREATE,
    ACTION_TYPE_DELETE,
    ACTION_TYPE_DRAFT_CRITIQUE,
    ACTION_TYPE_FOR_EACH_CONFIRMATION,
    ACTION_TYPE_GENERIC,
    ACTION_TYPE_GET,
    ACTION_TYPE_LIST,
    ACTION_TYPE_PLAN_APPROVAL,
    ACTION_TYPE_SEARCH,
    ACTION_TYPE_SEND,
)
from src.domains.agents.prompts import (
    get_current_datetime_context,
    get_hitl_classifier_prompt,
    load_prompt,
)
from src.domains.agents.services.hitl.validator import HitlValidator
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.structured_output import get_structured_output
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class ClassificationResult(BaseModel):
    """Result of HITL response classification.

    Attributes:
        decision: Classification type (APPROVE/REJECT/EDIT/REPLAN/AMBIGUOUS).
        confidence: Confidence score (0.0-1.0) for the classification.
        reasoning: Short explanation of why this classification was chosen.
        edited_params: If EDIT, dict of parameter modifications (e.g., {"query": "Huà"}).
                       If REPLAN, contains {"reformulated_intent": "user's new request"}.
        clarification_question: If AMBIGUOUS, suggested question to ask user.

    Issue #63 Enhancement:
        REPLAN is used when user requests a different action type (e.g., "detail" instead of "search").
        This triggers plan regeneration instead of parameter modification.
    """

    decision: Literal["APPROVE", "REJECT", "EDIT", "REPLAN", "AMBIGUOUS"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    edited_params: dict[str, Any] | None = None  # For EDIT or REPLAN decision
    clarification_question: str | None = None  # For AMBIGUOUS decision


@lru_cache(maxsize=1)
def _load_classifier_example_sections() -> dict[str, str]:
    """Parse the versioned classifier examples into per-action-type sections.

    Loads ``hitl_classifier_examples.txt`` (English, language-neutral) and splits
    it on ``=== <key> ===`` markers, where ``<key>`` is an ACTION_TYPE_* value.
    Cached: the file is read once per process.

    Returns:
        Mapping of action-type key to its English few-shot example block.
    """
    raw = load_prompt("hitl_classifier_examples")
    sections: dict[str, str] = {}
    current_key: str | None = None
    buffer: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("=== ") and stripped.endswith(" ==="):
            if current_key is not None:
                sections[current_key] = "\n".join(buffer).strip()
            current_key = stripped[4:-4].strip()
            buffer = []
        elif current_key is not None:
            buffer.append(line)
    if current_key is not None:
        sections[current_key] = "\n".join(buffer).strip()
    return sections


class HitlResponseClassifier:
    """Classifies user natural language responses for HITL interactions.

    Multi-Provider Support:
    - Uses LLM factory for provider-agnostic instantiation
    - Configurable via HITL_CLASSIFIER_LLM_PROVIDER in .env
    - Supports OpenAI, Anthropic, DeepSeek, Perplexity, Ollama

    Classification Decisions:
        Approve: "yes", "ok", "sure", "go ahead", "confirm"
        Reject: "no", "stop", "cancel", "not now"
        Edit: "not john but Hua", "use john@example.com instead" (same action type, different params)
        Replan: "details of X", "send to Y instead" (different action type requested)
        Ambiguous: "maybe", "I don't know", "hmm"

    Issue #63 Enhancement:
        REPLAN is triggered when user requests a different action type:
        - "search john" + "details of john" → REPLAN (search → details)
        - "list emails" + "send to john" → REPLAN (list → send)

    Architecture:
        - Temperature: 0.1 (deterministic classification)
        - JSON output format (structured response, OpenAI only)
        - Context-aware (receives action_requests for better classification)
    """

    def __init__(
        self,
        model: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
    ) -> None:
        """Initialize classifier with LLM model via factory.

        Migration notes (backward compatible):
        - Parameters are now optional (None = use settings defaults)
        - If provided, they override global settings via config_override
        - LLM creation delegated to factory (multi-provider support)

        Args:
            model: LLM model name (None = use settings.hitl_classifier_llm_model).
            temperature: Temperature for classification (None = use settings).
            top_p: Top-p (nucleus sampling) parameter (None = use settings).
            frequency_penalty: Frequency penalty parameter (None = use settings).
            presence_penalty: Presence penalty parameter (None = use settings).
        """
        # Build config_override dict (only include non-None parameters)
        config_override = {}
        if model is not None:
            config_override["model"] = model
        if temperature is not None:
            config_override["temperature"] = temperature
        if top_p is not None:
            config_override["top_p"] = top_p
        if frequency_penalty is not None:
            config_override["frequency_penalty"] = frequency_penalty
        if presence_penalty is not None:
            config_override["presence_penalty"] = presence_penalty

        # Create LLM via factory (provider-agnostic)
        self.llm: BaseChatModel = get_llm(
            llm_type="hitl_classifier",
            config_override=config_override if config_override else None,
        )

        # Resolve provider for structured output helper
        agent_config = get_llm_config_for_agent(settings, "hitl_classifier")
        self._provider = agent_config.provider

        # Log initialization with effective config
        logger.info(
            "hitl_classifier_initialized",
            provider=self._provider,
            model=model or agent_config.model,
            temperature=temperature or agent_config.temperature,
            has_override=bool(config_override),
        )

    async def classify(
        self, user_response: str, action_context: list[dict], tracker: Any | None = None
    ) -> ClassificationResult:
        """Classify user response using full LLM classification.

        DESIGN DECISION: Full LLM (no fast-path regex) to handle nuanced responses.

        Rationale:
        - Fast-path regex can miss context: "non recherche plutot jean" → REJECT instead of EDIT
        - gpt-4.1-mini-mini is fast (~200-300ms) and cheap (~$0.000015/call)
        - LLM understands full context: negation + correction, approval + modification, etc.

        Trade-off: +200ms latency vs. avoiding false negatives on EDIT patterns.

        Args:
            user_response: Natural language response from user.
            action_context: List of action_requests from interrupt.
            tracker: Optional TrackingContext for token tracking.

        Returns:
            ClassificationResult with decision, confidence, reasoning.

        Raises:
            Exception: If LLM invocation fails or response parsing fails.
        """
        import time

        from src.infrastructure.observability.metrics_agents import (
            hitl_classification_duration_seconds,
            hitl_classification_method_total,
        )

        classification_start = time.time()

        # Full LLM classification for all responses (no fast-path)
        prompt = self._build_prompt(user_response, action_context)

        try:
            # Phase 6 - LLM Observability: Use instrumented config for Langfuse tracing
            from src.infrastructure.llm.instrumentation import create_instrumented_config

            # Create instrumented config with Langfuse callbacks
            # Merge with TokenTrackingCallback if provided
            config = create_instrumented_config(
                llm_type="hitl_classifier",
                # session_id and user_id would be passed from caller if available
                tags=["hitl", "classification"],
                metadata={
                    "user_response_length": len(user_response),
                    "action_count": len(action_context) if action_context else 0,
                },
            )

            # Merge token tracker if provided (for accurate cost tracking)
            if tracker:
                existing_callbacks = config.get("callbacks", [])
                config["callbacks"] = existing_callbacks + [tracker]

            # Call LLM with structured output (provider-agnostic via helper)
            try:
                classification = await get_structured_output(
                    llm=self.llm,
                    messages=prompt,
                    schema=ClassificationResult,
                    provider=self._provider,
                    node_name="hitl_classifier",
                    config=config,
                )
            except Exception as structured_err:
                # Fallback: raw invoke + manual JSON parsing for providers
                # that don't support structured output reliably
                logger.warning(
                    "hitl_structured_output_fallback",
                    error=str(structured_err),
                    error_type=type(structured_err).__name__,
                    msg="Structured output failed, falling back to raw invoke + JSON parsing",
                )
                result = await self.llm.ainvoke(prompt, config=config)
                content = result.text
                classification = self._parse_result(content)
            classification_duration = time.time() - classification_start

            # Record LLM classification metrics
            from src.core.config import get_settings
            from src.infrastructure.observability.metrics_agents import (
                hitl_classification_confidence,
                hitl_classification_demoted_total,
            )

            settings = get_settings()

            hitl_classification_method_total.labels(
                method="llm", decision=classification.decision
            ).inc()
            hitl_classification_duration_seconds.labels(method="llm").observe(
                classification_duration
            )
            hitl_classification_confidence.labels(decision=classification.decision).observe(
                classification.confidence
            )

            logger.info(
                "hitl_classification_completed",
                decision=classification.decision,
                confidence=classification.confidence,
                user_response=user_response[:50],
                duration_ms=round(classification_duration * 1000, 2),
            )

            # PRODUCTION FIX 1: Demote EDIT with missing params to AMBIGUOUS
            # If LLM classifies as EDIT but fails to extract edited_params,
            # treat as AMBIGUOUS and ask for clarification
            if classification.decision == "EDIT" and not classification.edited_params:
                reasoning_preview = (
                    classification.reasoning[:100] if classification.reasoning else ""
                )
                logger.warning(
                    "edit_decision_demoted_missing_params",
                    original_confidence=classification.confidence,
                    reasoning_preview=reasoning_preview,
                    user_response=user_response[:50],
                    has_clarification=bool(classification.clarification_question),
                )

                # Convert to AMBIGUOUS with existing or fallback clarification
                classification.decision = "AMBIGUOUS"
                if not classification.clarification_question:
                    classification.clarification_question = (
                        "Tu veux modifier quelque chose ? Peux-tu préciser exactement quoi ?"
                        if user_response
                        else "Peux-tu clarifier ta demande ?"
                    )
                classification.confidence = settings.hitl_demotion_confidence
                classification.edited_params = {}  # Clear empty params

                # Track demotion for monitoring
                hitl_classification_demoted_total.labels(
                    from_decision="EDIT", to_decision="AMBIGUOUS", reason="missing_params"
                ).inc()

            # PRODUCTION FIX 2: Demote low-confidence EDIT to AMBIGUOUS
            # Prevents false positives when LLM is uncertain about EDIT intent
            # Threshold: Configurable via HITL_CLASSIFIER_CONFIDENCE_THRESHOLD (default: 0.7)
            #
            # Issue #60 Fix: Don't demote if edited_params contains valid values!
            # If the LLM extracted actual parameters, trust the extraction even with lower confidence.
            # This fixes plan-level HITL where user says "juste 2" → EDIT {max_results: 2}
            elif (
                classification.decision == "EDIT"
                and classification.confidence < settings.hitl_classifier_confidence_threshold
                and not classification.edited_params  # Only demote if no params extracted
            ):
                reasoning_preview = (
                    classification.reasoning[:100] if classification.reasoning else ""
                )
                logger.warning(
                    "edit_decision_demoted_to_ambiguous",
                    original_confidence=classification.confidence,
                    reasoning_preview=reasoning_preview,
                    user_response=user_response[:50],
                )

                # Convert to AMBIGUOUS with clarification request
                classification.decision = "AMBIGUOUS"
                classification.clarification_question = (
                    "Tu veux modifier quelque chose ? Peux-tu préciser exactement quoi ?"
                    if user_response
                    else "Peux-tu clarifier ta demande ?"
                )
                classification.confidence = settings.hitl_demotion_confidence
                classification.edited_params = {}  # Clear uncertain edits

                # Track demotion for monitoring
                hitl_classification_demoted_total.labels(
                    from_decision="EDIT", to_decision="AMBIGUOUS", reason="low_confidence"
                ).inc()

            # METRICS: Track clarification fallback (AMBIGUOUS decisions)
            if classification.decision == "AMBIGUOUS":
                from src.infrastructure.observability.metrics_agents import (
                    hitl_clarification_fallback_total,
                )

                hitl_clarification_fallback_total.inc()

            return classification

        except Exception as e:
            logger.error(
                "hitl_classification_error",
                error=str(e),
                user_response=user_response[:50],
            )
            raise

    def _build_prompt(self, response: str, context: list[dict]) -> list:
        """Build optimized classification prompt with action type context.

        Args:
            response: User response string.
            context: Action context from interrupt.

        Returns:
            List of messages for LLM (system + user message if needed).
        """
        # Extract action type and description
        action_type = self._extract_action_type(context)
        action_desc = self._format_action_context(context)

        # Get contextualized examples for this action type
        examples = self._get_contextual_examples(action_type, action_desc)

        # Build prompt with action type context using versioned settings
        from src.core.config import get_settings

        settings = get_settings()

        try:
            # Load versioned HITL classifier prompt (version controlled via settings)
            prompt_template = load_prompt(
                "hitl_classifier_prompt", version=settings.hitl_classifier_prompt_version
            )
            # Get current datetime for prompt context
            current_datetime = get_current_datetime_context()
            system_prompt = prompt_template.format(
                action_type=action_type,
                action_desc=action_desc,
                response=response,
                current_datetime=current_datetime,
            )
            # Replace examples placeholder
            system_prompt = system_prompt.replace("{{EXAMPLES_PLACEHOLDER}}", examples)
        except FileNotFoundError:
            # Fallback to legacy function if prompt file not found
            logger.warning(
                "hitl_classifier_prompt not found, using fallback",
                version=settings.hitl_classifier_prompt_version,
            )
            system_prompt = get_hitl_classifier_prompt(action_desc, response)

        return [SystemMessage(content=system_prompt)]

    def _extract_action_type(self, context: list[dict]) -> str:
        """Extract action type for contextualized classification.

        Issue #61 Fix: Added support for plan_approval type.

        Args:
            context: List of action_requests dicts.

        Returns:
            Action type constant from constants.py
        """
        if not context or len(context) != 1:
            return ACTION_TYPE_GENERIC

        action = context[0]

        # Issue #61: Check for plan_approval type FIRST (before tool extraction)
        # Plan-level HITL has "type": "plan_approval" instead of tool_name
        action_type = action.get("type", "")
        if action_type == "plan_approval":
            return ACTION_TYPE_PLAN_APPROVAL

        # Draft critique: HITL for draft review before execution
        if action_type == "draft_critique":
            return ACTION_TYPE_DRAFT_CRITIQUE

        # FOR_EACH confirmation: HITL for bulk operations on item lists
        if action_type == "for_each_confirmation":
            return ACTION_TYPE_FOR_EACH_CONFIRMATION

        # PHASE 3.2.8: Use centralized validator for tool extraction
        validator = HitlValidator()
        try:
            tool_name = validator.extract_tool_name(action)
        except ValueError:
            tool_name = "action"

        tool_name_lower = tool_name.lower()

        if "search" in tool_name_lower or "recherche" in tool_name_lower:
            return ACTION_TYPE_SEARCH
        elif "send" in tool_name_lower or "envoi" in tool_name_lower or "email" in tool_name_lower:
            return ACTION_TYPE_SEND
        elif "delete" in tool_name_lower or "suppr" in tool_name_lower:
            return ACTION_TYPE_DELETE
        elif "create" in tool_name_lower or "add" in tool_name_lower:
            return ACTION_TYPE_CREATE
        elif "list" in tool_name_lower:
            return ACTION_TYPE_LIST
        elif "get" in tool_name_lower or "details" in tool_name_lower:
            return ACTION_TYPE_GET
        else:
            return ACTION_TYPE_GENERIC

    def _get_contextual_examples(self, action_type: str, action_desc: str) -> str:
        """Load language-neutral (English) few-shot examples for the action type.

        Examples are externalized to the versioned prompt
        ``hitl_classifier_examples.txt`` (English) so the classifier is not
        biased toward any single user language: the user response may be in
        any language and is classified by intent structure, not by matching
        words. ``action_desc`` is accepted for backward-compatible call sites.

        Args:
            action_type: Type of action (from ACTION_TYPE_* constants).
            action_desc: Description of the specific action (unused).

        Returns:
            The English few-shot example block for the action type.
        """
        del action_desc  # examples are action-type-scoped; kept for compatibility
        sections = _load_classifier_example_sections()
        return sections.get(action_type, sections["default"])

    def _format_action_context(self, context: list[dict]) -> str:
        """Format action_requests for prompt context.

        Issue #61 Fix: Added support for plan_approval type.

        Args:
            context: List of action_requests dicts.

        Returns:
            Human-readable description of actions.
        """
        if not context:
            return "an action"

        if len(context) == 1:
            action = context[0]

            # Issue #61: Handle plan_approval type specifically
            if action.get("type") == "plan_approval":
                return self._format_plan_approval_context(action)

            # Draft critique: Format draft content for modification instructions
            if action.get("type") == "draft_critique":
                return self._format_draft_critique_context(action)

            # FOR_EACH confirmation: Format item list for exclusion criteria
            if action.get("type") == "for_each_confirmation":
                return self._format_for_each_context(action)

            # PHASE 3.2.8: Use centralized validator for tool extraction
            validator = HitlValidator()
            try:
                tool_name = validator.extract_tool_name(action)
            except ValueError:
                tool_name = "action"

            tool_args = validator.extract_tool_args(action)

            # Format nicely based on tool type
            # Include parameter names for EDIT extraction
            if "search" in tool_name.lower():
                query = tool_args.get(FIELD_QUERY) or tool_args.get("q") or ""
                return f"search for '{query}' (parameter: query)"
            elif "delete" in tool_name.lower():
                return f"deletion ({tool_name})"
            elif "send" in tool_name.lower():
                return f"send ({tool_name})"
            elif "create" in tool_name.lower():
                return f"creation ({tool_name})"
            else:
                return f"{tool_name} with {tool_args}"

        else:
            # Multiple actions (future multi-HITL)
            return f"{len(context)} actions"

    def _format_plan_approval_context(self, action: dict) -> str:
        """Format plan_approval action context for classifier prompt.

        Issue #61 Fix: Uses tool manifests to extract parameter metadata
        (name, type, description) for generic EDIT detection across all agents.

        This is fully generic - works for contacts, emails, calendar, drive,
        or any future agent without code changes.

        Args:
            action: Plan approval action dict with plan_summary.

        Returns:
            Human-readable description with editable parameters and their descriptions.
        """
        from src.domains.agents.registry import get_global_registry

        plan_summary = action.get("plan_summary", {})
        steps = plan_summary.get("steps", [])
        total_steps = plan_summary.get("total_steps", len(steps))

        # Get registry for manifest lookups
        registry = get_global_registry()

        # Extract ALL editable parameters from steps using manifest metadata
        editable_params = []
        for step in steps:
            tool_name = step.get("tool_name", "")
            params = step.get("parameters", {})

            # Get parameter descriptions from tool manifest (generic approach)
            param_descriptions = {}
            if tool_name:
                try:
                    manifest = registry.get_tool_manifest(tool_name)
                    # Build lookup: param_name -> description
                    for param_schema in manifest.parameters:
                        param_descriptions[param_schema.name] = param_schema.description
                except Exception:
                    # Manifest not found - continue without descriptions
                    pass

            for key, value in params.items():
                # Include all primitive types (int, str, bool)
                if isinstance(value, int | str | bool):
                    # Truncate long string values for readability
                    if isinstance(value, str) and len(value) > 30:
                        display_value = f'"{value[:27]}..."'
                    elif isinstance(value, str):
                        display_value = f'"{value}"'
                    else:
                        display_value = str(value)

                    # Add description from manifest if available
                    param_desc = param_descriptions.get(key, "")
                    if param_desc:
                        # Include short description to help LLM understand parameter purpose
                        short_desc = param_desc[:50] + "..." if len(param_desc) > 50 else param_desc
                        editable_params.append(f"{key}={display_value} ({short_desc})")
                    else:
                        editable_params.append(f"{key}={display_value}")

        # Build context description
        if editable_params:
            params_str = ", ".join(editable_params)
            return f"execution plan with {total_steps} steps (editable parameters: {params_str})"
        else:
            return f"execution plan with {total_steps} steps"

    def _format_draft_critique_context(self, action: dict) -> str:
        """Format draft_critique action context for classifier prompt.

        Provides draft summary to help LLM understand what user wants to modify.
        For EDIT decisions, the LLM should extract modification_instructions.

        Args:
            action: Draft critique action dict with draft_type, draft_content, draft_id.

        Returns:
            Human-readable description of the draft being reviewed.
        """
        draft_type = action.get("draft_type", "unknown")
        draft_content = action.get("draft_content", {})

        # Build summary based on draft type
        if draft_type == "email":
            to_addr = draft_content.get("to", "?")
            subject = draft_content.get("subject", "")
            body_preview = draft_content.get("body", "")[:100]
            if len(draft_content.get("body", "")) > 100:
                body_preview += "..."
            return (
                f"email draft to {to_addr}, " f"subject: '{subject}', " f"content: '{body_preview}'"
            )

        elif draft_type == "email_reply":
            to_addr = draft_content.get("to", "?")
            body_preview = draft_content.get("body", "")[:100]
            return f"reply draft to {to_addr}, content: '{body_preview}'"

        elif draft_type == "email_forward":
            to_addr = draft_content.get("to", "?")
            return f"forward draft to {to_addr}"

        elif draft_type == "event":
            summary = draft_content.get("summary", "?")
            start = draft_content.get("start_datetime", "?")
            return f"event draft '{summary}' on {start}"

        elif draft_type == "event_update":
            summary = draft_content.get("summary", "?")
            return f"event update '{summary}'"

        elif draft_type == "contact":
            name = draft_content.get("name", "?")
            email = draft_content.get("email", "")
            return f"contact draft '{name}' ({email})"

        elif draft_type == "contact_update":
            name = draft_content.get("name", "?")
            return f"contact update '{name}'"

        elif draft_type == "task":
            title = draft_content.get("title", "?")
            return f"task draft '{title}'"

        elif draft_type == "task_update":
            title = draft_content.get("title", "?")
            return f"task update '{title}'"

        else:
            return f"draft of type '{draft_type}'"

    def _format_for_each_context(self, action: dict) -> str:
        """Format for_each_confirmation action context for classifier prompt.

        Provides item list summary to help LLM understand what the user might
        want to exclude from the bulk operation.

        Args:
            action: FOR_EACH confirmation action dict with item_previews and total_affected.

        Returns:
            Human-readable description of the items being affected.
        """
        total_affected = action.get("total_affected", 0)
        item_previews = action.get("item_previews", [])
        steps = action.get("steps", [])

        # Extract action type from first step
        action_description = "operation"
        if steps:
            first_step = steps[0]
            tool_name = first_step.get("tool_name", "")
            if "delete" in tool_name.lower() or "suppr" in tool_name.lower():
                action_description = "deletion"
            elif "label" in tool_name.lower():
                action_description = "labeling"
            elif "send" in tool_name.lower():
                action_description = "send"
            elif "create" in tool_name.lower():
                action_description = "creation"
            elif "update" in tool_name.lower():
                action_description = "update"

        # Build item list preview for context
        items_preview = ""
        if item_previews:
            preview_lines = []
            for i, preview in enumerate(item_previews[:5]):  # First 5 for context
                # Extract readable info from preview
                preview_text = " | ".join(str(v)[:30] for v in preview.values() if v is not None)
                preview_lines.append(f"  {i + 1}. {preview_text}")

            items_preview = "\n".join(preview_lines)
            if len(item_previews) > 5:
                items_preview += f"\n  ... and {len(item_previews) - 5} more"

        context_str = f"{action_description} on {total_affected} item(s)"
        if items_preview:
            context_str += f"\n\nAffected items:\n{items_preview}"

        return context_str

    def _parse_result(self, json_content: str) -> ClassificationResult:
        """Parse JSON result from LLM into ClassificationResult.

        Args:
            json_content: JSON string from LLM.

        Returns:
            ClassificationResult object.

        Raises:
            ValueError: If JSON is invalid or missing required fields.
        """
        try:
            # Strip markdown code blocks if present (LLM sometimes wraps JSON in ```json ... ```)
            content = json_content.strip()
            if content.startswith("```json"):
                content = content[7:]  # Remove ```json
            elif content.startswith("```"):
                content = content[3:]  # Remove ```
            if content.endswith("```"):
                content = content[:-3]  # Remove trailing ```
            content = content.strip()

            data = json.loads(content)

            # Validate required fields
            if "decision" not in data or "confidence" not in data or "reasoning" not in data:
                raise ValueError(f"Missing required fields in classification response: {data}")

            return ClassificationResult(**data)

        except json.JSONDecodeError as e:
            logger.error("json_parse_error", error=str(e), content=json_content[:200])
            raise ValueError(f"Invalid JSON from classifier: {e}") from e
        except Exception as e:
            logger.error("result_parse_error", error=str(e), content=json_content[:200])
            raise
