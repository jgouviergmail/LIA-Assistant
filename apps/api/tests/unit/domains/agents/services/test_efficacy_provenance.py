"""Recorded invocation parameters, never current defaults, identify experience provenance."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.sql import Select

from src.domains.conversations.models import ConversationMessage

pytestmark = pytest.mark.unit


def _invocation(**updates: object) -> dict[str, object]:
    return {
        "provider": "openai",
        "model_name": "model-a",
        "llm_type": "response",
        "temperature": 0.0,
        "top_p": None,
        "max_output_tokens": 2048,
        "reasoning_level": "low",
        "reasoning_budget_tokens": None,
        "params_digest": "a" * 64,
    } | updates


def test_provenance_uses_recorded_parameter_changes_without_defaults() -> None:
    from src.domains.agents.services.efficacy_provenance import fingerprint_invocations

    baseline = fingerprint_invocations([_invocation()])
    assert baseline is not None and len(baseline) == 64
    for field, value in (
        ("provider", "anthropic"),
        ("model_name", "model-b"),
        ("llm_type", "router"),
        ("temperature", None),
        ("top_p", 0.5),
        ("max_output_tokens", 4096),
        ("reasoning_level", "high"),
        ("reasoning_budget_tokens", 1024),
        ("params_digest", "b" * 64),
    ):
        assert fingerprint_invocations([_invocation(**{field: value})]) != baseline


def test_identical_retries_and_log_order_do_not_change_configuration_identity() -> None:
    from src.domains.agents.services.efficacy_provenance import fingerprint_invocations

    router = _invocation(llm_type="router")
    response = _invocation()
    assert fingerprint_invocations([response, router, response]) == fingerprint_invocations(
        [router, response]
    )


def test_absent_or_invalid_recorded_provenance_is_not_fabricated() -> None:
    from src.domains.agents.services.efficacy_provenance import fingerprint_invocations

    assert fingerprint_invocations([]) is None
    assert fingerprint_invocations([_invocation(temperature=float("nan"))]) is None
    assert fingerprint_invocations([_invocation(max_output_tokens=True)]) is None


def _message() -> tuple[UUID, ConversationMessage]:
    from src.domains.agents.analysis.efficacy_context import EfficacyAnalysis, EfficacyTurnContext
    from src.domains.conversations.models import ConversationMessage
    from src.domains.psyche.efficacy_contracts import EfficacyEpoch

    user_id = uuid4()
    now = datetime.now(UTC)
    context = EfficacyTurnContext(
        owner_id=user_id,
        run_id="run-1",
        epoch=EfficacyEpoch(state_id=uuid4(), generation=uuid4()),
        analysis=EfficacyAnalysis.model_validate({"domains": ["technical"]}),
        issued_at=now - timedelta(seconds=2),
    )
    row = ConversationMessage(
        id=uuid4(),
        conversation_id=uuid4(),
        role="assistant",
        hidden=False,
        content="Not read by provenance",
        created_at=now,
        message_metadata={
            "run_id": "run-1",
            "response_feedback": {"verdict": "thumbs_up"},
            "psyche_efficacy": {
                "version": 1,
                "context": context.model_dump(mode="json"),
                "observations": [],
            },
        },
    )
    return user_id, row


class _Mappings:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def mappings(self) -> list[dict[str, object]]:
        return self.rows


class _Session:
    def __init__(self, user_id: UUID, rows: list[dict[str, object]]) -> None:
        self.user_id = user_id
        self.rows = rows

    async def execute(self, statement: Select[tuple[object, ...]]) -> _Mappings:
        # The fake implements the real query's owner/run boundary, rather than
        # accepting arbitrary SQL and silently making an unscoped query pass.
        from sqlalchemy.dialects import postgresql

        compiled = statement.compile(dialect=postgresql.dialect())
        params = compiled.params
        if self.user_id not in params.values() or "run-1" not in params.values():
            return _Mappings([_invocation(model_name="foreign-owner")])
        return _Mappings(self.rows)

    async def flush(self) -> None:
        return None


def _mount_owned_message(
    monkeypatch: pytest.MonkeyPatch, user_id: UUID, row: ConversationMessage
) -> None:
    import src.domains.agents.services.efficacy_provenance as module

    async def lock(db: object, owner: object) -> None:
        return None

    async def owned(db: object, owner: UUID, message_id: UUID) -> ConversationMessage | None:
        return row if owner == user_id and message_id == row.id else None

    monkeypatch.setattr(module, "lock_feedback_owner", lock)
    monkeypatch.setattr(module, "get_assistant_message_for_user", owned)


@pytest.mark.asyncio
async def test_finalizer_stamps_new_json_preserving_existing_feedback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.agents.services.efficacy_provenance import (
        finalize_provenance,
        fingerprint_invocations,
    )

    user_id, row = _message()
    old = row.message_metadata
    _mount_owned_message(monkeypatch, user_id, row)
    assert await finalize_provenance(_Session(user_id, [_invocation()]), user_id, row.id)
    assert row.message_metadata is not old
    assert "config_fingerprint" not in old["psyche_efficacy"]
    assert row.message_metadata["response_feedback"] == {"verdict": "thumbs_up"}
    assert row.message_metadata["psyche_efficacy"]["config_fingerprint"] == fingerprint_invocations(
        [_invocation()]
    )


@pytest.mark.asyncio
async def test_finalized_configuration_is_immutable_for_late_feedback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.agents.services.efficacy_provenance import finalize_provenance

    user_id, row = _message()
    _mount_owned_message(monkeypatch, user_id, row)
    assert await finalize_provenance(_Session(user_id, [_invocation()]), user_id, row.id)
    first = row.message_metadata["psyche_efficacy"]["config_fingerprint"]
    assert await finalize_provenance(
        _Session(user_id, [_invocation(model_name="changed-later")]), user_id, row.id
    )
    assert row.message_metadata["psyche_efficacy"]["config_fingerprint"] == first


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid", ["foreign", "provisional", "hidden", "expired", "wrong_run", "absent_logs"]
)
async def test_noncanonical_or_unproven_episode_is_not_stamped(
    monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    from src.domains.agents.services.efficacy_provenance import finalize_provenance

    user_id, row = _message()
    _mount_owned_message(monkeypatch, user_id, row)
    if invalid == "provisional":
        row.message_metadata["provisional"] = True
    if invalid == "hidden":
        row.hidden = True
    if invalid == "wrong_run":
        row.message_metadata["run_id"] = "run-previous"
    if invalid == "expired":
        row.message_metadata["psyche_efficacy"]["context"]["issued_at"] = (
            datetime.now(UTC) - timedelta(days=2)
        ).isoformat()
    owner = uuid4() if invalid == "foreign" else user_id
    rows = [] if invalid == "absent_logs" else [_invocation()]
    assert not await finalize_provenance(_Session(user_id, rows), owner, row.id)
    assert "config_fingerprint" not in row.message_metadata["psyche_efficacy"]


def test_zero_explicit_reasoning_budget_is_preserved_in_provenance() -> None:
    from src.domains.agents.services.efficacy_provenance import fingerprint_invocations

    zero = fingerprint_invocations([_invocation(reasoning_budget_tokens=0)])
    assert zero is not None
    assert zero != fingerprint_invocations([_invocation(reasoning_budget_tokens=None)])


@pytest.mark.asyncio
async def test_late_finalizer_validates_context_at_canonical_terminal_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.agents.services.efficacy_provenance import finalize_provenance

    user_id, row = _message()
    row.created_at = datetime.now(UTC) - timedelta(days=30)
    row.message_metadata["psyche_efficacy"]["context"]["issued_at"] = (
        row.created_at - timedelta(seconds=2)
    ).isoformat()
    _mount_owned_message(monkeypatch, user_id, row)
    assert await finalize_provenance(_Session(user_id, [_invocation()]), user_id, row.id)


@pytest.mark.asyncio
async def test_collection_disabled_at_turn_start_cannot_be_enabled_retroactively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.agents.services.efficacy_provenance import finalize_provenance

    user_id, row = _message()
    row.message_metadata["psyche_efficacy"]["context"]["collection_enabled"] = False
    _mount_owned_message(monkeypatch, user_id, row)
    assert not await finalize_provenance(_Session(user_id, [_invocation()]), user_id, row.id)


@pytest.mark.parametrize("field", ["max_output_tokens", "reasoning_budget_tokens"])
def test_provider_sentinels_are_recorded_instead_of_mistaken_for_invalid_config(field: str) -> None:
    from src.domains.agents.services.efficacy_provenance import fingerprint_invocations

    sent = fingerprint_invocations([_invocation(**{field: -1})])
    assert sent is not None
    assert sent != fingerprint_invocations([_invocation(**{field: None})])
