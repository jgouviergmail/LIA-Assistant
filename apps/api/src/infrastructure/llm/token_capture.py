"""Shared token-usage capture callback for structured-output LLM calls.

``get_structured_output`` (the structured-output chokepoint) returns only the
parsed Pydantic model — the raw ``AIMessage`` and its usage metadata never
reach the caller. Paths that must track their spend (proactive tasks:
heartbeat, open-loop extraction, telephony return synthesis) attach this
handler to the ``RunnableConfig`` callbacks and read the counters after the
call.

Consolidates the two historical private copies (``heartbeat/prompts.py`` and
``agents/services/open_loop_extractor.py``) which each read a *different*
surface of the ``LLMResult``:

- per-generation ``message.usage_metadata`` (LangChain-canonical, populated
  by every chat-model integration) — preferred;
- response-level ``llm_output["token_usage"]`` (OpenAI-compatible aggregate)
  — fallback only, so a provider populating both is never double-counted.

The counters are in the ONE reader's buckets (``usage_metadata.py``, ADR-306):
``tokens_in`` is the billable input with the cache reads REMOVED, priced apart
through ``tokens_cache``, and ``tokens_cache_write`` is the part of
``tokens_in`` Claude wrote to its prompt cache. They used to be the RAW
provider values while four of the five callers priced ``tokens_cache`` on top,
so every cached token was billed twice there.
"""

from __future__ import annotations

from datetime import UTC, datetime
from threading import RLock
from time import time
from typing import Any, Literal
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from src.core.llm_usage import LLMBillingRecord
from src.infrastructure.cache.pricing_cache import (
    PricingCacheData,
    capture_pricing_snapshot,
    get_cached_cost_usd_eur,
    get_cached_usd_eur_rate,
)
from src.infrastructure.llm.inference_params import requested_model
from src.infrastructure.llm.usage_metadata import (
    UsageTokens,
    model_name_of_response,
    sum_usage,
    tokens_from_response,
    tokens_from_usage_metadata,
)
from src.infrastructure.observability.error_taxonomy import classify_llm_error


def _generation_usage(response: LLMResult) -> UsageTokens | None:
    """Sum per-generation ``message.usage_metadata`` (LangChain-canonical surface).

    Returns:
        The summed reading, or ``None`` when no generation carried usage
        metadata at all.
    """
    readings = [
        tokens_from_usage_metadata(meta)
        for generation_list in response.generations
        for gen in generation_list
        if (meta := getattr(getattr(gen, "message", None), "usage_metadata", None))
    ]
    return sum_usage(readings) if readings else None


def _aggregate_usage(response: LLMResult) -> UsageTokens:
    """Usage from ``llm_output["token_usage"]`` (OpenAI-compatible aggregate).

    Its ``prompt_tokens`` includes the cached ones, like ``input_tokens`` does,
    so it goes through the same reader under the LangChain spelling.
    """
    llm_output = getattr(response, "llm_output", None) or {}
    token_usage = llm_output.get("token_usage") or {}
    details = token_usage.get("prompt_tokens_details") or {}
    return tokens_from_usage_metadata(
        {
            "input_tokens": token_usage.get("prompt_tokens"),
            "output_tokens": token_usage.get("completion_tokens"),
            "input_token_details": {"cache_read": details.get("cached_tokens")},
        }
    )


def _response_model(response: LLMResult) -> str | None:
    """Prefer the provider's reported model to the pre-call request."""
    returned = next(
        (
            model
            for generations in response.generations
            for generation in generations
            if (model := model_name_of_response(getattr(generation, "message", None)))
        ),
        None,
    )
    output = response.llm_output or {}
    reported = returned or output.get("model_name") or output.get("model")
    return reported if isinstance(reported, str) else None


def priced_call(
    usage: UsageTokens,
    model_name: str,
    started_at: float,
    *,
    snapshot: PricingCacheData | None = None,
) -> LLMBillingRecord:
    """Freeze one attempt's tariff before its summary can be delayed or retried."""
    snapshot = snapshot if snapshot is not None else capture_pricing_snapshot()
    usd, eur = get_cached_cost_usd_eur(
        model=model_name,
        prompt_tokens=usage.prompt,
        completion_tokens=usage.completion,
        cached_tokens=usage.cached,
        cache_write_tokens=usage.cache_write,
        at=datetime.fromtimestamp(started_at, UTC),
        snapshot=snapshot,
    )
    return LLMBillingRecord(
        model_name=model_name,
        started_at=started_at,
        tokens_in=usage.prompt,
        tokens_out=usage.completion,
        tokens_cache=usage.cached,
        tokens_cache_write=usage.cache_write,
        cost_usd=usd,
        cost_eur=eur,
        usd_to_eur_rate=get_cached_usd_eur_rate(snapshot),
    )


class TokenCaptureHandler(BaseCallbackHandler):
    """Accumulate token usage across every LLM call of one invocation.

    Attach a fresh instance per logical operation (the counters accumulate
    across retries too — retried attempts are paid, so they belong in the
    spend). A lock also protects sync callbacks dispatched by LangChain's
    executor when several provider attempts complete concurrently.
    """

    def __init__(self, model_name: str | None = None) -> None:
        super().__init__()
        self.tokens_in: int = 0
        self.tokens_out: int = 0
        self.tokens_cache: int = 0
        self.tokens_cache_write: int = 0
        self._default_model = model_name
        self._starts: dict[UUID, tuple[float, str | None, PricingCacheData]] = {}
        self._recorded_runs: set[UUID] = set()
        self._calls: list[
            tuple[
                UsageTokens,
                float,
                str | None,
                PricingCacheData,
                Literal["success", "error"],
                str | None,
            ]
        ] = []
        self._billing_records: tuple[LLMBillingRecord, ...] = ()
        self._claimed_records = 0
        self._lock = RLock()

    def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], *, run_id: UUID, **kwargs: Any
    ) -> None:
        """Capture the request's model and start before provider execution."""
        with self._lock:
            self._starts[run_id] = (
                time(),
                requested_model(kwargs.get("invocation_params")) or self._default_model,
                capture_pricing_snapshot(),
            )

    def on_chat_model_start(
        self, serialized: dict[str, Any], messages: list[list[Any]], *, run_id: UUID, **kwargs: Any
    ) -> None:
        self.on_llm_start(serialized, [], run_id=run_id, **kwargs)

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        with self._lock:
            partial = kwargs.get("response")
            if isinstance(partial, LLMResult):
                self._append_usage(
                    partial, run_id, status="error", failure_kind=classify_llm_error(error)
                )
            self._starts.pop(run_id, None)

    def get_billing_records(self, fallback_model: str) -> tuple[LLMBillingRecord, ...]:
        """Price every captured attempt once, preserving its own model and hour."""
        with self._lock:
            for usage, started_at, model, snapshot, status, failure_kind in self._calls[
                len(self._billing_records) :
            ]:
                self._billing_records += (
                    priced_call(
                        usage, model or fallback_model, started_at, snapshot=snapshot
                    ).model_copy(update={"status": status, "failure_kind": failure_kind}),
                )
            return self._billing_records

    @property
    def has_usage(self) -> bool:
        """True when the provider reported any token usage at all."""
        return bool(self.tokens_in or self.tokens_out or self.tokens_cache)

    def claim_billing_records(self, fallback_model: str) -> tuple[LLMBillingRecord, ...]:
        """Claim known paid attempts once, including partial failed operations."""
        with self._lock:
            records = self.get_billing_records(fallback_model)
            pending = records[self._claimed_records :]
            self._claimed_records = len(records)
            return pending

    def ensure_response_record(
        self,
        response: Any,
        *,
        model_name: str,
        started_at: float,
        snapshot: PricingCacheData,
    ) -> None:
        """Seed a direct reply only when callbacks reported no paid usage.

        Some clients (and test fakes) return an AIMessage without firing the
        attached callbacks. Never add its reading on top of callback usage.
        """
        with self._lock:
            if self._calls:
                return
            usage = tokens_from_response(response)
            if usage.is_empty:
                return
            self.tokens_in += usage.prompt
            self.tokens_out += usage.completion
            self.tokens_cache += usage.cached
            self.tokens_cache_write += usage.cache_write
            self._calls.append(
                (
                    usage,
                    started_at,
                    model_name_of_response(response) or model_name,
                    snapshot,
                    "success",
                    None,
                )
            )
            self.get_billing_records(model_name)

    @property
    def accounting_handled(self) -> bool:
        """A persistence attempt already owns these paid records."""
        return bool(self._claimed_records)

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Extract token usage from the LLM response (both known surfaces)."""
        with self._lock:
            self._append_usage(response, kwargs.get("run_id"))

    def _append_usage(
        self,
        response: LLMResult,
        run_id: UUID | None,
        *,
        status: Literal["success", "error"] = "success",
        failure_kind: str | None = None,
    ) -> None:
        # Fallback surface, reached only when NO generation carried
        # usage_metadata — the two surfaces can never double-count.
        if run_id is not None:
            if run_id in self._recorded_runs:
                return
            self._recorded_runs.add(run_id)
        started_at, requested, snapshot = (
            self._starts.pop(run_id, (time(), self._default_model, capture_pricing_snapshot()))
            if run_id is not None
            else (time(), self._default_model, capture_pricing_snapshot())
        )
        usage = _generation_usage(response) or _aggregate_usage(response)
        self.tokens_in += usage.prompt
        self.tokens_out += usage.completion
        self.tokens_cache += usage.cached
        self.tokens_cache_write += usage.cache_write
        if not usage.is_empty:
            reported = _response_model(response)
            self._calls.append(
                (usage, started_at, reported or requested, snapshot, status, failure_kind)
            )
            if reported or requested:
                self.get_billing_records(self._default_model or "unknown")
