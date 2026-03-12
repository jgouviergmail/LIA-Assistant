"""
Tests for Circuit Breaker pattern implementation.

Sprint 16 - Gold-Grade Architecture
Created: 2025-12-18
"""

import asyncio
from unittest.mock import patch

import pytest

from src.infrastructure.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitBreakerRegistry,
    CircuitState,
    get_circuit_breaker,
)


class TestCircuitBreakerStates:
    """Tests for circuit breaker state transitions."""

    @pytest.fixture
    def circuit_breaker(self):
        """Create a fresh circuit breaker for each test."""
        return CircuitBreaker(
            service="test_service",
            failure_threshold=3,
            success_threshold=2,
            timeout_seconds=1,  # Short timeout for tests
            half_open_max_calls=2,
        )

    @pytest.mark.asyncio
    async def test_initial_state_is_closed(self, circuit_breaker):
        """Circuit breaker should start in closed state."""
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.is_closed
        assert not circuit_breaker.is_open
        assert not circuit_breaker.is_half_open

    @pytest.mark.asyncio
    async def test_stays_closed_on_success(self, circuit_breaker):
        """Circuit should stay closed on successful calls."""
        await circuit_breaker.record_success()
        await circuit_breaker.record_success()
        await circuit_breaker.record_success()

        assert circuit_breaker.is_closed

    @pytest.mark.asyncio
    async def test_opens_after_failure_threshold(self, circuit_breaker):
        """Circuit should open after reaching failure threshold."""
        # Record failures up to threshold
        for _ in range(circuit_breaker.failure_threshold):
            await circuit_breaker.record_failure(Exception("test error"))

        assert circuit_breaker.is_open

    @pytest.mark.asyncio
    async def test_resets_failure_count_on_success(self, circuit_breaker):
        """Failure count should reset on success."""
        # Record some failures (less than threshold)
        await circuit_breaker.record_failure(Exception("error 1"))
        await circuit_breaker.record_failure(Exception("error 2"))

        # Success should reset counter
        await circuit_breaker.record_success()

        # Now need full threshold again to open
        await circuit_breaker.record_failure(Exception("error 3"))
        await circuit_breaker.record_failure(Exception("error 4"))

        assert circuit_breaker.is_closed  # Not enough failures after reset

    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_timeout(self, circuit_breaker):
        """Circuit should transition to half-open after timeout."""
        # Open the circuit
        for _ in range(circuit_breaker.failure_threshold):
            await circuit_breaker.record_failure(Exception("test"))

        assert circuit_breaker.is_open

        # Wait for timeout
        await asyncio.sleep(circuit_breaker.timeout_seconds + 0.1)

        # Next request check should transition to half-open
        async with circuit_breaker._lock:
            allowed = await circuit_breaker._should_allow_request()

        assert allowed
        assert circuit_breaker.is_half_open

    @pytest.mark.asyncio
    async def test_closes_from_half_open_on_success(self, circuit_breaker):
        """Circuit should close from half-open after success threshold."""
        # Open the circuit
        for _ in range(circuit_breaker.failure_threshold):
            await circuit_breaker.record_failure(Exception("test"))

        # Wait for timeout and trigger half-open
        await asyncio.sleep(circuit_breaker.timeout_seconds + 0.1)
        async with circuit_breaker._lock:
            await circuit_breaker._should_allow_request()

        assert circuit_breaker.is_half_open

        # Record successes to close
        for _ in range(circuit_breaker.success_threshold):
            await circuit_breaker.record_success()

        assert circuit_breaker.is_closed

    @pytest.mark.asyncio
    async def test_reopens_from_half_open_on_failure(self, circuit_breaker):
        """Circuit should reopen from half-open on failure."""
        # Open the circuit
        for _ in range(circuit_breaker.failure_threshold):
            await circuit_breaker.record_failure(Exception("test"))

        # Wait for timeout and trigger half-open
        await asyncio.sleep(circuit_breaker.timeout_seconds + 0.1)
        async with circuit_breaker._lock:
            await circuit_breaker._should_allow_request()

        assert circuit_breaker.is_half_open

        # Failure in half-open should reopen
        await circuit_breaker.record_failure(Exception("failed again"))

        assert circuit_breaker.is_open


class TestCircuitBreakerRequestHandling:
    """Tests for request allow/reject behavior."""

    @pytest.fixture
    def circuit_breaker(self):
        return CircuitBreaker(
            service="test_service",
            failure_threshold=2,
            success_threshold=1,
            timeout_seconds=1,
            half_open_max_calls=2,
        )

    @pytest.mark.asyncio
    async def test_allows_request_when_closed(self, circuit_breaker):
        """Requests should be allowed when circuit is closed."""
        async with circuit_breaker._lock:
            allowed = await circuit_breaker._should_allow_request()
        assert allowed

    @pytest.mark.asyncio
    async def test_rejects_request_when_open(self, circuit_breaker):
        """Requests should be rejected when circuit is open."""
        # Open the circuit
        for _ in range(circuit_breaker.failure_threshold):
            await circuit_breaker.record_failure(Exception("test"))

        async with circuit_breaker._lock:
            allowed = await circuit_breaker._should_allow_request()

        assert not allowed

    @pytest.mark.asyncio
    async def test_limits_requests_in_half_open(self, circuit_breaker):
        """Only limited requests allowed in half-open state."""
        # Open the circuit
        for _ in range(circuit_breaker.failure_threshold):
            await circuit_breaker.record_failure(Exception("test"))

        # Wait for timeout
        await asyncio.sleep(circuit_breaker.timeout_seconds + 0.1)

        # First request triggers transition to half-open (does NOT count against limit)
        async with circuit_breaker._lock:
            allowed = await circuit_breaker._should_allow_request()
        assert allowed
        assert circuit_breaker.is_half_open
        assert circuit_breaker._half_open_calls == 0  # Transition request doesn't count

        # Subsequent requests up to half_open_max_calls should be allowed
        for i in range(circuit_breaker.half_open_max_calls):
            async with circuit_breaker._lock:
                allowed = await circuit_breaker._should_allow_request()
            assert allowed, f"Request {i+1} in half-open should be allowed"

        # Next request should be rejected (exceeded half_open_max_calls)
        async with circuit_breaker._lock:
            allowed = await circuit_breaker._should_allow_request()
        assert not allowed

    @pytest.mark.asyncio
    async def test_reject_raises_error(self, circuit_breaker):
        """_reject_request should raise CircuitBreakerError."""
        # Open the circuit
        for _ in range(circuit_breaker.failure_threshold):
            await circuit_breaker.record_failure(Exception("test"))

        with pytest.raises(CircuitBreakerError) as exc_info:
            await circuit_breaker._reject_request()

        assert exc_info.value.service == "test_service"
        assert exc_info.value.state == CircuitState.OPEN


class TestCircuitBreakerContextManager:
    """Tests for async context manager usage."""

    @pytest.fixture
    def circuit_breaker(self):
        return CircuitBreaker(
            service="test_service",
            failure_threshold=2,
            success_threshold=1,
            timeout_seconds=1,
        )

    @pytest.mark.asyncio
    async def test_context_manager_records_success(self, circuit_breaker):
        """Context manager should record success on clean exit."""
        async with circuit_breaker:
            pass  # No exception

        # Should still be closed with reset failure count
        assert circuit_breaker.is_closed
        assert circuit_breaker._failure_count == 0

    @pytest.mark.asyncio
    async def test_context_manager_records_failure(self, circuit_breaker):
        """Context manager should record failure on exception."""
        with pytest.raises(ValueError):
            async with circuit_breaker:
                raise ValueError("test error")

        assert circuit_breaker._failure_count == 1

    @pytest.mark.asyncio
    async def test_context_manager_rejects_when_open(self, circuit_breaker):
        """Context manager should reject when circuit is open."""
        # Open the circuit
        for _ in range(circuit_breaker.failure_threshold):
            await circuit_breaker.record_failure(Exception("test"))

        with pytest.raises(CircuitBreakerError):
            async with circuit_breaker:
                pass


class TestCircuitBreakerDecorator:
    """Tests for @protect decorator."""

    @pytest.fixture
    def circuit_breaker(self):
        return CircuitBreaker(
            service="test_service",
            failure_threshold=2,
            success_threshold=1,
            timeout_seconds=1,
        )

    @pytest.mark.asyncio
    async def test_decorator_allows_success(self, circuit_breaker):
        """Decorated function should execute normally on success."""

        @circuit_breaker.protect
        async def my_func():
            return "success"

        result = await my_func()
        assert result == "success"
        assert circuit_breaker.is_closed

    @pytest.mark.asyncio
    async def test_decorator_records_failure(self, circuit_breaker):
        """Decorated function should record failure on exception."""

        @circuit_breaker.protect
        async def failing_func():
            raise RuntimeError("test error")

        with pytest.raises(RuntimeError):
            await failing_func()

        assert circuit_breaker._failure_count == 1

    @pytest.mark.asyncio
    async def test_decorator_rejects_when_open(self, circuit_breaker):
        """Decorated function should fail fast when circuit is open."""

        @circuit_breaker.protect
        async def my_func():
            return "success"

        # Open the circuit
        for _ in range(circuit_breaker.failure_threshold):
            await circuit_breaker.record_failure(Exception("test"))

        with pytest.raises(CircuitBreakerError):
            await my_func()


class TestCircuitBreakerRegistry:
    """Tests for the circuit breaker registry."""

    def setup_method(self):
        """Clear registry before each test."""
        CircuitBreakerRegistry.clear()

    @pytest.mark.asyncio
    async def test_get_creates_new_instance(self):
        """Registry should create new circuit breaker for new service."""
        cb = await CircuitBreakerRegistry.get("service_a")
        assert cb.service == "service_a"

    @pytest.mark.asyncio
    async def test_get_returns_same_instance(self):
        """Registry should return same instance for same service."""
        cb1 = await CircuitBreakerRegistry.get("service_a")
        cb2 = await CircuitBreakerRegistry.get("service_a")
        assert cb1 is cb2

    def test_get_sync_creates_instance(self):
        """Sync get should create circuit breaker."""
        cb = CircuitBreakerRegistry.get_sync("service_sync")
        assert cb.service == "service_sync"

    @pytest.mark.asyncio
    async def test_get_all_status(self):
        """Should return status of all registered breakers."""
        await CircuitBreakerRegistry.get("service_1")
        await CircuitBreakerRegistry.get("service_2")

        status = CircuitBreakerRegistry.get_all_status()

        assert "service_1" in status
        assert "service_2" in status
        assert status["service_1"]["state"] == "closed"

    @pytest.mark.asyncio
    async def test_reset_all(self):
        """Should reset all circuit breakers."""
        cb1 = await CircuitBreakerRegistry.get("service_1", failure_threshold=1)
        cb2 = await CircuitBreakerRegistry.get("service_2", failure_threshold=1)

        # Open both circuits
        await cb1.record_failure(Exception("test"))
        await cb2.record_failure(Exception("test"))

        assert cb1.is_open
        assert cb2.is_open

        # Reset all
        await CircuitBreakerRegistry.reset_all()

        assert cb1.is_closed
        assert cb2.is_closed


class TestConvenienceFunction:
    """Tests for get_circuit_breaker convenience function."""

    def setup_method(self):
        CircuitBreakerRegistry.clear()

    def test_get_circuit_breaker_returns_instance(self):
        """Should return circuit breaker instance.

        NOTE: Circuit breaker is always enabled (no global kill switch).
        """
        with patch("src.infrastructure.resilience.circuit_breaker.settings") as mock_settings:
            mock_settings.circuit_breaker_failure_threshold = 5
            mock_settings.circuit_breaker_success_threshold = 3
            mock_settings.circuit_breaker_timeout_seconds = 60
            mock_settings.circuit_breaker_half_open_max_calls = 3

            cb = get_circuit_breaker("test_service")

            assert cb.service == "test_service"


class TestCircuitBreakerStatus:
    """Tests for status reporting."""

    def test_get_status_returns_complete_info(self):
        """Status should include all relevant information."""
        cb = CircuitBreaker(
            service="status_test",
            failure_threshold=5,
            success_threshold=3,
            timeout_seconds=60,
            half_open_max_calls=2,
        )

        status = cb.get_status()

        assert status["service"] == "status_test"
        assert status["state"] == "closed"
        assert status["failure_count"] == 0
        assert status["config"]["failure_threshold"] == 5
        assert status["config"]["success_threshold"] == 3


class TestCircuitBreakerReset:
    """Tests for manual reset functionality."""

    @pytest.mark.asyncio
    async def test_reset_closes_open_circuit(self):
        """Manual reset should close an open circuit."""
        cb = CircuitBreaker(
            service="reset_test",
            failure_threshold=1,
        )

        # Open the circuit
        await cb.record_failure(Exception("test"))
        assert cb.is_open

        # Reset
        await cb.reset()

        assert cb.is_closed
        assert cb._failure_count == 0
        assert cb._success_count == 0
