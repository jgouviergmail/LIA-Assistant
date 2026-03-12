"""
Callback factory for LLM observability with Langfuse v3 (2025).

This module provides a production-grade, generic factory pattern for creating LangChain-compatible
callbacks that integrate with Langfuse SDK v3.9+ for comprehensive LLM tracing and monitoring.

Architecture (2025 Best Practices):
    - Singleton CallbackHandler pattern (SDK v3.9+ recommendation)
    - Metadata-driven context propagation (session_id, user_id, tags via config["metadata"])
    - Environment-based configuration (12-factor app principles)
    - Graceful degradation if Langfuse unavailable
    - Thread-safe for concurrent requests
    - Production-ready error handling and logging

Key Design Principles:
    - Generic: Works with any LangChain/LangGraph component
    - Maintainable: Single source of truth for Langfuse config
    - Evolvable: Easy to add new metadata/tags for future agents
    - Secure: No hardcoded credentials, environment-based config
    - Observable: Structured logging for debugging

Usage:
    >>> # Initialize once at startup (in main.py lifespan)
    >>> from src.infrastructure.llm.callback_factory import init_callback_factory
    >>> factory = init_callback_factory(settings)

    >>> # Create callbacks for each LLM call (in service layer)
    >>> from src.infrastructure.llm.callback_factory import get_callback_factory
    >>> factory = get_callback_factory()
    >>> callbacks = factory.create_callbacks()

    >>> # Use with LangChain via instrumentation layer
    >>> from src.infrastructure.llm.instrumentation import create_instrumented_config
    >>> config = create_instrumented_config(
    ...     llm_type="router",
    ...     session_id="conv_123",
    ...     user_id="user_456",
    ...     tags=["production"],
    ...     metadata={"intent": "contacts_search"}
    ... )
    >>> response = llm.invoke(messages, config=config)

Integration Points:
    - main.py: lifespan startup/shutdown
    - instrumentation.py: automatic config enrichment
    - factory.py: LLM creation with callbacks
    - All agent nodes: automatic tracing via config

References:
    - Langfuse SDK v3: https://langfuse.com/docs/sdk/python
    - LangChain Integration: https://langfuse.com/docs/integrations/langchain/tracing
    - Self-Hosted Guide: https://langfuse.com/self-hosting
    - Best Practices: https://langfuse.com/guides/cookbook/integration_langchain

Version: 2.0.0 (Cleaned & Optimized)
Date: 2025-11-05
"""

import os
from typing import Any

import structlog

from src.core.config import Settings

logger = structlog.get_logger(__name__)


class CallbackFactory:
    """
    Production-grade factory for Langfuse callbacks with SDK v3.9+ best practices.

    This factory implements the singleton CallbackHandler pattern recommended for Langfuse v3,
    providing thread-safe callback creation for LangChain/LangGraph instrumentation.

    Architecture Rationale:
        - **Singleton Handler**: One CallbackHandler persists for app lifetime
        - **Metadata Propagation**: Context (session_id, user_id, tags) passed via config["metadata"]
        - **Environment Config**: Langfuse SDK reads from os.environ (12-factor pattern)
        - **Graceful Degradation**: Returns empty list if disabled, no exceptions

    Thread Safety:
        The singleton handler is thread-safe because:
        1. CallbackHandler is initialized once at startup (single-threaded)
        2. Each invoke() call passes unique metadata via config
        3. Langfuse SDK internally handles concurrent traces

    Attributes:
        settings (Settings): Application settings with Langfuse configuration
        _enabled (bool): Whether Langfuse tracing is enabled
        _handler (Optional[CallbackHandler]): Singleton handler instance

    Example:
        >>> factory = CallbackFactory(settings)
        >>> if factory.is_enabled():
        ...     callbacks = factory.create_callbacks()
        ...     config = {"callbacks": callbacks, "metadata": {
        ...         "langfuse_session_id": "session_123",
        ...         "langfuse_user_id": "user_456",
        ...         "langfuse_tags": ["router", "production"]
        ...     }}
        ...     response = llm.invoke(messages, config=config)
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize callback factory with application settings.

        Environment Configuration:
            Exports Pydantic settings to os.environ for Langfuse SDK consumption.
            Required variables:
                - LANGFUSE_PUBLIC_KEY: Project public key
                - LANGFUSE_SECRET_KEY: Project secret key
                - LANGFUSE_HOST: Self-hosted URL (e.g., http://langfuse-web:3000)

            Optional variables:
                - LANGFUSE_RELEASE: Release identifier (e.g., git commit SHA)
                - LANGFUSE_SAMPLE_RATE: Sampling rate 0.0-1.0 (default 1.0)
                - LANGFUSE_FLUSH_INTERVAL: Batch flush interval in seconds
                - LANGFUSE_DEBUG: Enable SDK debug logging (true/false)

        Singleton Pattern:
            Creates ONE CallbackHandler at initialization that persists for the
            entire application lifetime. This ensures proper trace flushing and
            efficient resource usage.

        Args:
            settings: Application settings containing Langfuse configuration

        Raises:
            No exceptions raised. If initialization fails, sets _enabled=False
            and logs the error. Application continues without tracing.
        """
        self.settings = settings
        self._enabled = settings.langfuse_enabled
        self._handler: Any | None = None  # Type: CallbackHandler (imported lazily)

        if not self._enabled:
            logger.info(
                "langfuse_disabled",
                reason="LANGFUSE_ENABLED=false in settings",
            )
            return

        # Validate required credentials
        if not self.settings.langfuse_public_key or not self.settings.langfuse_secret_key:
            logger.warning(
                "langfuse_credentials_missing",
                message="Langfuse API keys not configured, tracing disabled",
                hint="Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in .env",
                public_key_set=bool(self.settings.langfuse_public_key),
                secret_key_set=bool(self.settings.langfuse_secret_key),
            )
            self._enabled = False
            return

        # Export configuration to environment (Langfuse SDK v3.9+ reads from os.environ)
        self._export_config_to_environment()

        # Initialize singleton CallbackHandler
        self._initialize_handler()

    def _export_config_to_environment(self) -> None:
        """
        Export Pydantic settings to os.environ for Langfuse SDK.

        Langfuse SDK v3.9+ reads configuration directly from environment variables.
        We export our Pydantic settings to ensure consistency across the application.

        Security Note:
            Environment variables are process-isolated. Setting them here does not
            leak credentials to other processes or containers.

        12-Factor App Compliance:
            This pattern follows 12-factor app principles by using environment
            for configuration, making deployment across environments seamless.
        """
        # Required configuration
        os.environ["LANGFUSE_PUBLIC_KEY"] = self.settings.langfuse_public_key
        os.environ["LANGFUSE_SECRET_KEY"] = self.settings.langfuse_secret_key
        os.environ["LANGFUSE_HOST"] = self.settings.langfuse_host

        # Optional configuration
        if self.settings.langfuse_release:
            os.environ["LANGFUSE_RELEASE"] = self.settings.langfuse_release

        if self.settings.langfuse_sample_rate is not None:
            os.environ["LANGFUSE_SAMPLE_RATE"] = str(self.settings.langfuse_sample_rate)

        if self.settings.langfuse_flush_interval is not None:
            os.environ["LANGFUSE_FLUSH_INTERVAL"] = str(self.settings.langfuse_flush_interval)

        # Debug configuration (explicit set, don't use setdefault)
        if hasattr(self.settings, "langfuse_debug"):
            os.environ["LANGFUSE_DEBUG"] = "true" if self.settings.langfuse_debug else "false"

        logger.info(
            "langfuse_config_exported",
            host=self.settings.langfuse_host,
            release=self.settings.langfuse_release,
            sample_rate=self.settings.langfuse_sample_rate,
            flush_interval=self.settings.langfuse_flush_interval,
            debug=os.environ.get("LANGFUSE_DEBUG"),
        )

    def _initialize_handler(self) -> None:
        """
        Initialize singleton CallbackHandler for application lifetime.

        Lazy Import:
            Imports CallbackHandler only when needed to avoid import-time
            dependencies and circular import issues.

        Error Handling:
            If initialization fails, logs error and disables tracing.
            Application continues without observability (graceful degradation).

        SDK v3.9+ Pattern:
            CallbackHandler() auto-initializes from environment variables.
            No parameters needed - all config from os.environ.
        """
        try:
            # Lazy import to avoid circular dependencies
            from langfuse.langchain import CallbackHandler  # type: ignore[import-not-found]

            # Create singleton handler (reads config from os.environ)
            self._handler = CallbackHandler()

            logger.info(
                "langfuse_handler_initialized",
                handler_id=id(self._handler),
                handler_type=type(self._handler).__name__,
                note="Singleton handler created for application lifetime",
            )

        except ImportError as e:
            logger.error(
                "langfuse_import_failed",
                error=str(e),
                hint="Install langfuse: pip install langfuse",
            )
            self._enabled = False

        except Exception as e:
            logger.error(
                "langfuse_handler_init_failed",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            self._enabled = False

    def create_callbacks(self) -> list[Any]:
        """
        Create callback list for LLM tracing (returns singleton handler).

        SDK v3.9+ Pattern (2025 Best Practice):
            - Returns the SAME handler instance for all requests
            - Context (session_id, user_id, tags) passed via config["metadata"]
            - Handler extracts metadata using keys: langfuse_session_id, langfuse_user_id, langfuse_tags
            - NO parameters accepted - pure singleton pattern

        Thread Safety:
            Safe for concurrent requests because:
            1. Handler instance is immutable after creation
            2. Each invoke() call has unique metadata in config
            3. SDK handles concurrent trace creation internally

        Returns:
            List containing singleton CallbackHandler if enabled, empty list otherwise.

        Usage:
            >>> # ❌ WRONG - Do NOT use directly
            >>> callbacks = factory.create_callbacks()

            >>> # ✅ CORRECT - Use instrumentation helper
            >>> from src.infrastructure.llm.instrumentation import create_instrumented_config
            >>> config = create_instrumented_config(
            ...     llm_type="router",
            ...     session_id="session_123",
            ...     user_id="user_456",
            ...     tags=["production"]
            ... )
            >>> response = llm.invoke(messages, config=config)

        Note:
            This method accepts ZERO parameters per SDK v3.9+ best practices.
            Use instrumentation.create_instrumented_config() instead,
            which automatically adds callbacks AND metadata keys.
        """
        if not self._enabled:
            return []

        if not self._handler:
            logger.error(
                "langfuse_handler_missing",
                note="Handler should have been initialized at startup",
            )
            return []

        return [self._handler]

    def flush(self) -> None:
        """
        Flush all pending traces to Langfuse server.

        Best Practice:
            Call at application shutdown to ensure all traces are sent
            before termination.

        SDK v3.9+ Pattern:
            Handler has a 'client' attribute with flush() method.

        Example:
            >>> # In main.py lifespan shutdown
            >>> factory = get_callback_factory()
            >>> if factory:
            ...     factory.flush()
        """
        if not self._enabled or not self._handler:
            return

        try:
            # SDK v3.9+: handler.client.flush()
            if hasattr(self._handler, "client") and hasattr(self._handler.client, "flush"):
                self._handler.client.flush()
                logger.info(
                    "langfuse_traces_flushed",
                    handler_id=id(self._handler),
                )
            else:
                logger.warning(
                    "langfuse_flush_unavailable",
                    note="Handler doesn't have client.flush() method",
                    has_client=hasattr(self._handler, "client"),
                )

        except Exception as e:
            logger.error(
                "langfuse_flush_error",
                error=str(e),
                error_type=type(e).__name__,
            )

    def shutdown(self) -> None:
        """
        Shutdown Langfuse tracing and release resources.

        Best Practice:
            Call after flush() at application shutdown for complete cleanup.

        Cleanup:
            1. Flushes pending traces
            2. Releases handler reference
            3. Disables tracing

        Example:
            >>> # In main.py lifespan shutdown
            >>> factory = get_callback_factory()
            >>> if factory:
            ...     factory.flush()
            ...     factory.shutdown()
        """
        if not self._enabled or not self._handler:
            return

        try:
            # Flush before shutdown
            self.flush()

            # Release resources
            handler_id = id(self._handler)
            self._handler = None
            self._enabled = False

            logger.info(
                "langfuse_factory_shutdown",
                handler_id=handler_id,
                note="Singleton handler released, tracing disabled",
            )

        except Exception as e:
            logger.error(
                "langfuse_shutdown_error",
                error=str(e),
                error_type=type(e).__name__,
            )

    def is_enabled(self) -> bool:
        """
        Check if Langfuse tracing is enabled.

        Returns:
            True if tracing is enabled and handler is initialized.

        Example:
            >>> if factory.is_enabled():
            ...     callbacks = factory.create_callbacks()
        """
        return self._enabled and self._handler is not None


# ============================================================================
# Global Singleton Pattern (Application-Wide Access)
# ============================================================================

_callback_factory: CallbackFactory | None = None


def init_callback_factory(settings: Settings) -> CallbackFactory:
    """
    Initialize the global callback factory singleton (called at startup).

    Best Practice:
        Call this once in main.py lifespan startup to initialize the
        Langfuse client and make it available application-wide.

    Args:
        settings: Application settings with Langfuse configuration

    Returns:
        Initialized CallbackFactory instance

    Example:
        >>> # In main.py lifespan startup
        >>> from src.infrastructure.llm.callback_factory import init_callback_factory
        >>> from src.core.config import get_settings
        >>>
        >>> settings = get_settings()
        >>> factory = init_callback_factory(settings)
        >>> logger.info("langfuse_ready", enabled=factory.is_enabled())
    """
    global _callback_factory
    _callback_factory = CallbackFactory(settings)

    logger.info(
        "callback_factory_initialized",
        enabled=_callback_factory.is_enabled(),
        factory_id=id(_callback_factory),
    )

    return _callback_factory


def get_callback_factory() -> CallbackFactory | None:
    """
    Get the global callback factory singleton instance.

    Best Practice:
        Use this function to access the factory from anywhere in the application.
        Factory must be initialized first via init_callback_factory().

    Returns:
        CallbackFactory instance if initialized, None otherwise

    Example:
        >>> from src.infrastructure.llm.callback_factory import get_callback_factory
        >>> from src.infrastructure.llm.instrumentation import create_instrumented_config
        >>>
        >>> factory = get_callback_factory()
        >>> if factory and factory.is_enabled():
        ...     config = create_instrumented_config(
        ...         llm_type="router",
        ...         session_id="conv_123"
        ...     )
        ...     response = llm.invoke(messages, config=config)
    """
    return _callback_factory


def flush_callbacks() -> None:
    """
    Flush all pending Langfuse traces (call at shutdown).

    Best Practice:
        Call in main.py lifespan shutdown to ensure all traces
        are sent before application termination.

    Example:
        >>> # In main.py lifespan shutdown
        >>> from src.infrastructure.llm.callback_factory import flush_callbacks
        >>> flush_callbacks()
        >>> logger.info("langfuse_traces_flushed")
    """
    global _callback_factory
    if _callback_factory:
        _callback_factory.flush()


def shutdown_callback_factory() -> None:
    """
    Shutdown Langfuse client and clean up resources (call at shutdown).

    Best Practice:
        Call after flush_callbacks() in main.py shutdown for complete cleanup.

    Cleanup Steps:
        1. Flushes all pending traces
        2. Releases handler instance
        3. Nullifies global reference
        4. Logs shutdown confirmation

    Example:
        >>> # In main.py lifespan shutdown
        >>> from src.infrastructure.llm.callback_factory import (
        ...     flush_callbacks,
        ...     shutdown_callback_factory
        ... )
        >>> flush_callbacks()
        >>> shutdown_callback_factory()
        >>> logger.info("langfuse_shutdown_complete")
    """
    global _callback_factory
    if _callback_factory:
        _callback_factory.shutdown()
        _callback_factory = None
