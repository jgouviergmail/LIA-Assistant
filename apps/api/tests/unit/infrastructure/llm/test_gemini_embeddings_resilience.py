"""The embedding path must survive a provider that rate-limits it.

Measured in production on 2026-09-01: 11 failures out of 24 calls (46 %), all
``429 RESOURCE_EXHAUSTED`` on the per-minute quota of the ``gemini-embedding``
base model, and every one of them degraded something in silence — RAG context
missing from an answer, journal context missing, a memory never written, a
message never indexed, the router's tool scoring skipped.

Three mechanisms, three distinct jobs, and it matters that they are not
confused with one another:

- the scheduler's **jitter** removes the burst at its source (elsewhere);
- the **shaper** caps instantaneous concurrency, which is what keeps this
  working as the number of users grows;
- the **retry** recovers the residual — the 429 that slips through anyway, and
  the plain 500 the provider also returns.

The tests below pin the contract of the last two, plus the one structural
change that made retrying possible at all: the call is built by a FACTORY, so
each attempt gets a fresh awaitable.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from google.genai.errors import ClientError, ServerError
from langchain_google_genai._common import GoogleGenerativeAIError

from src.core.config import settings
from src.core.constants import (
    EMBEDDING_PROVIDER_DELAY_JITTER_SECONDS,
    EMBEDDING_PROVIDER_DELAY_MARGIN_SECONDS,
)
from src.core.exceptions import MaxRetriesExceededError
from src.infrastructure.llm.embedding_errors import embedding_retry_reason
from src.infrastructure.llm.embedding_patience import embeddings_may_wait, patient_embeddings
from src.infrastructure.llm.gemini_embeddings import (
    GeminiRetrievalEmbeddings,
    is_transient_embedding_error,
)
from src.infrastructure.rate_limiting.slot_waiter import SlotOutcome

pytestmark = pytest.mark.unit

_SLOT = "src.infrastructure.llm.gemini_embeddings.wait_for_slot"


def _embeddings() -> GeminiRetrievalEmbeddings:
    with patch("src.infrastructure.llm.gemini_embeddings.GoogleGenerativeAIEmbeddings"):
        return GeminiRetrievalEmbeddings(model="models/gemini-embedding-001")


def _quota_error() -> Exception:
    return RuntimeError(
        "Error embedding content (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. "
        "{'error': {'code': 429, 'message': 'Quota exceeded for "
        "aiplatform.googleapis.com/global_embed_content_requests_per_minute_per_base_model'}}"
    )


# ---------------------------------------------------------------------------
# Which failures deserve a second chance
# ---------------------------------------------------------------------------


class TestTransientClassification:
    """Retrying the wrong error is not free: it triples the latency of a
    failure that was never going to succeed."""

    @pytest.mark.parametrize(
        "message",
        [
            "429 RESOURCE_EXHAUSTED. Quota exceeded for aiplatform.googleapis.com",
            "Error embedding content: 500 INTERNAL. Internal error encountered.",
            "503 Service Unavailable",
            "504 Deadline Exceeded",
            "The read operation timed out",
            "Connection reset by peer",
        ],
    )
    def test_transient_provider_failures_are_retryable(self, message: str) -> None:
        assert is_transient_embedding_error(RuntimeError(message)) is True

    @pytest.mark.parametrize(
        "message",
        [
            "400 INVALID_ARGUMENT: text is empty",
            "403 PERMISSION_DENIED: API key not valid",
            "401 UNAUTHENTICATED",
            "404 NOT_FOUND: model does not exist",
        ],
    )
    def test_a_permanent_failure_is_never_retried(self, message: str) -> None:
        """A bad key or a malformed input fails identically three times; the
        only thing retrying buys is three times the delay before the caller
        learns it."""
        assert is_transient_embedding_error(RuntimeError(message)) is False

    def test_classification_reads_the_message_not_the_exception_class(self) -> None:
        """The provider SDK raises one broad type for everything, so the class
        carries no information and the payload carries all of it."""

        class WeirdProviderError(Exception):
            pass

        assert is_transient_embedding_error(WeirdProviderError("429 RESOURCE_EXHAUSTED")) is True
        assert is_transient_embedding_error(WeirdProviderError("400 INVALID_ARGUMENT")) is False


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------


class TestRetryOnTransientFailure:
    async def test_a_quota_error_is_retried_and_can_succeed(self) -> None:
        """Budget read from settings, never hardcoded: the ceiling on this
        path is deliberately tight and moving it must not silently invalidate
        the test that proves retrying works."""
        from src.core.config import settings

        budget = settings.embedding_retry_max_attempts
        embeddings = _embeddings()
        attempts: list[int] = []

        async def flaky(*_args, **_kwargs):
            attempts.append(len(attempts))
            if len(attempts) < budget:
                raise _quota_error()
            return [0.1, 0.2]

        embeddings._client.aembed_query = flaky
        with patch(_SLOT, AsyncMock(return_value=SlotOutcome.ACQUIRED)):
            with patch("asyncio.sleep", AsyncMock()):
                result = await embeddings.aembed_query("bonjour")

        assert result == [0.1, 0.2]
        assert len(attempts) == budget, "each attempt must call the provider AGAIN"

    async def test_every_attempt_gets_a_FRESH_awaitable(self) -> None:
        """The reason the seam takes a factory. A coroutine is awaitable once;
        re-awaiting the same object raises RuntimeError instead of retrying,
        which is why this path could not retry before."""
        embeddings = _embeddings()
        created: list[object] = []

        async def _call(*_args, **_kwargs):
            raise _quota_error()

        def factory(*args, **kwargs):
            coro = _call(*args, **kwargs)
            created.append(coro)
            return coro

        embeddings._client.aembed_query = factory
        with patch(_SLOT, AsyncMock(return_value=SlotOutcome.ACQUIRED)):
            with patch("asyncio.sleep", AsyncMock()):
                with pytest.raises(Exception):
                    await embeddings.aembed_query("bonjour")

        assert len(created) >= 2
        assert len({id(c) for c in created}) == len(created), "no coroutine reused"

    async def test_a_permanent_failure_fails_on_the_FIRST_attempt(self) -> None:
        embeddings = _embeddings()
        attempts: list[int] = []

        async def always_bad(*_args, **_kwargs):
            attempts.append(1)
            raise RuntimeError("400 INVALID_ARGUMENT: text is empty")

        embeddings._client.aembed_query = always_bad
        with patch(_SLOT, AsyncMock(return_value=SlotOutcome.ACQUIRED)):
            with patch("asyncio.sleep", AsyncMock()):
                with pytest.raises(RuntimeError, match="INVALID_ARGUMENT"):
                    await embeddings.aembed_query("bonjour")

        assert len(attempts) == 1

    async def test_an_exhausted_retry_still_raises_for_the_caller(self) -> None:
        """Five subsystems catch this and degrade; none of them may be told the
        embedding succeeded."""
        embeddings = _embeddings()

        async def always_429(*_args, **_kwargs):
            raise _quota_error()

        embeddings._client.aembed_query = always_429
        with patch(_SLOT, AsyncMock(return_value=SlotOutcome.ACQUIRED)):
            with patch("asyncio.sleep", AsyncMock()):
                with pytest.raises(MaxRetriesExceededError):
                    await embeddings.aembed_query("bonjour")


# ---------------------------------------------------------------------------
# Shaping
# ---------------------------------------------------------------------------


class TestShaping:
    async def test_a_slot_is_requested_before_calling_the_provider(self) -> None:
        embeddings = _embeddings()
        embeddings._client.aembed_query = AsyncMock(return_value=[0.0])

        with patch(_SLOT, AsyncMock(return_value=SlotOutcome.ACQUIRED)) as slot:
            await embeddings.aembed_query("bonjour")

        slot.assert_awaited_once()

    async def test_the_slot_key_is_the_MODEL_not_the_user(self) -> None:
        """The quota is global per base model. Keyed per user, every user would
        get their own budget and the shaper would shape nothing."""
        embeddings = _embeddings()
        embeddings._client.aembed_query = AsyncMock(return_value=[0.0])

        with patch(_SLOT, AsyncMock(return_value=SlotOutcome.ACQUIRED)) as slot:
            await embeddings.aembed_query("bonjour")

        key = slot.await_args.args[0] if slot.await_args.args else slot.await_args.kwargs["key"]
        assert "gemini-embedding-001" in key

    async def test_an_expired_wait_still_lets_the_call_through(self) -> None:
        """The shaper is not a gate: our own throttle must never be the reason
        an answer loses its memory."""
        embeddings = _embeddings()
        embeddings._client.aembed_query = AsyncMock(return_value=[0.42])

        with patch(_SLOT, AsyncMock(return_value=SlotOutcome.EXPIRED)):
            assert await embeddings.aembed_query("bonjour") == [0.42]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


class TestMetrics:
    async def test_every_ATTEMPT_is_counted_and_the_outcome_counted_once(self) -> None:
        """The existing series counts provider calls and keeps doing so — with
        retries, one logical failure is several attempts and that is the truth
        about what hit the provider. The alert needs the other number, so the
        outcome is counted separately, exactly once per operation."""
        from src.infrastructure.llm import gemini_embeddings as mod

        embeddings = _embeddings()
        attempts: list[int] = []

        async def flaky(*_args, **_kwargs):
            attempts.append(1)
            if len(attempts) < 2:
                raise _quota_error()
            return [1.0]

        embeddings._client.aembed_query = flaky

        calls: list[str] = []
        outcomes: list[str] = []
        with patch.object(mod, "embedding_api_calls_total") as api_calls:
            with patch.object(mod, "embedding_call_outcomes_total") as outcome_metric:
                api_calls.labels.side_effect = lambda **kw: type(
                    "M", (), {"inc": lambda _s, *a: calls.append(kw["status"])}
                )()
                outcome_metric.labels.side_effect = lambda **kw: type(
                    "M", (), {"inc": lambda _s, *a: outcomes.append(kw["outcome"])}
                )()
                with patch(_SLOT, AsyncMock(return_value=SlotOutcome.ACQUIRED)):
                    with patch("asyncio.sleep", AsyncMock()):
                        await embeddings.aembed_query("bonjour")

        assert calls.count("error") == 1, "the failed attempt is a real provider call"
        assert calls.count("success") == 1
        assert outcomes == ["succeeded"], "one operation, one outcome"


class TestTheBudgetStaysOffTheCriticalPath:
    """`user_message_embedding` shares its singleton with the memory domain, so
    the same instance serves a user's turn and a background batch. There is no
    instance to give a patient budget to — which makes the DEFAULTS the only
    thing standing between resilience and a chat turn that stalls.
    """

    def test_the_worst_case_added_delay_respects_its_ceiling(self) -> None:
        from src.core.config import settings
        from src.core.constants import EMBEDDING_WORST_CASE_ADDED_SECONDS

        # Every attempt waits for its own slot, plus the backoff before each
        # retry after the first try.
        attempts = settings.embedding_retry_max_attempts
        retries = max(0, attempts - 1)
        worst = attempts * settings.embedding_rate_limit_wait_seconds + sum(
            settings.embedding_retry_backoff_factor**attempt for attempt in range(retries)
        )
        assert worst <= EMBEDDING_WORST_CASE_ADDED_SECONDS, (
            f"A failing embedding would add {worst:.1f}s to a chat turn. Past "
            "the ceiling this stops protecting the answer and starts delaying it."
        )

    def test_retry_is_enabled_at_all(self) -> None:
        """The other side of the same guard: a ceiling met by disabling the
        feature is not a passing test."""
        from src.core.config import settings

        assert settings.embedding_retry_max_attempts >= 2
        assert settings.embedding_rate_limit_max_calls > 0


class TestAgainstTheRealCountersAndSettings:
    """No metric doubles, no settings doubles.

    The tests above patch the counters to observe them precisely. This one runs
    the same paths against the REAL Prometheus objects and the REAL settings,
    because a contract that only holds against a mock is a contract about the
    mock — and the counters are what the new alert reads.
    """

    @staticmethod
    def _value(metric, **labels) -> float:
        for family in metric.collect():
            for sample in family.samples:
                if sample.name.endswith("_total") and all(
                    sample.labels.get(k) == v for k, v in labels.items()
                ):
                    return float(sample.value)
        return 0.0

    async def test_a_recovered_failure_moves_both_counters_the_right_way(self) -> None:
        from src.core.config import settings
        from src.infrastructure.llm.tracked_embeddings import (
            embedding_api_calls_total,
            embedding_call_outcomes_total,
        )

        model = "gemini-embedding-001"
        before_attempts = self._value(embedding_api_calls_total, model=model, status="error")
        before_ok = self._value(embedding_call_outcomes_total, model=model, outcome="succeeded")

        embeddings = _embeddings()
        attempts: list[int] = []

        async def flaky(*_args, **_kwargs):
            attempts.append(1)
            if len(attempts) < settings.embedding_retry_max_attempts:
                raise _quota_error()
            return [0.1, 0.2, 0.3]

        embeddings._client.aembed_query = flaky
        with patch(_SLOT, AsyncMock(return_value=SlotOutcome.ACQUIRED)):
            with patch("asyncio.sleep", AsyncMock()):
                vector = await embeddings.aembed_query("bonjour")

        assert len(vector) == 3
        # Each failed attempt is a real provider call and is counted as one...
        assert self._value(embedding_api_calls_total, model=model, status="error") == (
            before_attempts + settings.embedding_retry_max_attempts - 1
        )
        # ...while the OPERATION succeeded exactly once. That gap is precisely
        # why the alert reads outcomes: on attempts it would fire on an
        # incident that repaired itself.
        assert self._value(embedding_call_outcomes_total, model=model, outcome="succeeded") == (
            before_ok + 1
        )

    async def test_an_operation_that_gives_up_is_counted_as_failed_once(self) -> None:
        from src.infrastructure.llm.tracked_embeddings import embedding_call_outcomes_total

        model = "gemini-embedding-001"
        before = self._value(embedding_call_outcomes_total, model=model, outcome="failed")

        embeddings = _embeddings()

        async def always_429(*_args, **_kwargs):
            raise _quota_error()

        embeddings._client.aembed_query = always_429
        with patch(_SLOT, AsyncMock(return_value=SlotOutcome.ACQUIRED)):
            with patch("asyncio.sleep", AsyncMock()):
                with pytest.raises(MaxRetriesExceededError):
                    await embeddings.aembed_query("bonjour")

        assert self._value(embedding_call_outcomes_total, model=model, outcome="failed") == (
            before + 1
        )

    async def test_a_cancelled_operation_is_not_recorded_as_a_failure(self) -> None:
        """Cancellation is not a provider failure, and counting it as one would
        make every shutdown look like an incident on the alert."""
        import asyncio

        from src.infrastructure.llm.tracked_embeddings import embedding_call_outcomes_total

        model = "gemini-embedding-001"
        before = self._value(embedding_call_outcomes_total, model=model, outcome="failed")

        embeddings = _embeddings()

        async def cancelled(*_args, **_kwargs):
            raise asyncio.CancelledError()

        embeddings._client.aembed_query = cancelled
        with patch(_SLOT, AsyncMock(return_value=SlotOutcome.ACQUIRED)):
            with pytest.raises(asyncio.CancelledError):
                await embeddings.aembed_query("bonjour")

        assert self._value(embedding_call_outcomes_total, model=model, outcome="failed") == before


class TestRetriesAreShapedToo:
    """A retry is another call on a provider that just refused one.

    Taking the slot once, outside the loop, would let every retry bypass the
    shaper — adding load exactly when the quota is saturated, and turning a
    burst into a storm as the number of users grows. Each ATTEMPT asks.
    """

    async def test_each_attempt_asks_for_its_own_slot(self) -> None:
        from src.core.config import settings

        embeddings = _embeddings()
        attempts: list[int] = []

        async def flaky(*_args, **_kwargs):
            attempts.append(1)
            if len(attempts) < settings.embedding_retry_max_attempts:
                raise _quota_error()
            return [0.0]

        embeddings._client.aembed_query = flaky
        with patch(_SLOT, AsyncMock(return_value=SlotOutcome.ACQUIRED)) as slot:
            with patch("asyncio.sleep", AsyncMock()):
                await embeddings.aembed_query("bonjour")

        assert slot.await_count == len(attempts), (
            "Retries that skip the shaper add load to a provider that is " "already refusing calls."
        )

    async def test_a_single_attempt_asks_once(self) -> None:
        embeddings = _embeddings()
        embeddings._client.aembed_query = AsyncMock(return_value=[0.0])

        with patch(_SLOT, AsyncMock(return_value=SlotOutcome.ACQUIRED)) as slot:
            await embeddings.aembed_query("bonjour")

        assert slot.await_count == 1


class TestTheShaperIsObservable:
    """With 1 to 3 active users the shaper never holds; the day it does, an
    operator must be able to SEE it rather than infer it from slower answers.

    Nothing acts on the outcome — the call goes through regardless — so the
    counter is the only trace that the budget has become too small.
    """

    @staticmethod
    def _count(model: str, outcome: str) -> float:
        from src.infrastructure.llm.tracked_embeddings import embedding_shaper_outcomes_total

        return embedding_shaper_outcomes_total.labels(model=model, outcome=outcome)._value.get()

    async def test_an_expired_wait_is_counted_under_its_own_label(self) -> None:
        embeddings = _embeddings()
        embeddings._client.aembed_query = AsyncMock(return_value=[0.0])
        before = self._count(embeddings.model_name, "expired")

        with patch(_SLOT, AsyncMock(return_value=SlotOutcome.EXPIRED)):
            await embeddings.aembed_query("bonjour")

        assert self._count(embeddings.model_name, "expired") == before + 1

    async def test_redis_being_down_is_NOT_counted_as_a_full_shaper(self) -> None:
        """Raising the budget would not fix a Redis outage, and restarting Redis
        would not fix a budget too small for the number of users. The two must
        not share a line on the chart."""
        embeddings = _embeddings()
        embeddings._client.aembed_query = AsyncMock(return_value=[0.0])
        before_expired = self._count(embeddings.model_name, "expired")
        before_unavailable = self._count(embeddings.model_name, "unavailable")

        with patch(_SLOT, AsyncMock(return_value=SlotOutcome.UNAVAILABLE)):
            await embeddings.aembed_query("bonjour")

        assert self._count(embeddings.model_name, "unavailable") == before_unavailable + 1
        assert self._count(embeddings.model_name, "expired") == before_expired

    async def test_every_attempt_of_a_retried_operation_is_counted(self) -> None:
        """The shaper is asked per ATTEMPT, so its counter must move per attempt
        — otherwise a saturated budget looks half as saturated as it is."""
        embeddings = _embeddings()
        embeddings._client.aembed_query = AsyncMock(side_effect=[_quota_error(), [0.0]])
        before = self._count(embeddings.model_name, "acquired")

        with patch(_SLOT, AsyncMock(return_value=SlotOutcome.ACQUIRED)):
            with patch("asyncio.sleep", AsyncMock()):
                await embeddings.aembed_query("bonjour")

        assert self._count(embeddings.model_name, "acquired") == before + 2


# ---------------------------------------------------------------------------
# The provider's own delay
# ---------------------------------------------------------------------------

_JITTER = "src.infrastructure.llm.gemini_embeddings._jitter_seconds"


def _as_langchain_raises_it(provider_error: Exception) -> Exception:
    try:
        raise GoogleGenerativeAIError(f"Error embedding content: {provider_error}") from (
            provider_error
        )
    except GoogleGenerativeAIError as wrapped:
        return wrapped


def _refusal(retry_delay: str) -> Exception:
    """A per-minute quota refusal: the SDK error carrying the delay is the cause."""
    return _as_langchain_raises_it(
        ClientError(
            429,
            {
                "error": {
                    "code": 429,
                    "status": "RESOURCE_EXHAUSTED",
                    "message": "Embed content requests per minute limit exceeded",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.RetryInfo",
                            "retryDelay": retry_delay,
                        }
                    ],
                }
            },
        )
    )


def _internal_error() -> Exception:
    """A transient failure that names no delay."""
    return _as_langchain_raises_it(
        ServerError(500, {"error": {"code": 500, "status": "INTERNAL", "message": "internal"}})
    )


async def _embed_through(failures: list[Exception]) -> tuple[object, list[float], int]:
    """Embed once, the provider failing in turn with ``failures`` then answering.

    Returns:
        What the caller got (the vector, or the exception raised), every wait
        served between attempts, and how many times the provider was called.
    """
    embeddings = _embeddings()
    pending = list(failures)
    calls = 0

    async def provider(*_args: object, **_kwargs: object) -> list[float]:
        nonlocal calls
        calls += 1
        if pending:
            raise pending.pop(0)
        return [0.1, 0.2]

    embeddings._client.aembed_query = provider
    sleep = AsyncMock()
    outcome: object
    with patch(_SLOT, AsyncMock(return_value=SlotOutcome.ACQUIRED)), patch("asyncio.sleep", sleep):
        try:
            outcome = await embeddings.aembed_query("bonjour")
        except Exception as error:  # noqa: BLE001 — the error IS what the test reads
            outcome = error
    return outcome, [call.args[0] for call in sleep.await_args_list], calls


def _backoff_wait() -> float:
    """What the client waits before its first retry when nobody names a delay."""
    return float(settings.embedding_retry_backoff_factor**0)


class TestIndexingWaitsWhatTheProviderAsks:
    """Measured on 2026-11-09: 581 quota refusals, every one naming a delay of
    20 to 49 seconds, every one retried after ONE second — 302 retries that
    could not succeed, and 253 documents failed for it."""

    async def test_it_waits_the_named_delay_and_the_retry_succeeds(self) -> None:
        with patient_embeddings(), patch(_JITTER, return_value=0.0):
            outcome, waits, calls = await _embed_through([_refusal("40s")])

        assert outcome == [0.1, 0.2]
        assert calls == 2
        # The structured delay is rounded DOWN (40s for 40.38 s): the margin is
        # what keeps the retry from arriving a fraction of a second early.
        assert waits == [40.0 + EMBEDDING_PROVIDER_DELAY_MARGIN_SECONDS]

    async def test_the_wait_is_spread_so_the_batch_does_not_come_back_as_one(self) -> None:
        with patient_embeddings():
            _outcome, waits, _calls = await _embed_through([_refusal("40s")])

        floor = 40.0 + EMBEDDING_PROVIDER_DELAY_MARGIN_SECONDS
        assert floor <= waits[0] <= floor + EMBEDDING_PROVIDER_DELAY_JITTER_SECONDS

    async def test_a_delay_beyond_its_patience_is_not_waited_at_all(self) -> None:
        """An exhausted daily quota says « come back in an hour »: waiting a
        minute before failing anyway would only hold the batch."""
        beyond = int(settings.embedding_patient_retry_max_wait_seconds) + 1
        with patient_embeddings():
            outcome, waits, calls = await _embed_through([_refusal(f"{beyond}s")])

        assert isinstance(outcome, MaxRetriesExceededError)
        assert (waits, calls) == ([], 1)

    async def test_a_delay_exactly_at_its_patience_is_still_waited(self) -> None:
        at_most = int(settings.embedding_patient_retry_max_wait_seconds)
        with patient_embeddings(), patch(_JITTER, return_value=0.0):
            outcome, waits, calls = await _embed_through([_refusal(f"{at_most}s")])

        assert outcome == [0.1, 0.2]
        assert waits == [at_most + EMBEDDING_PROVIDER_DELAY_MARGIN_SECONDS]
        assert calls == 2

    async def test_a_second_refusal_ends_the_operation_as_an_exhausted_retry(self) -> None:
        with patient_embeddings(), patch(_JITTER, return_value=0.0):
            outcome, _waits, calls = await _embed_through(
                [_refusal("40s")] * settings.embedding_retry_max_attempts
            )

        assert isinstance(outcome, MaxRetriesExceededError)
        assert calls == settings.embedding_retry_max_attempts

    @pytest.mark.parametrize("patience", [0.0, 0.5])
    async def test_declared_work_is_never_stricter_than_undeclared_work(
        self, monkeypatch: pytest.MonkeyPatch, patience: float
    ) -> None:
        """A patience switched off (0), or set below the ordinary wait, must
        leave declared work at least what every caller has: a refusal naming a
        delay within the ordinary one-second wait is still retried."""
        monkeypatch.setattr(settings, "embedding_patient_retry_max_wait_seconds", patience)
        within = f"{_backoff_wait():g}s"
        with patient_embeddings(), patch(_JITTER, return_value=0.0):
            outcome, waits, calls = await _embed_through([_refusal(within)])

        assert outcome == [0.1, 0.2]
        assert calls == 2
        assert waits == [_backoff_wait() + EMBEDDING_PROVIDER_DELAY_MARGIN_SECONDS]

    async def test_a_patience_of_zero_waits_for_no_long_delay(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "embedding_patient_retry_max_wait_seconds", 0.0)
        with patient_embeddings():
            outcome, waits, calls = await _embed_through([_refusal("40s")])

        assert isinstance(outcome, MaxRetriesExceededError)
        assert (waits, calls) == ([], 1)

    async def test_a_failure_that_names_no_delay_keeps_the_ordinary_backoff(self) -> None:
        with patient_embeddings():
            outcome, waits, calls = await _embed_through([_internal_error()])

        assert outcome == [0.1, 0.2]
        assert (waits, calls) == ([_backoff_wait()], 2)


class TestAChatTurnDoesNotWaitForAQuota:
    """Nothing declared: an embedding is on somebody's turn. The provider said
    « in 40 seconds »; the retry one second later was a second refusal bought
    with a second of the answer's time."""

    async def test_a_refusal_naming_a_long_delay_is_not_retried(self) -> None:
        outcome, waits, calls = await _embed_through([_refusal("40s")])

        assert isinstance(outcome, MaxRetriesExceededError)
        assert (waits, calls) == ([], 1)

    async def test_the_failure_reads_like_an_exhausted_retry_to_its_callers(self) -> None:
        """Same type, same cause chain: whoever classified the old failure
        (the system indexer walks the chain for the status code) reads this one
        the same way — it only arrives sooner."""
        outcome, _waits, _calls = await _embed_through([_refusal("40s")])

        assert isinstance(outcome, MaxRetriesExceededError)
        assert outcome.max_retries == 1, "one attempt was made, and the error says so"
        assert embedding_retry_reason(outcome) == "http_429"

    async def test_a_delay_within_its_own_wait_is_retried_exactly_as_before(self) -> None:
        within = f"{_backoff_wait():g}s"
        outcome, waits, calls = await _embed_through([_refusal(within)])

        assert outcome == [0.1, 0.2]
        assert (waits, calls) == ([_backoff_wait()], 2)

    async def test_a_failure_that_names_no_delay_is_retried_exactly_as_before(self) -> None:
        outcome, waits, calls = await _embed_through([_internal_error()])

        assert outcome == [0.1, 0.2]
        assert (waits, calls) == ([_backoff_wait()], 2)

    async def test_the_old_wording_only_quota_error_is_retried_exactly_as_before(self) -> None:
        """No structure, no delay: the 2026-09-01 payload keeps its retry."""
        outcome, waits, calls = await _embed_through([_quota_error()])

        assert outcome == [0.1, 0.2]
        assert (waits, calls) == ([_backoff_wait()], 2)


class TestGivingUpEarlyIsCountedLikeAnyFailure:
    async def test_one_refused_attempt_and_one_failed_operation(self) -> None:
        from src.infrastructure.llm.tracked_embeddings import (
            embedding_api_calls_total,
            embedding_call_outcomes_total,
        )

        read = TestAgainstTheRealCountersAndSettings._value
        model = "gemini-embedding-001"
        refused = read(embedding_api_calls_total, model=model, status="error")
        failed = read(embedding_call_outcomes_total, model=model, outcome="failed")

        outcome, _waits, _calls = await _embed_through([_refusal("40s")])

        assert isinstance(outcome, MaxRetriesExceededError)
        assert read(embedding_api_calls_total, model=model, status="error") == refused + 1
        assert read(embedding_call_outcomes_total, model=model, outcome="failed") == failed + 1


class TestPatienceIsDeclaredNeverInherited:
    def test_nothing_is_patient_unless_it_says_so(self) -> None:
        """The safe side of forgetting: an undeclared call site costs nobody a
        second — which is what the single tight profile was protecting."""
        assert embeddings_may_wait() is False

    def test_the_scope_ends_where_it_was_opened_even_on_an_error(self) -> None:
        with pytest.raises(RuntimeError):
            with patient_embeddings():
                assert embeddings_may_wait() is True
                raise RuntimeError("the batch failed")

        assert embeddings_may_wait() is False

    def test_scopes_nest_and_unwind_in_order(self) -> None:
        with patient_embeddings():
            with patient_embeddings():
                assert embeddings_may_wait() is True
            assert embeddings_may_wait() is True
        assert embeddings_may_wait() is False

    async def test_a_batch_being_patient_does_not_make_a_concurrent_turn_wait(self) -> None:
        """The same singleton serves a user's turn and a background batch."""
        started = asyncio.Event()
        release = asyncio.Event()
        seen: dict[str, bool] = {}

        async def batch() -> None:
            with patient_embeddings():
                started.set()
                await release.wait()
                seen["batch"] = embeddings_may_wait()

        async def turn() -> None:
            await started.wait()
            seen["turn"] = embeddings_may_wait()
            release.set()

        await asyncio.gather(batch(), turn())

        assert seen == {"batch": True, "turn": False}

    async def test_work_started_inside_the_scope_stays_patient(self) -> None:
        """A document embeds in tasks of its own (bounded concurrency, native
        renewal brackets): the declaration must travel with them."""
        with patient_embeddings():
            inherited = await asyncio.create_task(_read_patience())

        assert inherited is True


async def _read_patience() -> bool:
    return embeddings_may_wait()
