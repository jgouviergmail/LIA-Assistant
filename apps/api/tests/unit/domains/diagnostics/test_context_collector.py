"""The evidence pack is fetched at diagnosis time, bounded, fail-open, PII-free.

What the diagnostician received until 2026-09-05 was seven fields. What it needed
was in Prometheus (two failed operations out of eight, both `http_500`) and in
Loki (every failure on `rag_injection_failed`). The collector fetches exactly what
the incident's recipe declares — never a free-form query — and every source
degrades to `unavailable` on its own: a Loki outage costs a diagnosis its log
excerpt, never the diagnosis (ADR-247: telemetry reading never raises).
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.constants import (
    DIAGNOSTICS_CONTEXT_FIELD_MAX_CHARS,
    DIAGNOSTICS_CONTEXT_LOG_LINES,
    DIAGNOSTICS_CONTEXT_LOG_SAMPLES,
    DIAGNOSTICS_CONTEXT_MAX_SERIES,
    DIAGNOSTICS_CONTEXT_TOP_COUNTS,
)
from src.domains.diagnostics import context_collector as collector_module
from src.domains.diagnostics.context_collector import collect_diagnosis_context
from src.domains.diagnostics.evidence_recipes import EVIDENCE_RECIPES
from src.infrastructure.telemetry.models import LokiLine, LokiResult, PromResult, PromSample

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 5, 6, 0, tzinfo=UTC)


def _incident(correlation_key: str = "EmbeddingOperationsFailing") -> Any:
    return SimpleNamespace(correlation_key=correlation_key, alertname=None)


def _sample(value: float, **labels: str) -> PromSample:
    return PromSample(metric=labels, value=value, ts=_NOW)


def _line(payload: dict[str, object] | None, *, level: str = "error", raw: str = "") -> LokiLine:
    return LokiLine(ts=_NOW, container="lia-api-prod", level=level, payload=payload, raw=raw)


def _prom(
    result_by_query: dict[str, PromResult] | None = None, *, default: PromResult | None = None
):
    client = MagicMock()

    async def instant_query(promql: str) -> PromResult:
        for needle, result in (result_by_query or {}).items():
            if needle in promql:
                return result
        return default or PromResult(status="ok", samples=[])

    client.instant_query = AsyncMock(side_effect=instant_query)
    return client


def _loki(result: LokiResult) -> MagicMock:
    client = MagicMock()
    client.query_range = AsyncMock(return_value=result)
    return client


class TestARecipeDrivesWhatIsFetched:
    async def test_every_declared_query_is_rendered_with_the_recipe_window(self) -> None:
        recipe = EVIDENCE_RECIPES["EmbeddingOperationsFailing"]
        prom = _prom()
        loki = _loki(LokiResult(status="ok", lines=[]))

        context = await collect_diagnosis_context(_incident(), prom_client=prom, loki_client=loki)

        assert context["recipe"] == "EmbeddingOperationsFailing"
        assert context["window_minutes"] == recipe.window_minutes
        rendered = [call.args[0] for call in prom.instant_query.await_args_list]
        assert len(rendered) == len(recipe.prom_queries)
        assert all(f"[{recipe.window_minutes}m]" in promql for promql in rendered)
        assert [m["query_id"] for m in context["metrics"]] == list(recipe.prom_queries)

    async def test_series_carry_labels_and_exact_values(self) -> None:
        prom = _prom(
            {
                "embedding_call_outcomes_total[": PromResult(
                    status="ok",
                    samples=[
                        _sample(2.0338, outcome="failed"),
                        _sample(6.1017, outcome="succeeded"),
                    ],
                )
            }
        )
        context = await collect_diagnosis_context(
            _incident(), prom_client=prom, loki_client=_loki(LokiResult(status="ok"))
        )

        outcomes = next(
            m for m in context["metrics"] if m["query_id"] == "embedding_outcomes_by_result"
        )
        assert outcomes["status"] == "ok"
        assert outcomes["title"] == "Embedding operations by outcome"
        assert outcomes["unit"] == "count", "a value without its unit cannot be read"
        assert outcomes["series"] == [
            {"labels": {"outcome": "failed"}, "value": 2.0338},
            {"labels": {"outcome": "succeeded"}, "value": 6.1017},
        ]

    async def test_the_loki_query_targets_the_recipe_service_and_window(self) -> None:
        loki = _loki(LokiResult(status="ok", lines=[]))
        await collect_diagnosis_context(_incident(), prom_client=_prom(), loki_client=loki)

        kwargs = loki.query_range.await_args.kwargs
        logql = loki.query_range.await_args.args[0]
        assert logql.startswith('{service="api"')
        assert kwargs["limit"] == DIAGNOSTICS_CONTEXT_LOG_LINES
        window = kwargs["end"] - kwargs["start"]
        assert (
            window.total_seconds()
            == EVIDENCE_RECIPES["EmbeddingOperationsFailing"].window_minutes * 60
        )

    async def test_a_recipe_without_logs_skips_loki_entirely(self) -> None:
        loki = _loki(LokiResult(status="ok"))
        context = await collect_diagnosis_context(
            _incident("DiskSpaceCritical"), prom_client=_prom(), loki_client=loki
        )
        assert context["logs"] == {"status": "skipped"}
        loki.query_range.assert_not_awaited()

    async def test_an_unknown_key_yields_the_runtime_block_alone(self) -> None:
        prom = _prom()
        loki = _loki(LokiResult(status="ok"))
        context = await collect_diagnosis_context(
            _incident("SomethingNobodyDeclared"), prom_client=prom, loki_client=loki
        )
        assert context["recipe"] is None
        assert context["metrics"] == []
        assert context["logs"] == {"status": "skipped"}
        assert "runtime" in context
        prom.instant_query.assert_not_awaited()
        loki.query_range.assert_not_awaited()


class TestTheRuntimeBlockAnswersRecentChanges:
    async def test_version_commit_and_uptime_are_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(collector_module.settings, "app_version", "1.42.0")
        monkeypatch.setattr(
            collector_module.settings, "git_commit_sha", "d1bc4743f400a68be70851891d32c80df96d38c9"
        )
        context = await collect_diagnosis_context(
            _incident("DiskSpaceCritical"),
            prom_client=_prom(),
            loki_client=_loki(LokiResult(status="ok")),
        )
        runtime = context["runtime"]
        assert runtime["version"] == "1.42.0"
        assert runtime["commit"] == "d1bc4743f400", "a short sha is enough to name a build"
        assert isinstance(runtime["uptime_seconds"], int) and runtime["uptime_seconds"] >= 0


class TestLogsAreCountedThenSampled:
    def _lines(self) -> list[LokiLine]:
        lines = [
            _line(
                {
                    "event": "gemini_embedding_failed",
                    "error": "Error embedding content: 500 INTERNAL. {'error': {'code': 500}}",
                }
            )
            for _ in range(8)
        ]
        lines += [
            _line(
                {
                    "event": "rag_injection_failed",
                    "error": "Max retries (2) exceeded",
                    "run_id": "abc",
                },
                level="warning",
            )
            for _ in range(4)
        ]
        lines.append(
            _line({"event": "retry_attempt", "error": "x"}, level="warning")
        )  # not in recipe
        lines.append(
            _line({"event": "gemini_embedding_failed", "error": "x"}, level="info")
        )  # level not kept
        return lines

    async def test_only_recipe_events_at_recipe_levels_are_kept_and_counted(self) -> None:
        context = await collect_diagnosis_context(
            _incident(),
            prom_client=_prom(),
            loki_client=_loki(LokiResult(status="ok", lines=self._lines())),
        )
        logs = context["logs"]
        assert logs["status"] == "ok"
        assert logs["lines_read"] == 14
        assert logs["lines_kept"] == 12
        assert logs["counts"][0] == {
            "event": "gemini_embedding_failed",
            "level": "error",
            "head": "Error embedding content: 500 INTERNAL. {'error': {'code': 500}}",
            "count": 8,
        }
        assert logs["counts"][1]["event"] == "rag_injection_failed"
        assert logs["counts"][1]["count"] == 4

    async def test_samples_are_capped_and_allowlisted(self) -> None:
        context = await collect_diagnosis_context(
            _incident(),
            prom_client=_prom(),
            loki_client=_loki(LokiResult(status="ok", lines=self._lines())),
        )
        samples = context["logs"]["samples"]
        assert len(samples) == DIAGNOSTICS_CONTEXT_LOG_SAMPLES
        for sample in samples:
            assert set(sample) <= {
                "ts",
                "level",
                "event",
                "error",
                "last_error",
                "error_type",
                "reason",
                "operation",
                "attempt",
                "max_retries",
                "status_code",
                "run_id",
                "logger",
            }
            assert "ts" in sample and "event" in sample

    async def test_counts_are_capped_to_the_top_n(self) -> None:
        lines = [
            _line({"event": "gemini_embedding_failed", "error": f"variant {i}"})
            for i in range(DIAGNOSTICS_CONTEXT_TOP_COUNTS + 7)
        ]
        context = await collect_diagnosis_context(
            _incident(),
            prom_client=_prom(),
            loki_client=_loki(LokiResult(status="ok", lines=lines)),
        )
        assert len(context["logs"]["counts"]) == DIAGNOSTICS_CONTEXT_TOP_COUNTS
        assert context["logs"]["counts_truncated"] is True

    async def test_a_non_structlog_service_keeps_raw_line_heads(self) -> None:
        lines = [
            _line(None, level="", raw="pg_dump: error: connection to server failed")
            for _ in range(3)
        ]
        context = await collect_diagnosis_context(
            _incident("BackupFailed"),
            prom_client=_prom(),
            loki_client=_loki(LokiResult(status="ok", lines=lines)),
        )
        logs = context["logs"]
        assert logs["status"] == "ok"
        assert logs["lines_kept"] == 3
        assert logs["counts"][0]["head"].startswith("pg_dump: error")
        assert logs["counts"][0]["event"] == ""


class TestNothingPersonalLeavesTheCollector:
    async def test_emails_and_url_secrets_are_pseudonymised(self) -> None:
        lines = [
            _line(
                {
                    "event": "gemini_embedding_failed",
                    "error": "refused for alice.martin@example.com at https://x.test/cb?token=SECRET123&code=abc",
                    "user_email": "alice.martin@example.com",
                    "content": "the user's private message",
                }
            )
        ]
        context = await collect_diagnosis_context(
            _incident(),
            prom_client=_prom(),
            loki_client=_loki(LokiResult(status="ok", lines=lines)),
        )
        flat = repr(context)
        assert "alice.martin@example.com" not in flat
        assert "SECRET123" not in flat
        assert "private message" not in flat, "a field outside the allowlist never travels"
        assert "user_email" not in flat

    async def test_every_kept_field_is_bounded(self) -> None:
        lines = [_line({"event": "gemini_embedding_failed", "error": "x" * 5000})]
        context = await collect_diagnosis_context(
            _incident(),
            prom_client=_prom(),
            loki_client=_loki(LokiResult(status="ok", lines=lines)),
        )
        assert len(context["logs"]["samples"][0]["error"]) <= DIAGNOSTICS_CONTEXT_FIELD_MAX_CHARS


class TestBounds:
    async def test_series_beyond_the_cap_are_truncated_and_said_so(self) -> None:
        samples = [
            _sample(float(i), reason=f"r{i}") for i in range(DIAGNOSTICS_CONTEXT_MAX_SERIES + 5)
        ]
        prom = _prom(default=PromResult(status="ok", samples=samples))
        context = await collect_diagnosis_context(
            _incident("DiskSpaceCritical"),
            prom_client=prom,
            loki_client=_loki(LokiResult(status="ok")),
        )
        metric = context["metrics"][0]
        assert len(metric["series"]) == DIAGNOSTICS_CONTEXT_MAX_SERIES
        assert metric["truncated"] is True


class TestFailOpen:
    async def test_loki_unavailable_keeps_the_metrics(self) -> None:
        context = await collect_diagnosis_context(
            _incident(),
            prom_client=_prom(),
            loki_client=_loki(LokiResult(status="unavailable", error="transport:ConnectError")),
        )
        assert context["logs"]["status"] == "unavailable"
        assert context["logs"]["error"] == "transport:ConnectError"
        assert len(context["metrics"]) == len(
            EVIDENCE_RECIPES["EmbeddingOperationsFailing"].prom_queries
        )

    async def test_a_prometheus_query_unavailable_is_reported_per_query(self) -> None:
        prom = _prom(default=PromResult(status="unavailable", error="circuit_open"))
        context = await collect_diagnosis_context(
            _incident("DiskSpaceCritical"),
            prom_client=prom,
            loki_client=_loki(LokiResult(status="ok")),
        )
        assert context["metrics"][0] == {
            "query_id": "disk_usage_percent",
            "title": "Host disk usage",
            "unit": "percent",
            "status": "unavailable",
            "error": "circuit_open",
            "series": [],
            "truncated": False,
        }

    async def test_an_unexpected_exception_in_a_client_never_escapes(self) -> None:
        prom = MagicMock()
        prom.instant_query = AsyncMock(side_effect=RuntimeError("boom"))
        loki = MagicMock()
        loki.query_range = AsyncMock(side_effect=RuntimeError("boom"))

        context = await collect_diagnosis_context(_incident(), prom_client=prom, loki_client=loki)

        assert all(m["status"] == "unavailable" for m in context["metrics"])
        assert context["logs"]["status"] == "unavailable"
        assert "runtime" in context

    async def test_sources_are_counted_by_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[tuple[str, str]] = []
        metric = MagicMock()
        metric.labels.side_effect = lambda **kw: type(
            "M", (), {"inc": lambda _s, *a: seen.append((kw["source"], kw["status"]))}
        )()
        monkeypatch.setattr(collector_module, "diagnostics_context_sources_total", metric)

        await collect_diagnosis_context(
            _incident("DiskSpaceCritical"),
            prom_client=_prom(default=PromResult(status="unavailable", error="http_503")),
            loki_client=_loki(LokiResult(status="ok")),
        )
        assert ("prometheus", "unavailable") in seen
