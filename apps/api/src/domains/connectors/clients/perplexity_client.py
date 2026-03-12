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
"""

import asyncio
from typing import Any
from uuid import UUID

import httpx
import structlog

from src.core.config import settings
from src.core.constants import HTTP_TIMEOUT_PERPLEXITY
from src.core.exceptions import MaxRetriesExceededError

logger = structlog.get_logger(__name__)

# Note: Cache TTL centralized in src.core.constants.PERPLEXITY_SEARCH_CACHE_TTL


class PerplexityClient:
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

    api_base_url = "https://api.perplexity.ai"

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
            user_id: Optional user ID for logging
            model: Model to use (sonar, sonar-pro)
            rate_limit_per_second: Max requests per second (None = use settings)
            user_timezone: User's timezone (default: UTC)
            user_language: User's language (default: fr)
        """
        self.api_key = api_key
        self.user_id = user_id
        self.model = model
        self.user_timezone = user_timezone
        self.user_language = user_language
        # Use settings if not explicitly provided
        effective_rate_limit = (
            rate_limit_per_second
            if rate_limit_per_second is not None
            else settings.client_rate_limit_perplexity_per_second
        )
        self._rate_limit_interval = 1.0 / effective_rate_limit
        self._last_request_time = 0.0
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create reusable HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=HTTP_TIMEOUT_PERPLEXITY,
                limits=httpx.Limits(
                    max_keepalive_connections=5,
                    max_connections=10,
                ),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._http_client

    async def close(self) -> None:
        """Cleanup HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def _rate_limit(self) -> None:
        """Apply rate limiting."""
        import time

        now = time.monotonic()
        elapsed = now - self._last_request_time

        if elapsed < self._rate_limit_interval:
            wait_time = self._rate_limit_interval - elapsed
            await asyncio.sleep(wait_time)

        self._last_request_time = time.monotonic()

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
        await self._rate_limit()

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
            "/chat/completions",
            json=payload,
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
        await self._rate_limit()

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
            "/chat/completions",
            json=payload,
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

    async def _make_request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make request to Perplexity API.

        Args:
            method: HTTP method
            path: API path
            json: Request body

        Returns:
            JSON response
        """
        client = await self._get_client()
        url = f"{self.api_base_url}{path}"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await client.request(
                    method,
                    url,
                    json=json,
                )

                if response.status_code == 429:
                    wait_time = 5 * (attempt + 1)
                    logger.warning(
                        "perplexity_rate_limited",
                        user_id=str(self.user_id) if self.user_id else None,
                        attempt=attempt + 1,
                        wait_seconds=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue

                response.raise_for_status()
                result: dict[str, Any] = response.json()
                return result

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    logger.error(
                        "perplexity_auth_error",
                        user_id=str(self.user_id) if self.user_id else None,
                        message="Invalid API key",
                    )
                    raise ValueError("Invalid Perplexity API key") from e
                raise

            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(
                        "perplexity_request_failed",
                        user_id=str(self.user_id) if self.user_id else None,
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    raise

                wait_time = 2**attempt
                logger.warning(
                    "perplexity_request_retry",
                    user_id=str(self.user_id) if self.user_id else None,
                    attempt=attempt + 1,
                    wait_seconds=wait_time,
                )
                await asyncio.sleep(wait_time)

        # Should never reach here but satisfy type checker
        raise MaxRetriesExceededError(
            operation="perplexity_request",
            max_retries=3,
        )

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
