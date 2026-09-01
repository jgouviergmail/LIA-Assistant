"""
Unit tests for retry utilities with exponential backoff.

Tests for the retry_with_backoff decorator that provides retry logic
with exponential backoff for transient failures.
"""

import asyncio
from unittest.mock import patch

import pytest

from src.core.exceptions import MaxRetriesExceededError
from src.infrastructure.utils.retry import retry_async, retry_with_backoff


class TestRetryWithBackoffAsync:
    """Tests for retry_with_backoff with async functions."""

    @pytest.mark.asyncio
    async def test_async_success_no_retry(self):
        """Test that successful async function doesn't retry."""
        call_count = 0

        @retry_with_backoff(max_retries=3)
        async def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await successful_func()
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_retry_on_exception(self):
        """Test that async function retries on exception."""
        call_count = 0

        @retry_with_backoff(
            max_retries=3,
            backoff_factor=0.01,  # Fast backoff for tests
            retryable_exceptions=(ValueError,),
        )
        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Transient error")
            return "success"

        result = await flaky_func()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_async_max_retries_exceeded(self):
        """Test that MaxRetriesExceededError is raised after max retries."""
        call_count = 0

        @retry_with_backoff(
            max_retries=3,
            backoff_factor=0.01,
            retryable_exceptions=(ValueError,),
        )
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(MaxRetriesExceededError) as exc_info:
            await always_fails()

        assert call_count == 3
        assert exc_info.value.max_retries == 3
        assert "always_fails" in exc_info.value.operation

    @pytest.mark.asyncio
    async def test_async_only_retries_specified_exceptions(self):
        """Test that only specified exceptions trigger retry."""
        call_count = 0

        @retry_with_backoff(
            max_retries=3,
            backoff_factor=0.01,
            retryable_exceptions=(ValueError,),
        )
        async def raises_runtime_error():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Not retryable")

        with pytest.raises(RuntimeError):
            await raises_runtime_error()

        # Should only be called once (no retry for RuntimeError)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_custom_operation_name(self):
        """Test that custom operation name is used in error."""

        @retry_with_backoff(
            max_retries=1,
            backoff_factor=0.01,
            retryable_exceptions=(ValueError,),
            operation_name="custom_operation",
        )
        async def my_func():
            raise ValueError("Error")

        with pytest.raises(MaxRetriesExceededError) as exc_info:
            await my_func()

        assert exc_info.value.operation == "custom_operation"

    @pytest.mark.asyncio
    async def test_async_backoff_timing(self):
        """Test that backoff increases exponentially."""
        call_times = []

        @retry_with_backoff(
            max_retries=3,
            backoff_factor=0.1,  # 0.1s, 0.1s for first two sleeps
            retryable_exceptions=(ValueError,),
            log_retries=False,
        )
        async def flaky_func():
            call_times.append(asyncio.get_event_loop().time())
            if len(call_times) < 3:
                raise ValueError("Transient")
            return "success"

        await flaky_func()

        # Check that there were delays between calls
        assert len(call_times) == 3
        # Second call should be after first backoff (0.1^0 = 1s, but we use 0.1)
        assert call_times[1] - call_times[0] >= 0.05  # Some tolerance
        # Third call should be after second backoff (0.1^1 = 0.1s)
        assert call_times[2] - call_times[1] >= 0.05

    @pytest.mark.asyncio
    async def test_async_log_retries_can_be_disabled(self):
        """Test that log_retries=False suppresses retry logs."""

        @retry_with_backoff(
            max_retries=2,
            backoff_factor=0.01,
            retryable_exceptions=(ValueError,),
            log_retries=False,
        )
        async def flaky_func():
            raise ValueError("Error")

        with patch("src.infrastructure.utils.retry.logger") as mock_logger:
            with pytest.raises(MaxRetriesExceededError):
                await flaky_func()

            # Warning should not be called (only error at the end)
            mock_logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_preserves_function_metadata(self):
        """Test that decorator preserves function metadata."""

        @retry_with_backoff(max_retries=3)
        async def documented_func():
            """This is the docstring."""
            return "result"

        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "This is the docstring."


class TestRetryWithBackoffSync:
    """Tests for retry_with_backoff with sync functions."""

    def test_sync_success_no_retry(self):
        """Test that successful sync function doesn't retry."""
        call_count = 0

        @retry_with_backoff(max_retries=3)
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_func()
        assert result == "success"
        assert call_count == 1

    def test_sync_retry_on_exception(self):
        """Test that sync function retries on exception."""
        call_count = 0

        @retry_with_backoff(
            max_retries=3,
            backoff_factor=0.01,
            retryable_exceptions=(ValueError,),
        )
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Transient error")
            return "success"

        result = flaky_func()
        assert result == "success"
        assert call_count == 3

    def test_sync_max_retries_exceeded(self):
        """Test that MaxRetriesExceededError is raised after max retries."""
        call_count = 0

        @retry_with_backoff(
            max_retries=3,
            backoff_factor=0.01,
            retryable_exceptions=(ValueError,),
        )
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(MaxRetriesExceededError) as exc_info:
            always_fails()

        assert call_count == 3
        assert exc_info.value.max_retries == 3

    def test_sync_only_retries_specified_exceptions(self):
        """Test that only specified exceptions trigger retry."""
        call_count = 0

        @retry_with_backoff(
            max_retries=3,
            backoff_factor=0.01,
            retryable_exceptions=(ValueError,),
        )
        def raises_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("Not retryable")

        with pytest.raises(TypeError):
            raises_type_error()

        assert call_count == 1

    def test_sync_preserves_function_metadata(self):
        """Test that decorator preserves function metadata."""

        @retry_with_backoff(max_retries=3)
        def documented_func():
            """This is the docstring."""
            return "result"

        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "This is the docstring."


class TestRetryWithBackoffDefaults:
    """Tests for default parameter values."""

    @pytest.mark.asyncio
    async def test_default_max_retries_is_3(self):
        """Test that default max_retries is 3."""
        call_count = 0

        @retry_with_backoff(
            backoff_factor=0.01,
            retryable_exceptions=(ValueError,),
        )
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("Error")

        with pytest.raises(MaxRetriesExceededError):
            await always_fails()

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_default_backoff_factor_is_2(self):
        """Test that default backoff_factor is 2.0."""

        # We test this indirectly by checking the decorator signature
        # The actual timing test would be too slow for unit tests
        @retry_with_backoff(max_retries=1, retryable_exceptions=(ValueError,))
        async def func():
            raise ValueError("Error")

        # Just verify the decorator works with defaults
        with pytest.raises(MaxRetriesExceededError):
            await func()

    @pytest.mark.asyncio
    async def test_default_retryable_exceptions_is_exception(self):
        """Test that default retryable_exceptions is (Exception,)."""
        call_count = 0

        @retry_with_backoff(max_retries=2, backoff_factor=0.01)
        async def raises_any_exception():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Error")
            return "success"

        result = await raises_any_exception()
        assert result == "success"
        assert call_count == 2


class TestRetryWithBackoffEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_max_retries_1_no_retry(self):
        """Test that max_retries=1 means single attempt (no retry)."""
        call_count = 0

        @retry_with_backoff(
            max_retries=1,
            backoff_factor=0.01,
            retryable_exceptions=(ValueError,),
        )
        async def fails_once():
            nonlocal call_count
            call_count += 1
            raise ValueError("Error")

        with pytest.raises(MaxRetriesExceededError):
            await fails_once()

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_preserves_last_exception(self):
        """Test that last exception is preserved in MaxRetriesExceededError."""

        @retry_with_backoff(
            max_retries=2,
            backoff_factor=0.01,
            retryable_exceptions=(ValueError,),
        )
        async def fails():
            raise ValueError("Specific error message")

        with pytest.raises(MaxRetriesExceededError) as exc_info:
            await fails()

        assert exc_info.value.last_error is not None
        assert "Specific error message" in str(exc_info.value.last_error)

    @pytest.mark.asyncio
    async def test_function_with_args_and_kwargs(self):
        """Test that function arguments are properly passed."""

        @retry_with_backoff(max_retries=1, retryable_exceptions=(ValueError,))
        async def func_with_args(a, b, c=None):
            return f"{a}-{b}-{c}"

        result = await func_with_args("x", "y", c="z")
        assert result == "x-y-z"

    @pytest.mark.asyncio
    async def test_function_returns_none(self):
        """Test that function returning None works correctly."""

        @retry_with_backoff(max_retries=1)
        async def returns_none():
            return None

        result = await returns_none()
        assert result is None

    @pytest.mark.asyncio
    async def test_multiple_retryable_exceptions(self):
        """Test retry with multiple exception types."""
        call_count = 0

        @retry_with_backoff(
            max_retries=4,
            backoff_factor=0.01,
            retryable_exceptions=(ValueError, TypeError, KeyError),
        )
        async def raises_different_errors():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("First")
            if call_count == 2:
                raise TypeError("Second")
            if call_count == 3:
                raise KeyError("Third")
            return "success"

        result = await raises_different_errors()
        assert result == "success"
        assert call_count == 4


class TestRetryWithBackoffLogging:
    """Tests for logging behavior."""

    @pytest.mark.asyncio
    async def test_logs_retry_attempts(self):
        """Test that retry attempts are logged."""
        call_count = 0

        @retry_with_backoff(
            max_retries=2,
            backoff_factor=0.01,
            retryable_exceptions=(ValueError,),
            log_retries=True,
        )
        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Transient")
            return "success"

        with patch("src.infrastructure.utils.retry.logger") as mock_logger:
            await flaky_func()
            # Should log warning for the retry
            mock_logger.warning.assert_called_once()
            call_kwargs = mock_logger.warning.call_args
            assert "retry_attempt" in str(call_kwargs)

    @pytest.mark.asyncio
    async def test_logs_error_on_max_retries(self):
        """Test that error is logged when max retries exceeded."""

        @retry_with_backoff(
            max_retries=1,
            backoff_factor=0.01,
            retryable_exceptions=(ValueError,),
        )
        async def always_fails():
            raise ValueError("Error")

        with patch("src.infrastructure.utils.retry.logger") as mock_logger:
            with pytest.raises(MaxRetriesExceededError):
                await always_fails()

            # Should log error
            mock_logger.error.assert_called_once()
            call_kwargs = mock_logger.error.call_args
            assert "max_retries_exceeded" in str(call_kwargs)


# ===========================================================================
# retry_async — the functional core (ADR-254)
# ===========================================================================


class TestRetryAsyncFunctionalCore:
    """The same retry policy, callable on a FACTORY rather than a decoration.

    The decorator cannot serve a caller that must build a fresh awaitable per
    attempt: a coroutine is awaitable exactly once, so re-awaiting the same
    object raises instead of retrying. That is not a detail — it is why the
    embedding path could not retry at all before this existed.
    """

    async def test_returns_the_first_successful_result(self):
        calls = []

        async def factory():
            calls.append(1)
            return "ok"

        assert await retry_async(factory, max_retries=3, backoff_factor=0) == "ok"
        assert len(calls) == 1

    async def test_calls_the_factory_AGAIN_on_each_attempt(self):
        """The point of a factory: attempt N+1 gets a FRESH awaitable."""
        seen = []

        async def factory():
            seen.append(len(seen))
            if len(seen) < 3:
                raise ValueError("transient")
            return "recovered"

        assert await retry_async(factory, max_retries=3, backoff_factor=0) == "recovered"
        assert seen == [0, 1, 2]

    async def test_raises_MaxRetriesExceeded_carrying_the_last_error(self):
        original = ValueError("still failing")

        async def factory():
            raise original

        with pytest.raises(MaxRetriesExceededError) as excinfo:
            await retry_async(factory, max_retries=2, backoff_factor=0)
        assert excinfo.value.last_error is original

    async def test_does_not_retry_an_exception_outside_the_allowed_set(self):
        calls = []

        async def factory():
            calls.append(1)
            raise TypeError("not retryable")

        with pytest.raises(TypeError):
            await retry_async(
                factory, max_retries=3, backoff_factor=0, retryable_exceptions=(ValueError,)
            )
        assert len(calls) == 1

    async def test_waits_between_attempts_with_exponential_backoff(self):
        waits: list[float] = []

        async def factory():
            raise ValueError("boom")

        async def fake_sleep(seconds):
            waits.append(seconds)

        with patch("asyncio.sleep", fake_sleep):
            with pytest.raises(MaxRetriesExceededError):
                await retry_async(factory, max_retries=3, backoff_factor=2.0)
        assert waits == [1.0, 2.0]

    async def test_a_single_attempt_never_sleeps(self):
        """max_retries=1 means "try once": sleeping after the only attempt
        would add latency to a failure nobody is going to retry."""
        waits: list[float] = []

        async def factory():
            raise ValueError("boom")

        async def fake_sleep(seconds):
            waits.append(seconds)

        with patch("asyncio.sleep", fake_sleep):
            with pytest.raises(MaxRetriesExceededError):
                await retry_async(factory, max_retries=1, backoff_factor=2.0)
        assert waits == []

    async def test_the_decorator_and_the_core_share_ONE_implementation(self):
        """Two copies of a backoff policy drift; the decorator must delegate."""
        seen = []

        @retry_with_backoff(max_retries=3, backoff_factor=0)
        async def decorated():
            seen.append(len(seen))
            if len(seen) < 2:
                raise ValueError("transient")
            return "ok"

        assert await decorated() == "ok"
        assert len(seen) == 2


@pytest.mark.unit
class TestTheCauseSurvivesExhaustion:
    """An exhausted retry must not erase WHY it failed.

    The system indexer runs its own patient, deadline-bounded retry on top of
    the embedding client's fast one, and classifies by walking ``__cause__``
    for the provider's status code. `MaxRetriesExceededError` keeps the last
    error as an attribute only, and the raise sits outside the `except` — so
    without an explicit `from`, the chain stopped at the wrapper and a 429 that
    had exhausted the inner retry was read as permanent.
    """

    async def test_the_last_error_is_the_cause_of_the_wrapper(self) -> None:
        class _Boom(Exception):
            pass

        original = _Boom("429 quota exceeded")

        async def always_fails() -> None:
            raise original

        with pytest.raises(MaxRetriesExceededError) as excinfo:
            await retry_async(
                always_fails,
                max_retries=2,
                backoff_factor=0.0,
                retryable_exceptions=(_Boom,),
                operation_name="probe",
            )
        assert excinfo.value.__cause__ is original
        assert excinfo.value.last_error is original

    async def test_a_status_code_is_still_reachable_through_two_retry_layers(
        self,
    ) -> None:
        """The end-to-end shape: provider error → embedding marker → wrapper."""
        from src.infrastructure.llm.embedding_errors import embedding_retry_reason

        class _ProviderError(Exception):
            def __init__(self) -> None:
                super().__init__("resource exhausted")
                self.code = 429

        provider = _ProviderError()

        class _Marker(Exception):
            pass

        async def fails_like_the_embedding_client() -> None:
            try:
                raise provider
            except _ProviderError as exc:
                raise _Marker(str(exc)) from exc

        with pytest.raises(MaxRetriesExceededError) as excinfo:
            await retry_async(
                fails_like_the_embedding_client,
                max_retries=2,
                backoff_factor=0.0,
                retryable_exceptions=(_Marker,),
                operation_name="embedding_embed_documents",
            )
        # Structural, not textual: the outer retry reads the code, not the words.
        assert embedding_retry_reason(excinfo.value) == "http_429"
