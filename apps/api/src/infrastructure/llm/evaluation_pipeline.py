"""
LLM-as-Judge Evaluation Pipeline.

Implements evaluation metrics for LLM outputs:
- RelevanceEvaluator: Scores response relevance to user query
- HallucinationEvaluator: Detects hallucinated content
- LatencyEvaluator: Scores response time against SLA thresholds

Integration:
- Prometheus metrics: langfuse_evaluation_score histogram
- Langfuse: Score submission to trace

Phase: 3.1.3 - Evaluation Scores Tracking
Created: 2025-12-18
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel

from src.core.config import settings
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_langfuse import langfuse_evaluation_score

logger = get_logger(__name__)


# ============================================================================
# DATA MODELS
# ============================================================================


@dataclass
class EvaluationResult:
    """Result of an evaluation."""

    metric_name: str
    score: float  # 0.0 to 1.0
    reasoning: str | None = None
    metadata: dict[str, Any] | None = None


class RelevanceScore(BaseModel):
    """Structured output for relevance evaluation."""

    score: float
    reasoning: str


class HallucinationScore(BaseModel):
    """Structured output for hallucination detection."""

    score: float
    hallucinated_claims: list[str]
    reasoning: str


# ============================================================================
# BASE EVALUATOR
# ============================================================================


class BaseEvaluator(ABC):
    """Abstract base class for LLM-as-judge evaluators."""

    metric_name: str

    @abstractmethod
    async def evaluate(
        self,
        query: str,
        response: str,
        context: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        """
        Evaluate an LLM response.

        Args:
            query: Original user query
            response: LLM response to evaluate
            context: Additional context (tool results, ground truth, etc.)

        Returns:
            EvaluationResult with score and optional reasoning
        """
        pass

    def _record_metric(self, score: float) -> None:
        """Record evaluation score to Prometheus."""
        langfuse_evaluation_score.labels(metric_name=self.metric_name).observe(score)
        logger.debug(
            "evaluation_score_recorded",
            metric_name=self.metric_name,
            score=score,
        )


# ============================================================================
# RELEVANCE EVALUATOR
# ============================================================================


class RelevanceEvaluator(BaseEvaluator):
    """
    Evaluates response relevance to the user query.

    Uses LLM-as-judge pattern to score how well the response
    addresses the user's question or request.
    """

    metric_name = "relevance"

    RELEVANCE_PROMPT = """You are an expert evaluator assessing response relevance.

Given a user query and an AI response, evaluate how well the response addresses the query.

Score criteria:
- 1.0: Perfect - Directly and completely addresses the query
- 0.8: Good - Addresses the query with minor gaps
- 0.6: Acceptable - Partially addresses the query
- 0.4: Poor - Tangentially related but misses key points
- 0.2: Very Poor - Mostly irrelevant
- 0.0: Completely irrelevant

User Query:
{query}

AI Response:
{response}

Provide your evaluation in JSON format with 'score' (float 0-1) and 'reasoning' (string)."""

    def __init__(self) -> None:
        self._llm: BaseChatModel | None = None

    @property
    def llm(self) -> BaseChatModel:
        """Lazy-load LLM via factory (provider-agnostic)."""
        if self._llm is None:
            self._llm = get_llm(
                "evaluator",
                config_override={
                    "max_tokens": settings.observability.evaluator_relevance_max_tokens
                },
            )
        return self._llm

    async def evaluate(
        self,
        query: str,
        response: str,
        context: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        """Evaluate response relevance."""
        try:
            from src.infrastructure.llm.invoke_helpers import (
                enrich_config_with_node_metadata,
            )

            prompt = self.RELEVANCE_PROMPT.format(query=query, response=response)
            structured_llm = self.llm.with_structured_output(RelevanceScore)
            invoke_config = enrich_config_with_node_metadata(None, "evaluation_relevance")
            result: RelevanceScore = await structured_llm.ainvoke(prompt, config=invoke_config)

            self._record_metric(result.score)

            return EvaluationResult(
                metric_name=self.metric_name,
                score=result.score,
                reasoning=result.reasoning,
            )
        except Exception as e:
            logger.error(
                "relevance_evaluation_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            # Return neutral score on failure
            return EvaluationResult(
                metric_name=self.metric_name,
                score=0.5,
                reasoning=f"Evaluation failed: {e!s}",
            )


# ============================================================================
# HALLUCINATION EVALUATOR
# ============================================================================


class HallucinationEvaluator(BaseEvaluator):
    """
    Detects hallucinated content in responses.

    Can optionally use ground truth data to improve detection accuracy.
    Score represents confidence that response is NOT hallucinated (1.0 = no hallucination).
    """

    metric_name = "hallucination"

    HALLUCINATION_PROMPT = """You are an expert evaluator detecting hallucinations in AI responses.

A hallucination is a claim that:
- Cannot be verified from the provided context
- Contradicts the provided context
- Makes up specific details (names, dates, numbers) without basis

User Query:
{query}

AI Response:
{response}

{context_section}

Score criteria (inverted - higher = better):
- 1.0: No hallucinations detected
- 0.8: Minor unverifiable details
- 0.6: Some questionable claims
- 0.4: Several hallucinated claims
- 0.2: Many hallucinations
- 0.0: Response is mostly hallucinated

Provide your evaluation in JSON format with:
- 'score' (float 0-1, higher = less hallucination)
- 'hallucinated_claims' (list of specific hallucinated claims found)
- 'reasoning' (string explanation)"""

    def __init__(self) -> None:
        self._llm: BaseChatModel | None = None

    @property
    def llm(self) -> BaseChatModel:
        """Lazy-load LLM via factory (provider-agnostic)."""
        if self._llm is None:
            self._llm = get_llm(
                "evaluator",
                config_override={
                    "max_tokens": settings.observability.evaluator_hallucination_max_tokens,
                },
            )
        return self._llm

    async def evaluate(
        self,
        query: str,
        response: str,
        context: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        """Evaluate response for hallucinations."""
        # Check if ground truth is required but not provided
        if settings.observability.evaluator_hallucination_require_ground_truth:
            if not context or "ground_truth" not in context:
                return EvaluationResult(
                    metric_name=self.metric_name,
                    score=0.5,
                    reasoning="Ground truth required but not provided",
                )

        # Build context section
        context_section = ""
        if context:
            if "ground_truth" in context:
                context_section = f"Ground Truth:\n{context['ground_truth']}"
            elif "tool_results" in context:
                context_section = f"Tool Results (source data):\n{context['tool_results']}"

        try:
            prompt = self.HALLUCINATION_PROMPT.format(
                query=query,
                response=response,
                context_section=context_section or "No additional context provided.",
            )
            from src.infrastructure.llm.invoke_helpers import (
                enrich_config_with_node_metadata,
            )

            structured_llm = self.llm.with_structured_output(HallucinationScore)
            invoke_config = enrich_config_with_node_metadata(None, "evaluation_hallucination")
            result: HallucinationScore = await structured_llm.ainvoke(prompt, config=invoke_config)

            self._record_metric(result.score)

            return EvaluationResult(
                metric_name=self.metric_name,
                score=result.score,
                reasoning=result.reasoning,
                metadata={"hallucinated_claims": result.hallucinated_claims},
            )
        except Exception as e:
            logger.error(
                "hallucination_evaluation_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            return EvaluationResult(
                metric_name=self.metric_name,
                score=0.5,
                reasoning=f"Evaluation failed: {e!s}",
            )


# ============================================================================
# LATENCY EVALUATOR
# ============================================================================


class LatencyEvaluator(BaseEvaluator):
    """
    Scores response latency against SLA thresholds.

    No LLM call required - uses configurable thresholds to compute score.
    """

    metric_name = "latency"

    async def evaluate(
        self,
        query: str,
        response: str,
        context: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        """
        Evaluate response latency.

        Args:
            query: Not used
            response: Not used
            context: Must contain 'latency_ms' key with response time in milliseconds

        Returns:
            EvaluationResult with latency score
        """
        if not context or "latency_ms" not in context:
            return EvaluationResult(
                metric_name=self.metric_name,
                score=0.5,
                reasoning="Latency data not provided",
            )

        latency_ms = context["latency_ms"]
        score = self._compute_latency_score(latency_ms)

        self._record_metric(score)

        return EvaluationResult(
            metric_name=self.metric_name,
            score=score,
            reasoning=f"Latency: {latency_ms:.0f}ms",
            metadata={"latency_ms": latency_ms},
        )

    def _compute_latency_score(self, latency_ms: float) -> float:
        """Compute score based on latency thresholds."""
        obs = settings.observability

        if latency_ms <= obs.evaluator_latency_excellent_threshold_ms:
            return 1.0
        elif latency_ms <= obs.evaluator_latency_good_threshold_ms:
            return 0.85
        elif latency_ms <= obs.evaluator_latency_acceptable_threshold_ms:
            return 0.65
        elif latency_ms <= obs.evaluator_latency_slow_threshold_ms:
            return 0.45
        else:
            return 0.2


# ============================================================================
# EVALUATION PIPELINE
# ============================================================================


class EvaluationPipeline:
    """
    Orchestrates multiple evaluators for comprehensive LLM output assessment.

    Usage:
        pipeline = EvaluationPipeline()
        results = await pipeline.evaluate_all(
            query="What's the weather?",
            response="It's sunny today.",
            context={"latency_ms": 450},
        )

    Integration with Langfuse:
        if settings.observability.evaluator_pipeline_send_to_langfuse:
            # Results are automatically sent to Langfuse via metrics
            pass
    """

    def __init__(self) -> None:
        self.evaluators: list[BaseEvaluator] = [
            RelevanceEvaluator(),
            HallucinationEvaluator(),
            LatencyEvaluator(),
        ]

    async def evaluate_all(
        self,
        query: str,
        response: str,
        context: dict[str, Any] | None = None,
    ) -> list[EvaluationResult]:
        """
        Run all evaluators and return results.

        Args:
            query: Original user query
            response: LLM response to evaluate
            context: Additional context for evaluators

        Returns:
            List of EvaluationResult from all evaluators
        """
        if not settings.observability.evaluator_enabled:
            logger.debug("evaluation_pipeline_disabled")
            return []

        results: list[EvaluationResult] = []

        for evaluator in self.evaluators:
            try:
                result = await evaluator.evaluate(query, response, context)
                results.append(result)
                logger.info(
                    "evaluation_completed",
                    metric_name=result.metric_name,
                    score=result.score,
                )
            except Exception as e:
                logger.error(
                    "evaluator_failed",
                    evaluator=evaluator.metric_name,
                    error=str(e),
                    error_type=type(e).__name__,
                )

        return results

    async def evaluate_relevance(
        self,
        query: str,
        response: str,
    ) -> EvaluationResult:
        """Convenience method for relevance-only evaluation."""
        return await RelevanceEvaluator().evaluate(query, response)

    async def evaluate_hallucination(
        self,
        query: str,
        response: str,
        context: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        """Convenience method for hallucination-only evaluation."""
        return await HallucinationEvaluator().evaluate(query, response, context)

    async def evaluate_latency(
        self,
        latency_ms: float,
    ) -> EvaluationResult:
        """Convenience method for latency-only evaluation."""
        return await LatencyEvaluator().evaluate("", "", {"latency_ms": latency_ms})


# Singleton instance for easy access
evaluation_pipeline = EvaluationPipeline()
