"""Bounded native LLM consumers with fresh authority and accounting on every exit."""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import time
from typing import Literal, Protocol
from uuid import UUID

import structlog
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, TypeAdapter

from src.core.config import settings
from src.core.constants import DISCUSSION_OPENING_MAX_CHARS
from src.core.llm_agent_config import LLMAgentConfig
from src.core.llm_config_helper import (
    get_effective_context_window_for_slot,
    get_llm_config_for_agent,
)
from src.core.llm_usage import LLMBillingRecord
from src.domains.agents.prompts.prompt_loader import PromptName, load_prompt
from src.domains.proactive_discussions.llm_contracts import (
    ContextInterpretation,
    DecisionEnvelope,
    DiscussionPhase,
    bounded_prompt_tokens,
)
from src.domains.proactive_discussions.rule_controls import RuleCompilation
from src.domains.proactive_discussions.schemas import DiscussionDecision
from src.infrastructure.cache.pricing_cache import capture_pricing_snapshot
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.llm.output_truncation import is_output_truncated
from src.infrastructure.llm.structured_output import get_structured_output
from src.infrastructure.llm.token_capture import TokenCaptureHandler
from src.infrastructure.proactive.tracking import bill_captured_usage

logger = structlog.get_logger(__name__)

DiscussionSlot = Literal["discussion_context", "discussion_decision", "discussion_message"]
#: Who asked, declared by the call site: a rebuild is the person's request, an
#: opening is LIA's initiative (registers' authorship, ``effects/source.py``).
DiscussionSource = Literal["user", "proactive"]
_CONFIG = TypeAdapter(dict[str, object])


class SpendPermit(Protocol):
    """What a model call needs from the run's financial permit."""

    async def admit(self, phase: DiscussionPhase, config: LLMAgentConfig, tokens: int) -> None:
        """Admit one call of a phase, or raise; the call is not made otherwise."""

    def record(self, records: tuple[LLMBillingRecord, ...], *, uncertain: bool) -> None:
        """Keep a call's billing records; an uncertain call forbids publication."""


class SingleAttempt(BaseCallbackHandler):
    """Refuse a second model call within one phase: no hidden retry is ever bought."""

    raise_error = True
    run_inline = True

    def __init__(self) -> None:
        self.started = 0

    def _claim(self) -> None:
        if self.started:
            raise ValueError("a discussion phase cannot buy an implicit second model call")
        self.started += 1

    def on_chat_model_start(
        self, serialized: dict[str, object], messages: list[list[BaseMessage]], **kwargs: object
    ) -> None:
        """Claim the phase's single chat-model call."""
        self._claim()

    def on_llm_start(
        self, serialized: dict[str, object], prompts: list[str], **kwargs: object
    ) -> None:
        """Claim the phase's single completion call."""
        self._claim()


@dataclass(frozen=True)
class PreparedCall:
    """One phase's bounded call: its slot, configuration, messages and prompt size."""

    slot: DiscussionSlot
    config: LLMAgentConfig
    messages: list[BaseMessage]
    input_tokens: int


_PHASE_PROMPTS: dict[DiscussionPhase, PromptName] = {
    "context": "discussion_context_prompt",
    "decision": "discussion_decision_prompt",
    "message": "discussion_message_prompt",
}


def prepare_call(
    phase: DiscussionPhase,
    content: str,
    schema: type[BaseModel] | None,
    *,
    prompt_name: PromptName | None = None,
) -> PreparedCall:
    """Bound one phase's call before any provider is created.

    Everything the call may use comes from the configured slot: its output budget
    (the slot's ``max_tokens``, already held to the output cap a vouched catalogue
    row declares), its window, its timeout. Only automatic provider retries are
    switched off: a discussion phase never buys a hidden second call (ADR-360).

    Args:
        phase: The phase, whose configured slot the call runs on.
        content: The user message (payload) of the call.
        schema: The structured output, or None for free wording.
        prompt_name: Another system prompt for the same phase (the read-rule
            compiler runs on the context slot with instructions of its own).

    Returns:
        The prepared call.

    Raises:
        PromptBudgetExceeded: When the complete prompt cannot fit the configured slot.
    """
    slots: dict[DiscussionPhase, DiscussionSlot] = {
        "context": "discussion_context",
        "decision": "discussion_decision",
        "message": "discussion_message",
    }
    slot = slots[phase]
    config = get_llm_config_for_agent(settings, slot)
    version = {
        "context": settings.discussion_context_prompt_version,
        "decision": settings.discussion_decision_prompt_version,
        "message": settings.discussion_message_prompt_version,
    }[phase]
    prompt = load_prompt(prompt_name or _PHASE_PROMPTS[phase], version)
    tokens = bounded_prompt_tokens(
        prompt,
        content,
        schema=schema,
        window=get_effective_context_window_for_slot(slot),
        output=config.max_tokens,
    )
    provider_options = _CONFIG.validate_python(json.loads(config.provider_config))
    if config.provider != "ollama":
        provider_options["max_retries"] = 0
    config = config.model_copy(update={"provider_config": json.dumps(provider_options)})
    return PreparedCall(
        slot=slot,
        config=config,
        messages=[SystemMessage(content=prompt), HumanMessage(content=content)],
        input_tokens=tokens,
    )


class DiscussionLLM:
    """The three discussion slots: every call admitted, bounded, single and billed.

    A call checks the run's authority before and after, is admitted against the
    run's reservation, is made once (no provider retry) and files its usage under
    the run, with the authorship its call site declared.
    """

    def __init__(
        self,
        owner_id: UUID,
        run_id: UUID,
        permit: SpendPermit,
        *,
        authorize: Callable[[], Awaitable[None]],
        source: DiscussionSource,
    ) -> None:
        self.owner_id, self.run_id, self.permit, self.authorize = (
            owner_id,
            run_id,
            permit,
            authorize,
        )
        self.source = source

    async def interpret(self, content: str) -> ContextInterpretation:
        """Run the context call.

        Args:
            content: The complete user message.

        Returns:
            The context interpretation; a proposal its answer could not carry is set
            aside alone and logged by reason, never by content.
        """
        output = await self._structured("context", content, ContextInterpretation)
        refused = output.refused_proposals
        if refused:
            logger.info(
                "discussion_context_proposals_refused",
                user_id=str(self.owner_id),
                run_id=str(self.run_id),
                stage="reading",
                refused=dict(sorted(refused.items())),
            )
        return output

    async def compile_rules(self, content: str) -> RuleCompilation:
        """Compile the person's statements into read restrictions, on the context slot.

        Args:
            content: The statements, as data.

        Returns:
            The denied sources, or an abstention.
        """
        return await self._structured(
            "context", content, RuleCompilation, prompt_name="discussion_rules_prompt"
        )

    async def decide(self, content: str) -> DiscussionDecision:
        """Run the decision call.

        Args:
            content: The complete user message.

        Returns:
            The decision: skip, defer or engage.
        """
        return (await self._structured("decision", content, DecisionEnvelope)).decision

    async def _structured[T: BaseModel](
        self,
        phase: DiscussionPhase,
        content: str,
        schema: type[T],
        *,
        prompt_name: PromptName | None = None,
    ) -> T:
        call = prepare_call(phase, content, schema, prompt_name=prompt_name)
        await self.authorize()
        await self.permit.admit(phase, call.config, call.input_tokens)
        model = get_llm(call.slot, config_override=call.config)
        capture, attempt = TokenCaptureHandler(call.config.model), SingleAttempt()
        failed = True
        try:
            result = await get_structured_output(
                llm=model,
                messages=call.messages,
                schema=schema,
                provider=call.config.provider,
                node_name=call.slot,
                user_id=self.owner_id,
                config=RunnableConfig(callbacks=[capture, attempt]),
            )
            await self.authorize()
            failed = False
            return result
        finally:
            await self._settle(call, capture, attempt, failed=failed)

    async def message(self, content: str) -> str:
        """Word the opening.

        Args:
            content: The complete user message.

        Returns:
            The opening's text, at most ``DISCUSSION_OPENING_MAX_CHARS`` characters.

        Raises:
            ValueError: The answer is not one complete assistant message: truncated,
                a tool call, empty or too long.
        """
        call = prepare_call("message", content, None)
        await self.authorize()
        await self.permit.admit("message", call.config, call.input_tokens)
        model = get_llm(call.slot, config_override=call.config)
        capture, attempt = TokenCaptureHandler(call.config.model), SingleAttempt()
        started, snapshot, failed = time(), capture_pricing_snapshot(), True
        try:
            raw: object = await invoke_with_instrumentation(
                llm=model,
                llm_type=call.slot,
                messages=call.messages,
                session_id=str(self.run_id),
                user_id=str(self.owner_id),
                config=RunnableConfig(callbacks=[capture, attempt]),
            )
            capture.ensure_response_record(
                raw, model_name=call.config.model, started_at=started, snapshot=snapshot
            )
            if not isinstance(raw, AIMessage) or raw.tool_calls or is_output_truncated(raw):
                raise ValueError("discussion wording is not a complete assistant message")
            text = coerce_content_to_text(raw.content).strip()
            if not text or len(text) > DISCUSSION_OPENING_MAX_CHARS:
                raise ValueError("discussion wording outside its message contract")
            await self.authorize()
            failed = False
            return text
        finally:
            await self._settle(call, capture, attempt, failed=failed)

    async def _settle(
        self,
        call: PreparedCall,
        capture: TokenCaptureHandler,
        attempt: SingleAttempt,
        *,
        failed: bool,
    ) -> None:
        records = capture.get_billing_records(call.config.model)
        # Synchronous receipt first: an outer cancellation/crash settlement owns the
        # financial reservation even if native usage persistence loses its acknowledgement.
        self.permit.record(records, uncertain=bool(attempt.started and not records))
        try:
            receipt = await bill_captured_usage(
                capture,
                user_id=self.owner_id,
                task_type="discussion",
                target_id=call.slot,
                model_name=call.config.model,
                source=self.source,
                run_id=str(self.run_id),
                failed=failed,
                llm_type=call.slot,
            )
            if records and receipt is None:
                self.permit.record((), uncertain=True)
        except BaseException:
            self.permit.record((), uncertain=True)
            raise
