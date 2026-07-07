"""
Perplexity API client.

Provides access to Perplexity AI for advanced web search and question answering.
Uses the Perplexity Online API (Sonar models) for real-time web search.

API Reference:
- https://docs.perplexity.ai/guides/getting-started

Authentication:
- API Key based (Bearer token)
- Get key from: https://www.perplexity.ai/settings/api

Models available:
- sonar: Fast, balanced model for search
- sonar-pro: Advanced reasoning with citations

Built on BaseAPIKeyClient (F4 migration): Redis-backed rate limiting with
local fallback, circuit breaker, retry with backoff, connection pooling.
The public contract is unchanged: methods RAISE on errors (callers catch
broadly) and the search/ask result shapes are preserved.
"""

from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.connectors.clients.base_api_key_client import BaseAPIKeyClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import APIKeyCredentials

logger = structlog.get_logger(__name__)

# Note: Cache TTL centralized in src.core.constants.PERPLEXITY_SEARCH_CACHE_TTL


class PerplexityClient(BaseAPIKeyClient):
    """
    Client for Perplexity API.

    Provides access to:
    - Web search with AI synthesis
    - Question answering with citations
    - Real-time information retrieval

    Example:
        >>> client = PerplexityClient(api_key="pplx-...")
        >>> result = await client.search("What is the latest news about AI?")
        >>> print(result["answer"])
    """

    connector_type = ConnectorType.PERPLEXITY
    api_base_url = "https://api.perplexity.ai"

    # Bearer token auth (base defaults: Authorization / Bearer / header)

    def __init__(
        self,
        api_key: str,
        user_id: UUID | None = None,
        model: str = "sonar",
        rate_limit_per_second: float | None = None,
        user_timezone: str = "UTC",
        user_language: str = "fr",
    ) -> None:
        """
        Initialize Perplexity client.

        Args:
            api_key: Perplexity API key (starts with pplx-)
            user_id: Optional user ID for logging and rate-limit scoping
            model: Model to use (sonar, sonar-pro)
            rate_limit_per_second: Max requests per second (None = use settings)
            user_timezone: User's timezone (default: UTC)
            user_language: User's language (default: fr)
        """
        effective_rate_limit = (
            rate_limit_per_second
            if rate_limit_per_second is not None
            else settings.client_rate_limit_perplexity_per_second
        )
        super().__init__(
            user_id=user_id,
            credentials=APIKeyCredentials(api_key=api_key),
            rate_limit_per_second=effective_rate_limit,
        )
        self.api_key = api_key
        self.model = model
        self.user_timezone = user_timezone
        self.user_language = user_language

    def _get_http_timeout(self) -> float:
        """Perplexity has a dedicated (LLM-latency) timeout setting."""
        return float(settings.http_timeout_perplexity)

    # =========================================================================
    # SEARCH OPERATIONS
    # =========================================================================

    async def search(
        self,
        query: str,
        search_recency_filter: str | None = None,
        return_citations: bool = True,
        return_related_questions: bool = False,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """
        Perform a web search with AI synthesis.

        Uses the Perplexity Sonar model to search the web and synthesize
        an answer with citations.

        Args:
            query: Search query or question
            search_recency_filter: Filter results by recency
                - "day": Last 24 hours
                - "week": Last 7 days
                - "month": Last 30 days
                - "year": Last 365 days
                - None: No filter (default)
            return_citations: Include source citations (default: True)
            return_related_questions: Return related questions (default: False)
            system_prompt: Optional system prompt for context (e.g. datetime)

        Returns:
            Dict with:
                - answer: Synthesized answer text
                - citations: List of source URLs (if return_citations=True)
                - related_questions: Related questions (if requested)

        Example:
            >>> result = await client.search("Latest developments in AI safety")
            >>> print(result["answer"])
            >>> print(result["citations"])
        """
        messages = []
        if system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": system_prompt,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": query,
            }
        )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "return_citations": return_citations,
            "return_related_questions": return_related_questions,
        }

        if search_recency_filter:
            payload["search_recency_filter"] = search_recency_filter

        response = await self._make_request(
            "POST",
            "chat/completions",
            json_data=payload,
        )

        # Extract answer and citations from response
        choices = response.get("choices", [])
        if not choices:
            return {
                "answer": "",
                "citations": [],
                "related_questions": [],
                "query": query,
            }

        message = choices[0].get("message", {})
        answer = message.get("content", "")

        # Citations are in the response root
        citations = response.get("citations", [])
        related_questions = response.get("related_questions", [])

        logger.info(
            "perplexity_search_completed",
            user_id=str(self.user_id) if self.user_id else None,
            query_preview=query[:50] if len(query) > 50 else query,
            answer_length=len(answer),
            citations_count=len(citations),
        )

        return {
            "answer": answer,
            "citations": citations,
            "related_questions": related_questions,
            "query": query,
            "model": self.model,
        }

    async def ask(
        self,
        question: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        """
        Ask a question with optional system context.

        Similar to search but allows custom system prompts for
        specialized use cases.

        Args:
            question: Question to answer
            system_prompt: Optional system prompt for context
            temperature: Response randomness (0.0-1.0, default: 0.2)

        Returns:
            Dict with answer and metadata

        Example:
            >>> result = await client.ask(
            ...     "What are the best practices for Python async?",
            ...     system_prompt="You are an expert Python developer."
            ... )
        """
        messages = []
        if system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": system_prompt,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": question,
            }
        )

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "return_citations": True,
        }

        response = await self._make_request(
            "POST",
            "chat/completions",
            json_data=payload,
        )

        choices = response.get("choices", [])
        if not choices:
            return {
                "answer": "",
                "citations": [],
                "question": question,
            }

        message = choices[0].get("message", {})

        logger.info(
            "perplexity_ask_completed",
            user_id=str(self.user_id) if self.user_id else None,
            question_preview=question[:50] if len(question) > 50 else question,
        )

        return {
            "answer": message.get("content", ""),
            "citations": response.get("citations", []),
            "question": question,
            "model": self.model,
        }

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def set_model(self, model: str) -> None:
        """
        Change the model.

        Args:
            model: Model name (sonar, sonar-pro)
        """
        self.model = model

    @staticmethod
    def get_available_models() -> list[dict[str, str]]:
        """
        Get list of available models.

        Returns:
            List of model info dicts
        """
        return [
            {
                "id": "sonar",
                "name": "Sonar",
                "description": "Fast, balanced model for web search",
            },
            {
                "id": "sonar-pro",
                "name": "Sonar Pro",
                "description": "Advanced reasoning with comprehensive citations",
            },
        ]
