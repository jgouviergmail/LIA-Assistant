"""
Circuit Breaker pattern implementation for resilience.

Provides fault tolerance for external API calls by preventing cascade failures.
When a service is failing, the circuit breaker "opens" to prevent further calls,
allowing the service time to recover.

States:
- CLOSED: Normal operation, calls pass through
- OPEN: Service failing, calls fail immediately without attempting
- HALF_OPEN: Testing recovery, limited calls allowed

Sprint 16 - Gold-Grade Architecture
Created: 2025-12-18

Usage:
    from src.infrastructure.resilience import get_circuit_breaker

    # Get circuit breaker for a service
    cb = get_circuit_breaker("google_contacts")

    # Use as context manager
    async with cb:
        result = await make_api_call()

    # Or use decorator
    @cb.protect
    async def make_api_call():
        ...
"""

import asyncio
import time
from collections.abc import Callable
from enum import Enum
from functools import wraps
from types import TracebackType
from typing import Any, ParamSpec, TypeVar

import structlog
from prometheus_client import Counter, Gauge

from src.core.config import settings

logger = structlog.get_logger(__name__)

# Type variables for generic decorator
P = ParamSpec("P")
T = TypeVar("T")


# ============================================================================
# PROMETHEUS METRICS
# ============================================================================

circuit_breaker_state = Gauge(
    "circuit_breaker_state",
    "Current circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["service"],
)

circuit_breaker_state_changes_total = Counter(
    "circuit_breaker_state_changes_total",
    "Total circuit breaker state changes",
    ["service", "from_state", "to_state"],
)

circuit_breaker_calls_total = Counter(
    "circuit_breaker_calls_total",
    "Total calls through circuit breaker",
    ["service", "result"],  # result: success, failure, rejected
)

circuit_breaker_open_duration_seconds = Gauge(
    "circuit_breaker_open_duration_seconds",
    "Time in seconds since circuit opened (0 if closed)",
    ["service"],
)


# ============================================================================
# CIRCUIT BREAKER EXCEPTION
# ============================================================================


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open."""

    def __init__(self, service: str, state: "CircuitState", retry_after: float | None = None):
        self.service = service
        self.state = state
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker for '{service}' is {state.value}. "
            f"Service unavailable, please try again later."
            + (f" Retry after {retry_after:.1f}s." if retry_after else "")
        )


# ============================================================================
# CIRCUIT STATE ENUM
# ============================================================================


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing recovery


# ============================================================================
# CIRCUIT BREAKER IMPLEMENTATION
# ============================================================================


class CircuitBreaker:
    """
    Circuit Breaker implementation for fault tolerance.

    Tracks failures and successes for a service, automatically opening
    the circuit when failure threshold is reached, and testing recovery
    after a timeout period.

    Thread-safe via asyncio locks.

    Attributes:
        service: Name of the service being protected
        failure_threshold: Failures before opening circuit
        success_threshold: Successes to close from half-open
        timeout_seconds: Time before half-open retry
        half_open_max_calls: Max calls in half-open state

    Example:
        cb = CircuitBreaker("google_contacts")

        async with cb:
            result = await google_client.search_contacts(query)
    """

    def __init__(
        self,
        service: str,
        failure_threshold: int | None = None,
        success_threshold: int | None = None,
        timeout_seconds: int | None = None,
        half_open_max_calls: int | None = None,
    ):
        """
        Initialize circuit breaker.

        Args:
            service: Name of the service being protected
            failure_threshold: Failures before opening (default from config)
            success_threshold: Successes to close from half-open (default from config)
            timeout_seconds: Time before half-open retry (default from config)
            half_open_max_calls: Max calls in half-open state (default from config)
        """
        self.service = service
        self.failure_threshold = failure_threshold or settings.circuit_breaker_failure_threshold
        self.success_threshold = success_threshold or settings.circuit_breaker_success_threshold
        self.timeout_seconds = timeout_seconds or settings.circuit_breaker_timeout_seconds
        self.half_open_max_calls = (
            half_open_max_calls or settings.circuit_breaker_half_open_max_calls
        )

        # State tracking
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._half_open_calls = 0

        # Thread safety
        self._lock = asyncio.Lock()

        # Initialize metrics
        circuit_breaker_state.labels(service=service).set(0)  # CLOSED
        circuit_breaker_open_duration_seconds.labels(service=service).set(0)

        logger.debug(
            "circuit_breaker_initialized",
            service=service,
            failure_threshold=self.failure_threshold,
            success_threshold=self.success_threshold,
            timeout_seconds=self.timeout_seconds,
        )

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (rejecting calls)."""
        return self._state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)."""
        return self._state == CircuitState.HALF_OPEN

    def _state_to_metric(self, state: CircuitState) -> int:
        """Convert state to metric value."""
        return {CircuitState.CLOSED: 0, CircuitState.OPEN: 1, CircuitState.HALF_OPEN: 2}[state]

    async def _transition_to(self, new_state: CircuitState) -> None:
        """
        Transition to a new state with logging and metrics.

        Args:
            new_state: The state to transition to
        """
        old_state = self._state
        if old_state == new_state:
            return

        self._state = new_state

        # Update metrics
        circuit_breaker_state.labels(service=self.service).set(self._state_to_metric(new_state))
        circuit_breaker_state_changes_total.labels(
            service=self.service,
            from_state=old_state.value,
            to_state=new_state.value,
        ).inc()

        # Track open duration
        if new_state == CircuitState.OPEN:
            circuit_breaker_open_duration_seconds.labels(service=self.service).set(0)
        elif old_state == CircuitState.OPEN and self._last_failure_time:
            duration = time.monotonic() - self._last_failure_time
            circuit_breaker_open_duration_seconds.labels(service=self.service).set(duration)

        logger.info(
            "circuit_breaker_state_change",
            service=self.service,
            from_state=old_state.value,
            to_state=new_state.value,
            failure_count=self._failure_count,
            success_count=self._success_count,
        )

    async def _should_allow_request(self) -> bool:
        """
        Check if a request should be allowed through.

        Returns:
            True if request should proceed, False if rejected
        """
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            # Check if timeout has elapsed
            if self._last_failure_time is not None:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self.timeout_seconds:
                    # Transition to half-open
                    await self._transition_to(CircuitState.HALF_OPEN)
                    self._half_open_calls = 0
                    self._success_count = 0
                    return True
            return False

        if self._state == CircuitState.HALF_OPEN:
            # Allow limited calls in half-open state
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

        return False

    async def record_success(self) -> None:
        """Record a successful call."""
        async with self._lock:
            circuit_breaker_calls_total.labels(service=self.service, result="success").inc()

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    # Close the circuit - service recovered
                    await self._transition_to(CircuitState.CLOSED)
                    self._failure_count = 0
                    self._success_count = 0
                    self._half_open_calls = 0
                    logger.info(
                        "circuit_breaker_recovery",
                        service=self.service,
                        message="Service recovered, circuit closed",
                    )
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    async def record_failure(self, error: Exception | None = None) -> None:
        """
        Record a failed call.

        Args:
            error: The exception that caused the failure (for logging)
        """
        async with self._lock:
            circuit_breaker_calls_total.labels(service=self.service, result="failure").inc()
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Failure in half-open - reopen circuit
                await self._transition_to(CircuitState.OPEN)
                self._success_count = 0
                logger.warning(
                    "circuit_breaker_reopen",
                    service=self.service,
                    error=str(error) if error else None,
                    message="Service still failing, circuit reopened",
                )
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    # Open the circuit
                    await self._transition_to(CircuitState.OPEN)
                    logger.warning(
                        "circuit_breaker_opened",
                        service=self.service,
                        failure_count=self._failure_count,
                        failure_threshold=self.failure_threshold,
                        error=str(error) if error else None,
                        message="Service failing, circuit opened",
                    )

    async def _reject_request(self) -> None:
        """Record a rejected request (circuit open)."""
        circuit_breaker_calls_total.labels(service=self.service, result="rejected").inc()

        # Calculate retry_after hint
        retry_after = None
        if self._last_failure_time is not None:
            elapsed = time.monotonic() - self._last_failure_time
            remaining = self.timeout_seconds - elapsed
            if remaining > 0:
                retry_after = remaining

        raise CircuitBreakerError(
            service=self.service,
            state=self._state,
            retry_after=retry_after,
        )

    async def __aenter__(self) -> "CircuitBreaker":
        """Async context manager entry - check if request is allowed."""
        async with self._lock:
            if not await self._should_allow_request():
                await self._reject_request()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        """Async context manager exit - record success or failure."""
        if exc_type is not None and isinstance(exc_val, Exception):
            await self.record_failure(exc_val)
        else:
            await self.record_success()
        return False  # Don't suppress exceptions

    def protect(self, func: Callable[P, T]) -> Callable[P, T]:
        """
        Decorator to protect a function with this circuit breaker.

        Args:
            func: The async function to protect

        Returns:
            Decorated function with circuit breaker protection

        Example:
            cb = CircuitBreaker("google_contacts")

            @cb.protect
            async def search_contacts(query: str):
                return await client.search(query)
        """

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            async with self._lock:
                if not await self._should_allow_request():
                    await self._reject_request()

            try:
                result = await func(*args, **kwargs)  # type: ignore[misc]
                await self.record_success()
                return result  # type: ignore[no-any-return]
            except Exception as e:
                await self.record_failure(e)
                raise

        return wrapper  # type: ignore[return-value]

    async def reset(self) -> None:
        """
        Manually reset the circuit breaker to closed state.

        Use with caution - mainly for testing or administrative override.
        """
        async with self._lock:
            old_state = self._state
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            self._last_failure_time = None

            circuit_breaker_state.labels(service=self.service).set(0)
            circuit_breaker_open_duration_seconds.labels(service=self.service).set(0)

            logger.info(
                "circuit_breaker_manual_reset",
                service=self.service,
                from_state=old_state.value,
            )

    def get_status(self) -> dict[str, Any]:
        """
        Get current circuit breaker status.

        Returns:
            Dict with state, counters, and configuration
        """
        return {
            "service": self.service,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "half_open_calls": self._half_open_calls,
            "last_failure_time": self._last_failure_time,
            "config": {
                "failure_threshold": self.failure_threshold,
                "success_threshold": self.success_threshold,
                "timeout_seconds": self.timeout_seconds,
                "half_open_max_calls": self.half_open_max_calls,
            },
        }


# ============================================================================
# CIRCUIT BREAKER REGISTRY (Singleton)
# ============================================================================


class CircuitBreakerRegistry:
    """
    Registry for managing circuit breakers across services.

    Singleton pattern ensures consistent state across the application.
    Thread-safe via asyncio locks.

    Usage:
        cb = CircuitBreakerRegistry.get("google_contacts")
        async with cb:
            result = await make_call()
    """

    _instances: dict[str, CircuitBreaker] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def get(
        cls,
        service: str,
        failure_threshold: int | None = None,
        success_threshold: int | None = None,
        timeout_seconds: int | None = None,
    ) -> CircuitBreaker:
        """
        Get or create a circuit breaker for a service.

        Args:
            service: Service identifier (e.g., "google_contacts", "openai")
            failure_threshold: Override default failure threshold
            success_threshold: Override default success threshold
            timeout_seconds: Override default timeout

        Returns:
            CircuitBreaker instance for the service
        """
        async with cls._lock:
            if service not in cls._instances:
                cls._instances[service] = CircuitBreaker(
                    service=service,
                    failure_threshold=failure_threshold,
                    success_threshold=success_threshold,
                    timeout_seconds=timeout_seconds,
                )
                logger.debug(
                    "circuit_breaker_created",
                    service=service,
                )
            return cls._instances[service]

    @classmethod
    def get_sync(cls, service: str) -> CircuitBreaker:
        """
        Synchronous version of get() for non-async contexts.

        Creates circuit breaker if it doesn't exist (no lock).
        Use async get() when possible for thread safety.
        """
        if service not in cls._instances:
            cls._instances[service] = CircuitBreaker(service=service)
        return cls._instances[service]

    @classmethod
    def get_all_status(cls) -> dict[str, dict[str, Any]]:
        """
        Get status of all registered circuit breakers.

        Returns:
            Dict mapping service names to their status
        """
        return {service: cb.get_status() for service, cb in cls._instances.items()}

    @classmethod
    async def reset_all(cls) -> None:
        """Reset all circuit breakers to closed state."""
        async with cls._lock:
            for cb in cls._instances.values():
                await cb.reset()
            logger.info(
                "circuit_breakers_reset_all",
                count=len(cls._instances),
            )

    @classmethod
    def clear(cls) -> None:
        """Clear all circuit breakers (mainly for testing)."""
        cls._instances.clear()


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================


def get_circuit_breaker(service: str) -> CircuitBreaker:
    """
    Convenience function to get a circuit breaker.

    Uses synchronous get for simplicity. For async contexts,
    use CircuitBreakerRegistry.get() directly.

    Args:
        service: Service identifier

    Returns:
        CircuitBreaker instance

    Example:
        cb = get_circuit_breaker("google_contacts")
        async with cb:
            result = await client.search(query)
    """
    # NOTE: Circuit breaker is always enabled
    return CircuitBreakerRegistry.get_sync(service)
