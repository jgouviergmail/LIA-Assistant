"""Absence-only selection saves extraction without suppressing memory retrieval."""

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from src.core.context import current_tracker
from src.domains.agents.services.analysis import jev_memory_presence as module
from src.domains.agents.services.analysis.memory_resolver import MemoryResolver, _ReferenceList
from src.domains.agents.services.memory_reference_resolution_service import ResolvedReferences
from src.domains.chat.service import TrackingContext
from src.domains.llm.pricing_service import ModelPrice
from src.domains.llm_config.jev_registry import JEV_USAGES, JevUsage
from src.domains.llm_config.jev_settings import DecisionConfiguration, JevSnapshot, read_flags
from src.domains.system_settings.models import SystemSettingKey
from src.domains.system_settings.registry import SETTING_SPECS
from src.infrastructure.llm import jev_runtime
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.typesafe_client import ChoiceAnswer

pytestmark = pytest.mark.unit


def answer(choice: str, confidence: float) -> ChoiceAnswer:
    return ChoiceAnswer(
        type="choice",
        choice=choice,
        confidence=confidence,
        probabilities={
            "absent": 0.999 if choice == "absent" else 0.001,
            "preserve": 0.001 if choice == "absent" else 0.999,
        },
    )


async def test_unbound_caller_never_calls_native_or_skips_extractor() -> None:
    token = current_tracker.set(None)
    try:
        with patch.object(module, "choose_with_jev", AsyncMock()) as native:
            assert not await module.choose_no_memory_references("My emails")
        native.assert_not_awaited()
    finally:
        current_tracker.reset(token)


@pytest.mark.parametrize(
    "outcome,choice,confidence,expected",
    [
        ("success", "absent", 0.99, True),
        ("success", "absent", 0.989999, False),
        ("success", "preserve", 1.0, False),
        ("success", "preserve", 0.989999, False),
        ("disabled", "absent", 1.0, False),
        ("timeout", "absent", 1.0, False),
        ("invalid_response", "absent", 1.0, False),
        ("unavailable", "absent", 1.0, False),
    ],
)
async def test_only_confident_successful_absence_skips(
    outcome: str,
    choice: str,
    confidence: float,
    expected: bool,
) -> None:
    tracker = TrackingContext("memory-presence", uuid4(), "chat", None, auto_commit=False)
    token = current_tracker.set(tracker)
    query = "My emails, then call my sister " + "x" * 1200
    try:
        with (
            patch.object(
                module,
                "choose_with_jev",
                AsyncMock(
                    return_value=DecisionAttempt(
                        outcome=outcome,
                        answer=answer(choice, confidence),
                    )
                ),
            ) as native,
            patch.object(module, "record_action", AsyncMock()) as debug,
        ):
            assert await module.choose_no_memory_references(query) is expected
        assert native.await_args.kwargs["state"] == {
            "query": query,
            "account_owner_identity_known": True,
        }
        assert native.await_args.kwargs["usage"] == JevUsage.MEMORY_REFERENCE_PRESENCE
        assert native.await_args.kwargs["user_id"] == tracker.user_id
        assert native.await_args.kwargs["run_id"] == tracker.run_id
        assert debug.await_args.kwargs["action"] == ("selected" if expected else "fallback")
        if outcome == "success":
            expected_outcome = (
                "no_references"
                if expected
                else (
                    "references_preserved"
                    if choice == "preserve" and confidence >= 0.99
                    else "uncertain"
                )
            )
        else:
            expected_outcome = outcome
        assert debug.await_args.kwargs["outcome"] == expected_outcome
    finally:
        current_tracker.reset(token)


async def test_error_falls_back_but_cancellation_propagates() -> None:
    tracker = TrackingContext("memory-presence", uuid4(), "chat", None, auto_commit=False)
    token = current_tracker.set(tracker)
    try:
        with patch.object(module, "choose_with_jev", AsyncMock(side_effect=OSError())):
            assert not await module.choose_no_memory_references("My calendar")
        with patch.object(
            module, "choose_with_jev", AsyncMock(side_effect=asyncio.CancelledError())
        ):
            with pytest.raises(asyncio.CancelledError):
                await module.choose_no_memory_references("My calendar")
    finally:
        current_tracker.reset(token)


@pytest.mark.parametrize("skip", [True, False])
async def test_gate_preserves_broad_facts_and_fallback_identity_path(skip: bool) -> None:
    from src.domains.agents.services.analysis import memory_resolver as resolver_module

    resolver = MemoryResolver()
    with (
        patch.object(resolver_module, "choose_no_memory_references", AsyncMock(return_value=skip)),
        patch.object(resolver_module, "get_llm") as factory,
        patch.object(
            resolver_module,
            "get_structured_output",
            AsyncMock(
                return_value=_ReferenceList(references=["my sister"]),
            ),
        ) as extraction,
        patch.object(resolver, "_retrieve_memory_facts", AsyncMock(return_value=["broad fact"])),
        patch.object(
            resolver, "_search_memories_targeted", AsyncMock(return_value=["target fact"])
        ) as search,
        patch.object(
            resolver, "_resolve_memory_references", AsyncMock(return_value=None)
        ) as resolve,
    ):
        result = await resolver.retrieve_and_resolve("my sister", str(uuid4()), {})
    assert result.facts == ["broad fact"]
    assert result.references == ([] if skip else ["my sister"])
    if skip:
        factory.assert_not_called()
        extraction.assert_not_awaited()
        search.assert_not_awaited()
        resolve.assert_not_awaited()
    else:
        extraction.assert_awaited_once()
        search.assert_awaited_once()
        resolve.assert_awaited_once()


async def test_new_usage_is_default_off_with_global_and_existing_usage_on() -> None:
    spec = JEV_USAGES[JevUsage.MEMORY_REFERENCE_PRESENCE]
    assert SETTING_SPECS[spec.setting_key].default is False
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(
        all=lambda: [
            SimpleNamespace(key=SystemSettingKey.JEV_ENABLED, value="true"),
            SimpleNamespace(key=SystemSettingKey.JEV_MEETING_TEMPLATE_ENABLED, value="true"),
        ]
    )
    flags = await read_flags(db)
    assert flags["memory_reference_presence"] is False
    assert flags["global"] is True and flags["meeting_template"] is True


async def test_confident_preserve_keeps_brother_fact_and_identity_resolution() -> None:
    from src.domains.agents.services.analysis import memory_resolver as resolver_module

    query = "qui est mon frère ?"
    fact = "Mon frère s'appelle Julien Exemple."
    tracker = TrackingContext("brother-preserved", uuid4(), "chat", None, auto_commit=False)
    resolved = ResolvedReferences(
        original_query=query,
        enriched_query="qui est Julien Exemple ?",
        mappings={"mon frère": "Julien Exemple"},
    )
    resolver = MemoryResolver()
    token = current_tracker.set(tracker)
    config = {}
    try:
        with (
            patch.object(
                module,
                "choose_with_jev",
                AsyncMock(
                    return_value=DecisionAttempt(outcome="success", answer=answer("preserve", 0.99))
                ),
            ),
            patch.object(module, "record_action", AsyncMock()) as debug,
            patch.object(resolver_module, "get_llm"),
            patch.object(
                resolver_module,
                "get_structured_output",
                AsyncMock(return_value=_ReferenceList(references=["mon frère"])),
            ) as extraction,
            patch.object(resolver, "_retrieve_memory_facts", AsyncMock(return_value=[fact])),
            patch.object(
                resolver, "_search_memories_targeted", AsyncMock(return_value=[fact])
            ) as search,
            patch.object(
                resolver, "_resolve_memory_references", AsyncMock(return_value=resolved)
            ) as resolution,
        ):
            result = await resolver.retrieve_and_resolve(query, str(tracker.user_id), config)
        assert result.facts == [fact]
        assert result.references == ["mon frère"]
        assert result.resolved is resolved
        extraction.assert_awaited_once()
        search.assert_awaited_once_with(["mon frère"], str(tracker.user_id), config)
        resolution.assert_awaited_once_with(query, [fact], config)
        assert debug.await_args.kwargs["outcome"] == "references_preserved"
        assert debug.await_args.kwargs["action"] == "fallback"
    finally:
        current_tracker.reset(token)


async def test_real_disabled_runtime_preserves_the_generative_extractor() -> None:
    from src.domains.agents.services.analysis import memory_resolver as resolver_module

    tracker = TrackingContext("memory-disabled", uuid4(), "chat", None, auto_commit=False)
    token = current_tracker.set(tracker)
    try:
        with (
            patch.object(
                jev_runtime,
                "load_jev_snapshot",
                AsyncMock(return_value=JevSnapshot(False, "disabled", None)),
            ),
            patch.object(jev_runtime, "enforce_usage_limit", AsyncMock()) as quota,
            patch.object(jev_runtime.httpx, "AsyncClient") as transport,
            patch.object(module, "record_action", AsyncMock()),
            patch.object(resolver_module, "get_llm") as factory,
            patch.object(
                resolver_module,
                "get_structured_output",
                AsyncMock(return_value=_ReferenceList(references=["my sister"])),
            ) as extraction,
        ):
            references = await MemoryResolver()._extract_references("Call my sister", {})
        assert references == ["my sister"]
        factory.assert_called_once()
        extraction.assert_awaited_once()
        quota.assert_not_awaited()
        transport.assert_not_called()
        assert tracker._node_records == []
    finally:
        current_tracker.reset(token)


@pytest.mark.parametrize("invalid", [False, True])
async def test_real_native_transport_charges_once_then_preserves_paid_failure_fallback(
    invalid: bool,
) -> None:
    tracker = TrackingContext("memory-native", uuid4(), "chat", None, auto_commit=False)
    config = DecisionConfiguration(
        "jev-1.13.0",
        2,
        SecretStr("synthetic-test-key"),
        ModelPrice(
            "jev-1.13.0",
            Decimal(".042"),
            None,
            Decimal(0),
            "per_1m_tokens",
            datetime.now(UTC),
        ),
    )
    calls = []

    def transport(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": config.model,
                "usage": {"input_tokens": 1000, "output_tokens": 41},
                "answers": {
                    "selection": {
                        "type": "choice",
                        "choice": "absent",
                        "confidence": 1.0,
                        "probabilities": {"absent": 1.0, "preserve": 0.1 if invalid else 0.0},
                    }
                },
            },
        )

    real_client = httpx.AsyncClient
    token = current_tracker.set(tracker)
    try:
        with (
            patch.object(
                jev_runtime,
                "load_jev_snapshot",
                AsyncMock(return_value=JevSnapshot(True, "ready", config)),
            ),
            patch.object(jev_runtime, "enforce_usage_limit", AsyncMock()),
            patch.object(jev_runtime, "begin_trace", AsyncMock(return_value=None)),
            patch.object(jev_runtime, "get_cached_usd_eur_rate", return_value=0.9),
            patch.object(
                jev_runtime.httpx,
                "AsyncClient",
                side_effect=lambda: real_client(transport=httpx.MockTransport(transport)),
            ),
            patch.object(module, "record_action", AsyncMock()) as debug,
        ):
            assert await module.choose_no_memory_references("My calendar") is not invalid
        assert len(calls) == 1
        assert len(tracker._node_records) == 1
        bill = tracker._node_records[0]
        assert float(bill.cost_usd) == pytest.approx(0.000042)
        assert bill.llm_type == "jev_memory_reference_presence"
        assert debug.await_args.kwargs["action"] == ("fallback" if invalid else "selected")
    finally:
        current_tracker.reset(token)
