"""Tests for heartbeat interest enrichment (ADR-135).

Bench 2026-07-18 proved the chain end-to-end (Perplexity -> "The Backrooms
(Kane Parsons)" -> concrete notification 2/2). These tests pin the wiring:
facts are fetched only for interest-centered heartbeats, links are appended,
tokens are accounted, and every failure path falls open to the plain draft.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask


def _target(topic: str | None) -> MagicMock:
    target = MagicMock()
    target.decision.message_draft = "vague draft"
    target.decision.reason = "r"
    target.decision.priority = "low"
    target.decision.sources_used = ["USER_INTERESTS"]
    target.decision.interest_topic = topic
    target.decision_tokens_in = 10
    target.decision_tokens_out = 5
    target.decision_tokens_cache = 0
    return target


@pytest.mark.unit
class TestEnrichment:
    async def test_facts_injected_and_links_appended(self) -> None:
        task = HeartbeatProactiveTask()
        with (
            patch(
                "src.domains.heartbeat.proactive_task.generate_heartbeat_message",
                new=AsyncMock(return_value=("msg with The Backrooms", 20, 10, 0)),
            ) as gen_msg,
            patch.object(
                task,
                "_fetch_interest_facts",
                new=AsyncMock(return_value=("FACTS...", ["https://a24.com/x"], 7, 3)),
            ),
            patch.object(task, "_get_user_personality", new=AsyncMock(return_value=None)),
        ):
            result = await task.generate_content(uuid.uuid4(), _target("Cinéma A24"), "fr")

        assert result.success
        assert "a24.com" in (result.content or "")
        assert result.metadata["interest_topic"] == "Cinéma A24"
        assert gen_msg.await_args.kwargs["facts_block"] == "FACTS..."
        # decision + message + enrichment tokens all accounted
        assert result.tokens_in == 10 + 20 + 7
        assert result.tokens_out == 5 + 10 + 3

    async def test_enrichment_failure_falls_open(self) -> None:
        task = HeartbeatProactiveTask()
        with (
            patch(
                "src.domains.heartbeat.proactive_task.generate_heartbeat_message",
                new=AsyncMock(return_value=("plain msg", 20, 10, 0)),
            ) as gen_msg,
            patch.object(task, "_fetch_interest_facts", new=AsyncMock(return_value=None)),
            patch.object(task, "_get_user_personality", new=AsyncMock(return_value=None)),
        ):
            result = await task.generate_content(uuid.uuid4(), _target("Cinéma A24"), "fr")

        assert result.success
        assert result.content == "plain msg"
        assert gen_msg.await_args.kwargs["facts_block"] is None

    async def test_no_topic_means_no_enrichment_call(self) -> None:
        task = HeartbeatProactiveTask()
        with (
            patch(
                "src.domains.heartbeat.proactive_task.generate_heartbeat_message",
                new=AsyncMock(return_value=("plain msg", 20, 10, 0)),
            ),
            patch.object(task, "_fetch_interest_facts", new=AsyncMock()) as fetch,
            patch.object(task, "_get_user_personality", new=AsyncMock(return_value=None)),
        ):
            result = await task.generate_content(uuid.uuid4(), _target(None), "fr")

        fetch.assert_not_awaited()
        assert result.metadata["interest_topic"] is None

    async def test_enrichment_reuses_recent_embeddings_for_dedup(self) -> None:
        """Symmetry with the interest flow: fetched content is deduped against
        recent notifications for the same interest (ADR-135)."""
        task = HeartbeatProactiveTask()
        interest = MagicMock()
        interest.id = uuid.uuid4()
        interest.category = "entertainment"
        embeddings = [[0.1, 0.2], [0.3, 0.4]]

        generator = MagicMock()
        generator.generate = AsyncMock(
            return_value=MagicMock(
                success=True,
                content_result=MagicMock(
                    content="facts", citations=[], tokens_in=1, tokens_out=1, source="perplexity"
                ),
            )
        )
        generator.close = AsyncMock()

        with (
            patch(
                "src.domains.interests.services.content_sources.InterestContentGenerator",
                return_value=generator,
            ),
            patch.object(
                task,
                "_resolve_interest_for_enrichment",
                new=AsyncMock(return_value=(interest.id, "entertainment", embeddings)),
            ),
        ):
            result = await task._fetch_interest_facts(uuid.uuid4(), "Cinéma A24", "fr")

        assert result is not None
        context = generator.generate.await_args[0][0]
        assert context.recent_notification_embeddings == embeddings
        assert context.category == "entertainment"

    async def test_facts_without_citations_appends_no_links(self) -> None:
        task = HeartbeatProactiveTask()
        with (
            patch(
                "src.domains.heartbeat.proactive_task.generate_heartbeat_message",
                new=AsyncMock(return_value=("msg", 20, 10, 0)),
            ),
            patch.object(
                task,
                "_fetch_interest_facts",
                new=AsyncMock(return_value=("FACTS...", [], 7, 3)),
            ),
            patch.object(task, "_get_user_personality", new=AsyncMock(return_value=None)),
        ):
            result = await task.generate_content(uuid.uuid4(), _target("Cinéma A24"), "fr")

        assert result.content == "msg"


@pytest.mark.unit
class TestEnrichmentMetrics:
    """Observability parity with ADR-131: the fail-open rate must be visible."""

    def test_metric_exists_with_outcome_label(self) -> None:
        from src.infrastructure.observability.metrics_registry import (
            heartbeat_enrichment_total,
        )

        # Counter is labelled by outcome so the fail-open rate is measurable.
        heartbeat_enrichment_total.labels(outcome="success")
        heartbeat_enrichment_total.labels(outcome="empty")
        heartbeat_enrichment_total.labels(outcome="error")
        heartbeat_enrichment_total.labels(outcome="disabled")
