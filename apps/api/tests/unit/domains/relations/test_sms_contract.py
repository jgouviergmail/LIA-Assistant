"""SMS-only relations, exact merged counts and existing scope inclusions."""

from datetime import UTC, datetime

from src.domains.relations.identity import IdentityResolver
from src.domains.relations.overview_scope import OverviewSection, RelationOverviewScope
from src.domains.relations.service import _bucketize
from src.domains.shared.aggregates import NameActivity


def test_sms_only_relation_joins_manual_alias_without_losing_exact_count():
    now = datetime.now(UTC)
    result = _bucketize(
        [],
        [],
        [],
        sms=[NameActivity("Papa", 137, now), NameActivity("Alice", 3, now)],
        resolver=IdentityResolver.from_pairs([("papa", "alice")]),
    )
    assert set(result) == {"alice"} and result["alice"].sms_count == 140
    assert result["alice"].last_interaction_at == now


def test_old_explicit_scope_never_silently_gains_sms():
    assert OverviewSection.SMS not in RelationOverviewScope.default().sections
    assert RelationOverviewScope.from_stored({"sections": []}).sections == []
    assert (
        OverviewSection.SMS
        not in RelationOverviewScope.from_stored({"sections": ["calls"]}).sections
    )


def test_sms_evidence_is_scoped_bounded_and_external():
    from uuid import uuid4

    from src.domains.relations.overview.blocks import local_blocks
    from src.domains.relations.schemas import IdentityConfidence, RelationDetail
    from src.domains.shared.relation_sms import PersonalSms

    detail = RelationDetail(
        display_name="Alice",
        identity_confidence=IdentityConfidence.EXACT,
        open_loops=[],
        recent_calls=[],
        memories=[],
        sms_available=True,
        sms_total=137,
        sms=[
            PersonalSms(
                id=uuid4(),
                sender="Alice",
                display_name="Alice",
                body="A" * 16000,
                received_at=datetime.now(UTC),
                date_kind="received",
            )
        ],
    )
    payload = local_blocks(detail, RelationOverviewScope(sections=["sms"]))
    assert payload["sms_total"] == 137
    assert payload["sms"][0]["trust"] == "external" and payload["sms"][0]["body_truncated"]
    assert len(payload["sms"][0]["body"]) <= 256
    assert "sms" not in local_blocks(detail, RelationOverviewScope(sections=[]))
    assert "sms" not in local_blocks(
        detail, RelationOverviewScope(sections=["sms"], directions=["sent"])
    )


def test_invalidated_sms_debrief_is_stale_without_automatic_absent_rebuild():
    from src.domains.relations.debrief.service import read_of
    from tests.unit.domains.relations.debrief.test_service_rules import _row

    row = _row(sections_used=["sms"], evidence_digest=None, body=None)
    result = read_of(row)
    assert result.status.value == "stale" and result.body is None and result.can_rebuild


async def test_paid_debrief_cannot_publish_when_sms_proof_refuses(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from src.core.exceptions import ResourceConflictError
    from src.core.llm_usage import LLMUsage
    from src.domains.relations.debrief.schemas import DebriefBody
    from src.domains.relations.debrief.service import RelationDebriefService

    service = RelationDebriefService(uuid4())
    service._track = AsyncMock()
    service._settle_failed = AsyncMock()
    service.read = AsyncMock(return_value="refused")
    service._settle_ready = AsyncMock(
        side_effect=ResourceConflictError("sms", detail={"error_code": "STALE_STATE"})
    )
    service._record_consultations = lambda *args: None
    evidence = SimpleNamespace(
        detail=SimpleNamespace(display_name="Alice", sms_proof=None),
        blocks={"sms": [{"body": "Bonjour"}]},
        unavailable=[],
    )
    monkeypatch.setattr(
        "src.domains.relations.debrief.service.build_overview_evidence",
        AsyncMock(return_value=evidence),
    )
    monkeypatch.setattr(
        "src.domains.relations.debrief.service.overview_payload", lambda _: evidence.blocks
    )
    monkeypatch.setattr("src.domains.relations.debrief.service.check_relation_sms", AsyncMock())
    body = DebriefBody(headline="Bonjour", where_we_stand="Un message")
    writer = AsyncMock(
        return_value=(body, LLMUsage(tokens_in=10, tokens_out=5, tokens_cache=0, cost_eur=0.001))
    )
    monkeypatch.setattr("src.domains.relations.debrief.service.write_debrief", writer)
    from src.domains.relations.debrief.service import _Previous

    result = await service._build_within(
        "test",
        author=None,
        name="Alice",
        key="alice",
        owner=uuid4(),
        scope=RelationOverviewScope(),
        language="fr",
        local_date=datetime.now(UTC).date(),
        previous=_Previous(state=None, digest=None, same_settings=False),
    )
    assert result == "refused"
    service._track.assert_awaited_once()
    service._settle_failed.assert_awaited_once()


async def test_explicit_sms_scope_reports_unavailability_without_an_empty_claim():
    from tests.unit.domains.relations.overview.test_evidence_parity import _run_tool

    output, _ = await _run_tool(scope=RelationOverviewScope(sections=[OverviewSection.SMS]))
    assert "sms" in output.structured_data["unavailable"]
    assert "sms" not in output.structured_data
