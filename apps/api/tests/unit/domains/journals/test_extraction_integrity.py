"""The extractor cannot promote a lone signal or reinforce an unexposed rule."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.domains.journals import extraction_service as extraction
from src.domains.journals.prompt_builders import build_introspection_prompt

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture
def runtime(monkeypatch):
    owner, note_id = uuid4(), uuid4()
    note = SimpleNamespace(
        id=note_id,
        user_id=owner,
        title="Rule",
        content="WHEN checking DO verify.",
        theme="learnings",
        mood="reflective",
        confidence="medium",
        evidence_count=0,
        contradiction_count=0,
        injection_count=0,
        last_injected_at=None,
        created_at=datetime.now(UTC),
        search_hints=[],
        level="L1",
        revision=1,
    )
    user = SimpleNamespace(
        id=owner,
        journal_max_total_chars=40000,
        journal_max_entry_chars=2000,
        personality_id=None,
        journals_enabled=True,
    )
    db = MagicMock(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: user)))
    db.commit = AsyncMock()

    @asynccontextmanager
    async def context():
        yield db

    @asynccontextmanager
    async def savepoint():
        yield

    db.begin_nested = savepoint
    service = SimpleNamespace(
        repo=SimpleNamespace(
            get_recent_for_user=AsyncMock(return_value=[note]),
            get_by_id=AsyncMock(return_value=note),
            get_total_chars=AsyncMock(return_value=30),
        ),
        create_entry=AsyncMock(return_value=note),
        update_entry=AsyncMock(return_value=note),
        delete_entry=AsyncMock(),
    )
    monkeypatch.setattr("src.infrastructure.database.get_db_context", context)
    monkeypatch.setattr("src.domains.journals.service.JournalService", lambda _: service)
    monkeypatch.setattr(
        extraction,
        "settings",
        SimpleNamespace(
            journals_enabled=True,
            journal_extraction_enabled=True,
            journal_extraction_min_messages=1,
            journal_default_max_total_chars=40000,
        ),
    )
    for name in ("_maybe_build_health_context", "_maybe_build_inner_state_section"):
        monkeypatch.setattr(extraction, name, AsyncMock(return_value=""))
    consent = AsyncMock(return_value=4)
    enabled = AsyncMock(return_value=True)
    monkeypatch.setattr(extraction, "snapshot_extraction_consent", consent, raising=False)
    monkeypatch.setattr(extraction, "is_capability_enabled", enabled, raising=False)
    monkeypatch.setattr(extraction, "runtime_context_if_running", lambda: None, raising=False)
    monkeypatch.setattr(
        extraction, "get_llm_config_for_agent", lambda *_: SimpleNamespace(model="offline")
    )
    monkeypatch.setattr(extraction, "get_llm", lambda *_: SimpleNamespace(model_name="offline"))
    invoke = AsyncMock(return_value=AIMessage(content="[]"))
    monkeypatch.setattr(extraction, "invoke_with_instrumentation", invoke)
    monkeypatch.setattr(extraction, "_persist_journal_tokens", AsyncMock())
    monkeypatch.setattr(extraction, "_update_user_last_cost", AsyncMock())
    monkeypatch.setattr(extraction, "record_origin", AsyncMock())
    monkeypatch.setattr(extraction, "start_extraction_observation", MagicMock())
    embeddings = AsyncMock(return_value=(None, None))
    monkeypatch.setattr(
        "src.domains.journals.extraction_preparation.prepare_embeddings", embeddings
    )

    async def run(actions, *, previous=False, revisions=None, response_metadata=None, raw=None):
        import json

        invoke.return_value = AIMessage(
            content=raw if raw is not None else json.dumps(actions),
            response_metadata=response_metadata or {},
        )
        options = {}
        if revisions is not None:
            options["previous_turn_injected_revisions"] = revisions
        return await extraction.extract_journal_entry_background.__wrapped__(
            str(owner),
            [HumanMessage(content="Vérifie toujours les données avant de conclure.", id="turn-1")],
            str(uuid4()),
            parent_run_id="run-1",
            previous_turn_injected_ids=[str(note_id)] if previous else [],
            **options,
        )

    return SimpleNamespace(
        note=note,
        service=service,
        consent=consent,
        enabled=enabled,
        invoke=invoke,
        run=run,
        user=user,
        embeddings=embeddings,
    )


def create(level):
    return {
        "action": "create",
        "theme": "learnings",
        "title": "Observation",
        "content": "A bounded signal.",
        "level": level,
    }


@pytest.mark.parametrize("level", ["L2", "L3"])
async def test_extraction_does_not_create_synthesis_levels(runtime, level):
    assert await runtime.run([create(level)]) == 0
    runtime.service.create_entry.assert_not_awaited()


async def test_only_one_fresh_l0_is_kept(runtime):
    assert await runtime.run([create("L0") for _ in range(3)]) == 1
    runtime.service.create_entry.assert_awaited_once()


async def test_never_exposed_rule_does_not_receive_evidence(runtime):
    action = {"action": "update", "entry_id": str(runtime.note.id), "evidence_outcome": "evidence"}
    assert await runtime.run([action]) == 0
    runtime.service.update_entry.assert_not_awaited()


async def test_ambiguous_duplicate_uuid_is_not_applied(runtime):
    ident = str(runtime.note.id)
    actions = [
        {"action": "update", "entry_id": ident, "content": "A replacement"},
        {"action": "delete", "entry_id": ident},
    ]
    assert await runtime.run(actions) == 0
    runtime.service.update_entry.assert_not_awaited()
    runtime.service.delete_entry.assert_not_awaited()


async def test_create_with_existing_id_cannot_hide_a_duplicate_mutation(runtime):
    ident = str(runtime.note.id)
    actions = [create("L1") | {"entry_id": ident}, {"action": "delete", "entry_id": ident}]
    assert await runtime.run(actions) == 0
    runtime.service.create_entry.assert_not_awaited()
    runtime.service.delete_entry.assert_not_awaited()


async def test_l3_is_not_deleted_by_single_turn_extraction(runtime):
    runtime.note.level = "L3"
    assert await runtime.run([{"action": "delete", "entry_id": str(runtime.note.id)}]) == 0
    runtime.service.delete_entry.assert_not_awaited()


async def test_rule_promoted_during_call_is_not_deleted_by_extraction(runtime):
    from copy import copy

    runtime.service.repo.get_recent_for_user.return_value = [copy(runtime.note)]
    runtime.note.level = "L2"
    assert await runtime.run([{"action": "delete", "entry_id": str(runtime.note.id)}]) == 0
    runtime.service.delete_entry.assert_not_awaited()


async def test_rule_promoted_during_call_is_not_rewritten_by_extraction(runtime):
    from copy import copy

    runtime.service.repo.get_recent_for_user.return_value = [copy(runtime.note)]
    runtime.note.level = "L2"
    action = {"action": "update", "entry_id": str(runtime.note.id), "content": "Rewritten"}
    assert await runtime.run([action]) == 0
    runtime.service.update_entry.assert_not_awaited()


async def test_evidence_uses_the_exposed_revision_and_event(runtime):
    action = {"action": "update", "entry_id": str(runtime.note.id), "evidence_outcome": "evidence"}
    assert await runtime.run([action], previous=True, revisions={str(runtime.note.id): 1}) == 1
    args = runtime.service.update_entry.await_args.kwargs
    assert args["expected_revision"] == 1
    assert args["event_key"].startswith("journal-turn:") and len(args["event_key"]) == 77
    assert args["evidence_outcome"] == "evidence"


async def test_mutation_of_exposed_rule_outside_prefilter_keeps_its_snapshot_version(runtime):
    runtime.service.repo.get_recent_for_user.return_value = []
    action = {
        "action": "update",
        "entry_id": str(runtime.note.id),
        "content": "A precise correction",
    }
    assert await runtime.run([action], previous=True, revisions={str(runtime.note.id): 1}) == 1
    assert runtime.service.update_entry.await_args.kwargs["expected_revision"] == 1


async def test_revision_changed_since_exposure_cannot_be_reinforced(runtime):
    runtime.note.revision = 2
    action = {"action": "update", "entry_id": str(runtime.note.id), "evidence_outcome": "evidence"}
    assert await runtime.run([action], previous=True, revisions={str(runtime.note.id): 1}) == 0
    runtime.service.update_entry.assert_not_awaited()


async def test_missing_exposure_revision_cannot_be_reinforced(runtime):
    action = {"action": "update", "entry_id": str(runtime.note.id), "evidence_outcome": "evidence"}
    assert await runtime.run([action], previous=True) == 0
    runtime.service.update_entry.assert_not_awaited()


async def test_missing_user_consent_skips_the_paid_call(runtime):
    runtime.consent.return_value = None
    assert await runtime.run([create("L1")]) == 0
    runtime.invoke.assert_not_awaited()


async def test_settlement_locks_the_same_consent_revision_as_admission(runtime):
    assert await runtime.run([create("L1")]) == 1
    calls = runtime.consent.await_args_list
    assert all(call.kwargs["expected_revision"] == 4 for call in calls[1:])
    assert calls[-1].kwargs["lock"] is True


async def test_run_context_without_consent_snapshot_cannot_pay(runtime, monkeypatch):
    monkeypatch.setattr(
        extraction, "runtime_context_if_running", lambda: SimpleNamespace(extraction_revision=None)
    )
    assert await runtime.run([create("L1")]) == 0
    runtime.consent.assert_not_awaited()
    runtime.invoke.assert_not_awaited()


async def test_revoked_consent_after_call_prevents_settlement(runtime):
    runtime.consent.side_effect = [4, 4, 4, None]
    assert await runtime.run([create("L1")]) == 0
    runtime.invoke.assert_awaited_once()
    runtime.service.create_entry.assert_not_awaited()


async def test_revoked_operator_switch_prevents_settlement(runtime):
    runtime.enabled.side_effect = [True, True, True, False]
    assert await runtime.run([create("L1")]) == 0
    runtime.invoke.assert_awaited_once()
    runtime.service.create_entry.assert_not_awaited()


async def test_revoked_consent_during_context_prevents_paid_call(runtime):
    runtime.consent.side_effect = [4, None]
    assert await runtime.run([create("L1")]) == 0
    runtime.invoke.assert_not_awaited()


async def test_revoked_switch_during_context_prevents_paid_call(runtime):
    runtime.enabled.side_effect = [True, False]
    assert await runtime.run([create("L1")]) == 0
    runtime.invoke.assert_not_awaited()


async def test_operator_switch_off_skips_context_and_paid_call(runtime):
    runtime.enabled.return_value = False
    assert await runtime.run([create("L1")]) == 0
    runtime.consent.assert_not_awaited()
    runtime.invoke.assert_not_awaited()


async def test_embeddings_are_prepared_before_owner_lock_and_passed_to_write(runtime):
    async def prepare(*_):
        assert not any(call.kwargs.get("lock") for call in runtime.consent.await_args_list)
        return [0.25], [0.5]

    runtime.embeddings.side_effect = prepare
    assert await runtime.run([create("L1")]) == 1
    assert runtime.service.create_entry.await_args.kwargs["precomputed_embeddings"] == (
        [0.25],
        [0.5],
    )


async def test_scalar_only_update_needs_no_embedding_provider(runtime):
    action = {"action": "update", "entry_id": str(runtime.note.id), "mood": "curious"}
    assert await runtime.run([action]) == 1
    runtime.embeddings.assert_not_awaited()
    assert runtime.service.update_entry.await_args.kwargs["precomputed_embeddings"] == (None, None)


async def test_embedding_preparation_failure_keeps_other_actions_independent(runtime):
    runtime.embeddings.side_effect = [RuntimeError("synthetic preparation failure"), (None, None)]
    assert await runtime.run([create("L1"), create("L1")]) == 1
    runtime.service.create_entry.assert_awaited_once()


@pytest.mark.parametrize("field", ["title", "search_hints"])
async def test_embedding_payload_changed_without_rule_revision_is_not_written(runtime, field):
    async def prepare(*_):
        setattr(runtime.note, field, "Manual title" if field == "title" else ["manual hint"])
        return [0.25], [0.5]

    runtime.embeddings.side_effect = prepare
    action = {
        "action": "update",
        "entry_id": str(runtime.note.id),
        "content": "Proposed correction.",
    }
    assert await runtime.run([action]) == 0
    runtime.service.update_entry.assert_not_awaited()


async def test_entry_over_legacy_default_is_kept_with_user_limit_2000(runtime):
    action = create("L1") | {"content": "x" * 1200}
    assert await runtime.run([action]) == 1
    assert runtime.service.create_entry.await_args.kwargs["content"] == "x" * 1200


async def test_oversize_entry_is_rejected_whole_for_user_limit(runtime):
    runtime.user.journal_max_entry_chars = 500
    assert await runtime.run([create("L1") | {"content": "x" * 501}]) == 0
    runtime.service.create_entry.assert_not_awaited()


async def test_synthesis_only_accepts_evidence_for_exposed_version(runtime):
    runtime.note.level = "L2"
    action = {
        "action": "update",
        "entry_id": str(runtime.note.id),
        "evidence_outcome": "evidence",
        "content": "A rewritten pattern",
        "title": "A new title",
        "theme": "self_reflection",
        "level": "L2",
    }
    assert await runtime.run([action], previous=True, revisions={str(runtime.note.id): 1}) == 1
    kwargs = runtime.service.update_entry.await_args.kwargs
    assert kwargs["content"] is None and kwargs["title"] is None and kwargs["theme"] is None
    assert kwargs["evidence_outcome"] == "evidence"


async def test_extraction_event_key_is_stable_for_retry_and_scoped_by_user():
    from src.domains.journals.extraction_actions import extraction_event_key

    message = HumanMessage(content="A correction", id="turn-1")
    first = extraction_event_key("user1", "thread1", message, None)
    assert first == extraction_event_key("user1", "thread1", message, None)
    assert first != extraction_event_key("user2", "thread1", message, None)
    assert first != extraction_event_key("user1", "thread2", message, None)


async def test_extraction_replay_under_another_graph_run_keeps_one_message_event():
    from src.domains.journals.extraction_actions import extraction_event_key

    message = HumanMessage(content="Keep the qualification.", id="source-message")
    assert extraction_event_key("user", "session", message, "run-1") == extraction_event_key(
        "user", "session", message, "run-2"
    )


async def test_distinct_same_text_messages_remain_distinct_source_events():
    from src.domains.journals.extraction_actions import extraction_event_key

    first = HumanMessage(content="Keep the qualification.", id="source-1")
    second = HumanMessage(content=first.text, id="source-2")
    assert extraction_event_key("user", "session", first, "run") != extraction_event_key(
        "user", "session", second, "run"
    )


async def test_message_without_id_uses_a_bounded_scoped_run_fallback():
    from src.domains.journals.extraction_actions import extraction_event_key

    message = HumanMessage(content="A correction.")
    run = "r" * 500
    key = extraction_event_key("user", "session", message, run)
    assert len(key) <= 200 and run not in key
    assert key == extraction_event_key("user", "session", message, run)
    assert key != extraction_event_key("user", "session", message, "other-run")


async def test_provider_cut_output_never_reaches_action_parser_or_settlement(runtime):
    assert await runtime.run([create("L1")], response_metadata={"finish_reason": "length"}) == 0
    runtime.invoke.assert_awaited_once()
    runtime.service.create_entry.assert_not_awaited()
    extraction._persist_journal_tokens.assert_awaited_once()


async def test_partial_json_cannot_publish_a_salvaged_action(runtime):
    import json

    truncated = json.dumps([create("L1")])[:-1] + ', {"action": "delete"'
    assert await runtime.run([], raw=truncated) == 0
    runtime.service.create_entry.assert_not_awaited()
    extraction._persist_journal_tokens.assert_awaited_once()


async def test_complete_json_followed_by_prose_cannot_publish_its_substring(runtime):
    import json

    raw = json.dumps([create("L1")]) + "\nExplanation after the payload."
    assert await runtime.run([], raw=raw) == 0
    runtime.service.create_entry.assert_not_awaited()


async def test_repeated_json_key_cannot_select_an_arbitrary_mutation(runtime):
    ident = str(runtime.note.id)
    raw = (
        '[{"action":"delete","action":"update","entry_id":"' + ident + '","content":"Replacement"}]'
    )
    assert await runtime.run([], raw=raw) == 0
    runtime.service.update_entry.assert_not_awaited()


@pytest.mark.parametrize("fenced", [False, True])
async def test_complete_object_and_optional_markdown_fence_apply_valid_batch(runtime, fenced):
    import json

    raw = json.dumps({"actions": [create("L1")]})
    if fenced:
        raw = "```json\n" + raw + "\n```"
    assert await runtime.run([], raw=raw) == 1
    runtime.service.create_entry.assert_awaited_once()


async def test_invalid_conflicting_action_rejects_entire_batch(runtime):
    ident = str(runtime.note.id)
    actions = [
        {"action": "update", "entry_id": ident, "content": "A valid replacement"},
        {"action": "update", "entry_id": ident, "content": 42},
        create("L1"),
    ]
    assert await runtime.run(actions) == 0
    runtime.service.update_entry.assert_not_awaited()
    runtime.service.create_entry.assert_not_awaited()


async def test_latest_human_turn_remains_whole_but_older_messages_are_bounded():
    latest = "x" * 1100 + "This restriction applies ONLY to this script."
    text = extraction._format_messages_for_extraction(
        [
            HumanMessage(content="y" * 1100),
            AIMessage(content="A prior answer."),
            HumanMessage(content=latest),
        ]
    )
    assert latest in text
    assert "y" * 1100 not in text


async def test_persona_cannot_reclassify_subjects_by_the_because_clause():
    prompt = build_introspection_prompt(
        conversation="USER: Reformule ton ton sec.",
        existing_entries="",
        current_chars=0,
        max_chars=40000,
        size_warning="",
        language_name="French",
        max_entry_chars=800,
        health_context="",
        inner_state_section="",
        previous_turn_directives_section="",
        personality_code=None,
    )
    assert "entry is `learnings` — not `user_observations`/`self_reflection`" not in prompt
    assert "third-person or detached" not in prompt
