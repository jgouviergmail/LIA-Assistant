"""
Resilience patterns for fault tolerance.

This module provides infrastructure for handling transient failures
in distributed systems, including circuit breaker pattern.

Sprint 16 - Gold-Grade Architecture
Created: 2025-12-18
"""

from src.infrastructure.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitBreakerRegistry,
    CircuitState,
    get_circuit_breaker,
)

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerError",
    "CircuitBreakerRegistry",
    "CircuitState",
    "get_circuit_breaker",
]
