"""
OpenAI LLM Provider.
Wraps LangChain ChatOpenAI with tracing and configuration.
Supports per-instance config overrides via factory pattern.
"""

from typing import TYPE_CHECKING, Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai import ChatOpenAI
from opentelemetry import trace

from src.core.config import settings
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.agents.graphs.base_agent_builder import LLMConfig

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)


class OpenAIProvider:
    """
    OpenAI LLM provider with OpenTelemetry tracing.
    Provides ChatOpenAI instances configured for different use cases (router, response).
    """

    @staticmethod
    def _merge_llm_config(settings_prefix: str, config_override: "LLMConfig | None") -> dict:
        """
        Merge LLM configuration from settings and optional overrides.

        Args:
            settings_prefix: Settings prefix (e.g., "router", "response", "contacts_agent").
            config_override: Optional configuration override. Supports partial overrides.

        Returns:
            dict: Merged configuration with all LLM parameters.
        """
        # Define all LLM parameters to extract
        param_names = [
            "model",
            "temperature",
            "top_p",
            "frequency_penalty",
            "presence_penalty",
            "max_tokens",
        ]

        merged_config: dict[str, Any] = {}
        for param in param_names:
            # Check if override exists for this parameter
            if config_override and param in config_override:
                merged_config[param] = config_override[param]  # type: ignore[literal-required]
            else:
                # Fall back to settings (e.g., settings.router_llm_model)
                settings_attr = f"{settings_prefix}_llm_{param}"
                merged_config[param] = getattr(settings, settings_attr)

        return merged_config

    @staticmethod
    def _create_chatopen_ai(merged_config: dict, streaming: bool, node_name: str) -> ChatOpenAI:
        """
        Create ChatOpenAI instance with metrics callback.

        Args:
            merged_config: Merged LLM configuration (model, temperature, etc.).
            streaming: Whether to enable streaming.
            node_name: Node name for metrics tracking.

        Returns:
            ChatOpenAI: Configured LLM instance with attached metrics callback.
        """
        # Create LLM instance with merged config
        llm = ChatOpenAI(  # type: ignore[call-arg]
            model=merged_config["model"],
            temperature=merged_config["temperature"],
            top_p=merged_config["top_p"],
            frequency_penalty=merged_config["frequency_penalty"],
            presence_penalty=merged_config["presence_penalty"],
            max_tokens=merged_config["max_tokens"],
            openai_api_key=LLMConfigOverrideCache.get_api_key("openai") or "",
            streaming=streaming,
            stream_usage=True,  # Include token usage in responses
        )

        # Phase 2.1.2 - Token Tracking Alignment Fix
        # DO NOT attach static callbacks - causes double counting with dynamic callbacks
        # MetricsCallbackHandler is added DYNAMICALLY via invoke_helpers.py with correct node_name
        #
        # Background:
        #   - Previously: llm.callbacks = [MetricsCallbackHandler(...)] (static)
        #   - Also: invoke_helpers.py adds MetricsCallbackHandler to config["callbacks"] (dynamic)
        #   - LangChain merges both: llm.callbacks + config["callbacks"]
        #   - Result: DOUBLE COUNTING (every LLM call counted twice in Prometheus)
        #
        # Solution:
        #   - LLM instance: llm.callbacks = [] (empty, no static callbacks)
        #   - Graph-level: invoke_helpers.py adds MetricsCallbackHandler dynamically
        #   - This ensures ONE MetricsCallbackHandler per invocation
        #
        # References:
        #   - invoke_helpers.py:213 (dynamic MetricsCallbackHandler injection)
        #   - CORRECTIONS_LANGFUSE_DUPLICATION.md (root cause analysis)
        #   - Investigation Report 2025-01-10 (4.4x discrepancy)
        callbacks: list[BaseCallbackHandler] = []
        llm.callbacks = callbacks

        return llm

    @staticmethod
    def get_router_llm(config_override: "LLMConfig | None" = None) -> ChatOpenAI:
        """
        Get LLM configured for router node.
        Low temperature for deterministic routing decisions.

        Args:
            config_override: Optional configuration override. Supports partial overrides
                (e.g., only override temperature, keep other settings defaults).
                If None, uses global settings from src.core.config.

        Returns:
            ChatOpenAI: Configured LLM instance for router.

        Example:
            >>> # Default behavior (uses settings)
            >>> llm = OpenAIProvider.get_router_llm()

            >>> # Override specific parameter
            >>> llm = OpenAIProvider.get_router_llm(config_override={"temperature": 0.2})
        """
        merged_config = OpenAIProvider._merge_llm_config("router", config_override)

        logger.debug(
            "creating_router_llm",
            **merged_config,
            has_override=config_override is not None,
        )

        return OpenAIProvider._create_chatopen_ai(
            merged_config=merged_config,
            streaming=False,  # Router doesn't need streaming
            node_name="router",
        )

    @staticmethod
    def get_response_llm(config_override: "LLMConfig | None" = None) -> ChatOpenAI:
        """
        Get LLM configured for response node.
        Higher temperature for creative responses.

        Args:
            config_override: Optional configuration override. Supports partial overrides
                (e.g., only override temperature, keep other settings defaults).
                If None, uses global settings from src.core.config.

        Returns:
            ChatOpenAI: Configured LLM instance for response.

        Example:
            >>> # Default behavior (uses settings)
            >>> llm = OpenAIProvider.get_response_llm()

            >>> # Override specific parameter
            >>> llm = OpenAIProvider.get_response_llm(config_override={"temperature": 1.2})
        """
        merged_config = OpenAIProvider._merge_llm_config("response", config_override)

        logger.debug(
            "creating_response_llm",
            **merged_config,
            has_override=config_override is not None,
        )

        return OpenAIProvider._create_chatopen_ai(
            merged_config=merged_config,
            streaming=True,  # Response node streams tokens
            node_name="response",
        )

    @staticmethod
    def get_contacts_agent_llm(config_override: "LLMConfig | None" = None) -> ChatOpenAI:
        """
        Get LLM configured for contacts agent node (ReAct pattern).
        Balanced temperature for precise tool usage with some creativity.

        Args:
            config_override: Optional configuration override. Supports partial overrides
                (e.g., only override temperature, keep other settings defaults).
                If None, uses global settings from src.core.config.

        Returns:
            ChatOpenAI: Configured LLM instance for contacts agent.

        Example:
            >>> # Default behavior (uses settings)
            >>> llm = OpenAIProvider.get_contacts_agent_llm()

            >>> # Override specific parameter
            >>> llm = OpenAIProvider.get_contacts_agent_llm(config_override={"temperature": 0.7})

            >>> # Override multiple parameters
            >>> llm = OpenAIProvider.get_contacts_agent_llm(config_override={
            ...     "model": "gpt-4.1-mini",
            ...     "temperature": 0.8,
            ...     "max_tokens": 5000
            ... })
        """
        merged_config = OpenAIProvider._merge_llm_config("contacts_agent", config_override)

        logger.debug(
            "creating_contacts_agent_llm",
            **merged_config,
            has_override=config_override is not None,
        )

        return OpenAIProvider._create_chatopen_ai(
            merged_config=merged_config,
            streaming=False,  # ReAct agents don't stream during tool calls
            node_name="contacts_agent",
        )

    @staticmethod
    def get_planner_llm(config_override: "LLMConfig | None" = None) -> ChatOpenAI:
        """
        Get LLM configured for planner node (Phase 5).
        Balanced temperature for plan generation with JSON output.

        Args:
            config_override: Optional configuration override. Supports partial overrides
                (e.g., only override temperature, keep other settings defaults).
                If None, uses global settings from src.core.config.

        Returns:
            ChatOpenAI: Configured LLM instance for planner.

        Example:
            >>> # Default behavior (uses settings)
            >>> llm = OpenAIProvider.get_planner_llm()

            >>> # Override specific parameter
            >>> llm = OpenAIProvider.get_planner_llm(config_override={"temperature": 0.3})
        """
        merged_config = OpenAIProvider._merge_llm_config("planner", config_override)

        logger.debug(
            "creating_planner_llm",
            **merged_config,
            has_override=config_override is not None,
        )

        return OpenAIProvider._create_chatopen_ai(
            merged_config=merged_config,
            streaming=False,  # Planner needs full response (JSON plan)
            node_name="planner",
        )

    @staticmethod
    def count_tokens(text: str, model: str | None = None) -> int:
        """
        Count tokens in text using tiktoken encoding for the model.

        Args:
            text: Text to count tokens for.
            model: Model name to get encoding for (default: from settings.token_count_default_model).

        Returns:
            int: Number of tokens.
        """
        import tiktoken

        if model is None:
            model = settings.token_count_default_model

        try:
            # Use configured token encoding
            encoding = tiktoken.get_encoding(settings.token_encoding_name)
            return len(encoding.encode(text))
        except Exception as e:
            logger.warning(
                "token_counting_fallback",
                error=str(e),
                model=model,
            )
            # Fallback: rough estimation (4 chars per token)
            return len(text) // 4
