"""The writing style from the conversation: read, learn and forget on exact cards (ADR-383).

Proven here: the cards bind what the settings would do (the switch, the record replaced
or removed), a card answered after anything changed refuses, a learning releases its
transaction before waiting on the mailbox and the model (ADR-304), runs as the account's
one learning at a time in place of the record its card bound, every way a learning ends
is said in the tools' vocabulary (ADR-303), forgetting removes the confirmed record only,
and the cards read in the six languages.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from langchain_core.tools import StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import (
    AuthorizationError,
    ConnectorAPIError,
    ResourceConflictError,
    ResourceNotFoundError,
)
from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application import (
    writing_style_forgetting,
    writing_style_learning,
    writing_style_queries,
)
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.writing_style_catalogue import (
    WRITING_STYLE_FORGET_MANIFEST,
    WRITING_STYLE_LEARN_MANIFEST,
    WRITING_STYLE_READ_MANIFEST,
)
from src.domains.agents.application.writing_style_learning import (
    canonical_writing_style_learning,
    mailbox_failure_code,
)
from src.domains.agents.application.writing_style_schemas import (
    WritingStyleForgetRequest,
    WritingStyleLearnRequest,
    WritingStyleRecord,
)
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.emails.writing_style import (
    EmptyStyleProfile,
    Learning,
    LearningOutcome,
    SentMailUnreadable,
)
from src.domains.agents.tools import application_writing_style_tools
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.writing_style.models import WritingStyle
from src.domains.writing_style.repository import StoredStyle
from src.domains.writing_style.schemas import WritingStyleResponse

pytestmark = pytest.mark.unit

ACTOR = uuid4()
LEARNED_AT = datetime(2026, 11, 13, 9, 30, 15, 123456, tzinfo=UTC)
LANGUAGES = ("en", "fr", "de", "es", "it", "zh-CN")


class _Session(AsyncSession):
    """A session that records when it commits, and can lose its commit."""

    def __init__(self, events: list[str], *, fail_commit: bool = False) -> None:
        super().__init__()
        self.events = events
        self.fail_commit = fail_commit

    async def commit(self) -> None:
        self.events.append("commit")
        if self.fail_commit:
            raise RuntimeError("connection lost")


def _row(*, profile: bool = True, at: datetime = LEARNED_AT) -> WritingStyle:
    return WritingStyle(
        user_id=ACTOR,
        profile_encrypted="sealed" if profile else None,
        mails_read=12,
        built_at=at,
    )


def _stored(monkeypatch: pytest.MonkeyPatch, *, enabled: bool, row: WritingStyle | None) -> None:
    async def stored_style(db: AsyncSession, actor_id: UUID) -> StoredStyle:
        return StoredStyle(enabled=enabled, row=row)

    monkeypatch.setattr(writing_style_queries, "_stored", stored_style)


async def _learning_card(
    monkeypatch: pytest.MonkeyPatch, *, replaces: WritingStyle | None = None
) -> ApplicationActionDraftContent:
    _stored(monkeypatch, enabled=True, row=replaces)
    return await writing_style_learning.prepare_writing_style_learning(
        _Session([]), ACTOR, WritingStyleLearnRequest(scope="current_account")
    )


async def _forgetting_card(monkeypatch: pytest.MonkeyPatch) -> ApplicationActionDraftContent:
    _stored(monkeypatch, enabled=True, row=_row())
    return await writing_style_forgetting.prepare_writing_style_forgetting(
        _Session([]), ACTOR, WritingStyleForgetRequest(scope="current_account")
    )


def _learns(
    monkeypatch: pytest.MonkeyPatch, events: list[str], answer: Learning | Exception
) -> list[datetime | None]:
    """The account's one learning at a time, and the learning; the records it replaced."""
    replaced: list[datetime | None] = []

    async def one_at_a_time(user_id: UUID, learn: Callable[[], Awaitable[Learning]]) -> Learning:
        events.append("one at a time")
        assert user_id == ACTOR
        return await learn()

    async def learn(user_id: UUID, *, replaces: datetime | None, config: object) -> Learning:
        events.append("learn")
        assert user_id == ACTOR and config is None
        replaced.append(replaces)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(writing_style_learning, "learn_one_at_a_time", one_at_a_time)
    monkeypatch.setattr(writing_style_learning, "learn_writing_style", learn)
    return replaced


# --- What the cards bind -----------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [{}, {"scope": "all"}, {"scope": "current_account", "user_id": str(uuid4())}],
)
def test_no_other_scope_or_authority_can_be_asked(payload: dict[str, object]) -> None:
    for model in (WritingStyleLearnRequest, WritingStyleForgetRequest):
        with pytest.raises(ValidationError):
            model.model_validate(payload)


def test_a_record_is_named_by_its_instant_count_and_whether_it_holds_a_profile() -> None:
    assert writing_style_queries.record_of(None) is None
    assert writing_style_queries.record_of(_row(profile=False)) == WritingStyleRecord(
        learned_at=LEARNED_AT.isoformat(), mails_read=12, profile_learned=False
    )


async def test_a_learning_card_names_what_it_reads_and_the_record_it_replaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    card = await _learning_card(monkeypatch, replaces=_row())

    scope = card.before["writing_style_learning"]
    assert scope == {
        "mails_to_read": settings.writing_style_sent_mails,
        "replaces": {
            "learned_at": LEARNED_AT.isoformat(),
            "mails_read": 12,
            "profile_learned": True,
        },
    }
    assert card.after == {"writing_style_learning": {**scope, "requested": True}}
    assert canonical_writing_style_learning(card)
    tampered = card.model_copy(update={"after": {"writing_style_learning": scope}})
    assert not canonical_writing_style_learning(tampered)


async def test_nothing_is_offered_to_learn_while_the_switch_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stored(monkeypatch, enabled=False, row=_row())

    with pytest.raises(AuthorizationError) as refused:
        await writing_style_learning.prepare_writing_style_learning(
            _Session([]), ACTOR, WritingStyleLearnRequest(scope="current_account")
        )

    assert refused.value.detail == {"error_code": "CAPABILITY_DISABLED"}


async def test_nothing_learned_is_nothing_to_forget_whatever_the_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stored(monkeypatch, enabled=False, row=None)

    with pytest.raises(ResourceNotFoundError):
        await writing_style_forgetting.prepare_writing_style_forgetting(
            _Session([]), ACTOR, WritingStyleForgetRequest(scope="current_account")
        )
    _stored(monkeypatch, enabled=False, row=_row())
    card = await writing_style_forgetting.prepare_writing_style_forgetting(
        _Session([]), ACTOR, WritingStyleForgetRequest(scope="current_account")
    )
    assert card.after == {"writing_style_record": None}


# --- A confirmed learning ----------------------------------------------------------------


async def test_a_confirmed_learning_commits_before_waiting_then_says_what_it_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    card = await _learning_card(monkeypatch)
    events: list[str] = []
    _learns(monkeypatch, events, Learning("learned", 30))
    receipt = PreferenceWriteReceipt()

    await writing_style_learning.execute_writing_style_learning(
        _Session(events), ACTOR, card, receipt
    )

    # Nothing is held while the mailbox and the model answer (ADR-304).
    assert events == ["commit", "one at a time", "learn"]
    assert receipt.committed
    assert receipt.values == {"writing_style_learning": {"outcome": "learned", "mails_read": 30}}


@pytest.mark.parametrize("record", [_row(), None])
async def test_a_confirmed_learning_replaces_the_record_its_card_bound_and_nothing_since(
    monkeypatch: pytest.MonkeyPatch, record: WritingStyle | None
) -> None:
    """The settings' click and this card take the same claim: one learning per account at a
    time, and a record forgotten or learned again since the card is the person's later act."""
    card = await _learning_card(monkeypatch, replaces=record)
    events: list[str] = []
    replaced = _learns(monkeypatch, events, Learning("learned", 30))

    await writing_style_learning.execute_writing_style_learning(
        _Session(events), ACTOR, card, PreferenceWriteReceipt()
    )

    assert events == ["commit", "one at a time", "learn"]
    assert replaced == [record.built_at if record is not None else None]


async def test_too_few_sent_mails_is_a_learning_that_kept_what_it_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    card = await _learning_card(monkeypatch)
    _learns(monkeypatch, [], Learning("too_few", 3))
    receipt = PreferenceWriteReceipt()

    await writing_style_learning.execute_writing_style_learning(_Session([]), ACTOR, card, receipt)

    assert receipt.committed
    assert receipt.values == {"writing_style_learning": {"outcome": "too_few", "mails_read": 3}}


@pytest.mark.parametrize(
    ("outcome", "code"),
    [("no_mailbox", "CONNECTOR_NOT_ACTIVATED"), ("reconnect", "UNAUTHORIZED")],
)
async def test_a_learning_with_no_mailbox_to_read_says_why_in_the_tools_words(
    monkeypatch: pytest.MonkeyPatch, outcome: LearningOutcome, code: str
) -> None:
    card = await _learning_card(monkeypatch)
    _learns(monkeypatch, [], Learning(outcome))
    receipt = PreferenceWriteReceipt()

    with pytest.raises(CommandRejected) as refused:
        await writing_style_learning.execute_writing_style_learning(
            _Session([]), ACTOR, card, receipt
        )

    assert refused.value.code == code and not receipt.committed


@pytest.mark.parametrize("outcome", ["switched_off", "superseded"])
async def test_a_switch_turned_off_or_a_record_changed_during_the_learning_is_a_stale_card(
    monkeypatch: pytest.MonkeyPatch, outcome: LearningOutcome
) -> None:
    """Nothing was kept: the person's later act — the switch, a forget — stands."""
    card = await _learning_card(monkeypatch)
    _learns(monkeypatch, [], Learning(outcome, 30))
    receipt = PreferenceWriteReceipt()

    with pytest.raises(ResourceConflictError) as stale:
        await writing_style_learning.execute_writing_style_learning(
            _Session([]), ACTOR, card, receipt
        )

    assert stale.value.detail == {"error_code": "STALE_STATE"} and not receipt.committed


async def test_a_card_answered_after_the_record_changed_learns_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    card = await _learning_card(monkeypatch, replaces=None)
    events: list[str] = []
    _learns(monkeypatch, events, Learning("learned", 30))
    # The person learned from the settings meanwhile: another record stands.
    _stored(monkeypatch, enabled=True, row=_row(at=LEARNED_AT + timedelta(minutes=1)))

    with pytest.raises(ResourceConflictError):
        await writing_style_learning.execute_writing_style_learning(
            _Session(events), ACTOR, card, PreferenceWriteReceipt()
        )

    assert events == []


@pytest.mark.parametrize(
    ("cause", "code"),
    [
        (ConnectorAPIError("google_gmail", 401, "unauthorized"), "UNAUTHORIZED"),
        (ConnectorAPIError("google_gmail", 429, "slow down"), "RATE_LIMIT_EXCEEDED"),
        (ConnectionError("down"), "EXTERNAL_API_ERROR"),
    ],
)
async def test_a_mailbox_that_failed_is_classified_by_its_cause_never_its_words(
    monkeypatch: pytest.MonkeyPatch, cause: Exception, code: str
) -> None:
    card = await _learning_card(monkeypatch)
    failed = SentMailUnreadable("the sent folder could not be read")
    failed.__cause__ = cause
    _learns(monkeypatch, [], failed)

    with pytest.raises(CommandRejected) as refused:
        await writing_style_learning.execute_writing_style_learning(
            _Session([]), ACTOR, card, PreferenceWriteReceipt()
        )

    assert refused.value.code == code == mailbox_failure_code(cause)


async def test_a_model_that_said_nothing_keeps_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    card = await _learning_card(monkeypatch)
    _learns(monkeypatch, [], EmptyStyleProfile("no profile"))
    receipt = PreferenceWriteReceipt()

    with pytest.raises(CommandRejected) as refused:
        await writing_style_learning.execute_writing_style_learning(
            _Session([]), ACTOR, card, receipt
        )

    assert refused.value.code == "EMPTY_RESULT" and not receipt.committed


async def test_another_actor_or_an_expired_card_runs_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    card = await _learning_card(monkeypatch)
    events: list[str] = []
    _learns(monkeypatch, events, Learning("learned", 30))
    expired = card.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})

    with pytest.raises(CommandRejected, match="FORBIDDEN"):
        await writing_style_learning.execute_writing_style_learning(
            _Session(events), uuid4(), card, PreferenceWriteReceipt()
        )
    with pytest.raises(CommandRejected, match="EXPIRED"):
        await writing_style_learning.execute_writing_style_learning(
            _Session(events), ACTOR, expired, PreferenceWriteReceipt()
        )

    assert events == []


# --- A confirmed forgetting --------------------------------------------------------------


def _forgets(monkeypatch: pytest.MonkeyPatch, removed: bool) -> list[datetime | None]:
    asked: list[datetime | None] = []

    class _Repository:
        def __init__(self, db: AsyncSession) -> None:
            self.db = db

        async def forget(self, user_id: UUID, *, learned_at: datetime | None = None) -> bool:
            assert user_id == ACTOR
            asked.append(learned_at)
            return removed

    monkeypatch.setattr(writing_style_forgetting, "WritingStyleRepository", _Repository)
    return asked


async def test_a_confirmed_forgetting_removes_the_record_the_card_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    card = await _forgetting_card(monkeypatch)
    asked = _forgets(monkeypatch, removed=True)
    events: list[str] = []
    receipt = PreferenceWriteReceipt()

    await writing_style_forgetting.execute_writing_style_forgetting(
        _Session(events), ACTOR, card, receipt
    )

    assert asked == [LEARNED_AT] and events == ["commit"]
    assert receipt.committed
    assert receipt.values is not None
    assert receipt.values["writing_style_record"] == {
        "learned_at": LEARNED_AT.isoformat(),
        "mails_read": 12,
        "profile_learned": True,
        "removed": True,
    }


async def test_a_record_learned_since_the_card_is_kept_and_the_card_is_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    card = await _forgetting_card(monkeypatch)
    _forgets(monkeypatch, removed=False)

    with pytest.raises(ResourceConflictError):
        await writing_style_forgetting.execute_writing_style_forgetting(
            _Session([]), ACTOR, card, PreferenceWriteReceipt()
        )


async def test_a_lost_commit_is_an_unknown_completion_never_a_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    card = await _forgetting_card(monkeypatch)
    _forgets(monkeypatch, removed=True)
    receipt = PreferenceWriteReceipt()

    with pytest.raises(CommandRejected, match="COMPLETION_UNKNOWN"):
        await writing_style_forgetting.execute_writing_style_forgetting(
            _Session([], fail_commit=True), ACTOR, card, receipt
        )

    assert not receipt.committed


# --- The cards, in six languages -----------------------------------------------------------


@pytest.mark.parametrize("language", LANGUAGES)
async def test_the_learning_card_reads_in_every_language(
    monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    labels = get_draft_preview_labels(language)
    first = str(
        render_application_preview(
            (await _learning_card(monkeypatch)).model_dump(mode="json"), labels, str
        )
    )
    again = str(
        render_application_preview(
            (await _learning_card(monkeypatch, replaces=_row())).model_dump(mode="json"),
            labels,
            str,
        )
    )

    assert labels["application_writing_style_learn_note"] in first
    assert labels["application_writing_style_nothing_learned"] in first
    assert str(settings.writing_style_sent_mails) in first
    assert labels["application_writing_style_replaces"] in again
    assert LEARNED_AT.isoformat() in again and "12" in again


@pytest.mark.parametrize("language", LANGUAGES)
async def test_the_forgetting_card_reads_in_every_language(
    monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    labels = get_draft_preview_labels(language)
    card = await _forgetting_card(monkeypatch)

    preview = str(render_application_preview(card.model_dump(mode="json"), labels, str))

    assert labels["application_writing_style_forget_note"] in preview
    assert labels["application_writing_style_learned_on"] in preview
    assert LEARNED_AT.isoformat() in preview


async def test_an_edited_card_is_asked_again_for_the_account_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for card in (await _learning_card(monkeypatch), await _forgetting_card(monkeypatch)):
        prompt = build_application_edit_prompt(card.model_dump(mode="json"), "do it")

        assert json.loads(prompt[1]["content"])["intent"] == {"scope": "current_account"}


# --- What the model sees and reads ---------------------------------------------------------


def _runtime() -> MagicMock:
    runtime = MagicMock()
    runtime.context = LiaRuntimeContext(
        user_id=ACTOR, thread_id="thread", conversation_id="conversation", language="fr"
    )
    return runtime


def _structured(tool: object) -> StructuredTool:
    """The decorated tool as LangChain built it: what the model and the loop see."""
    assert isinstance(tool, StructuredTool)
    return tool


def test_the_model_names_no_account_and_no_authority() -> None:
    """Identity is injected: what the loop binds names the request only."""
    for tool, field in (
        (application_writing_style_tools.get_lia_writing_style_tool, "query"),
        (application_writing_style_tools.learn_lia_writing_style_tool, "request"),
        (application_writing_style_tools.forget_lia_writing_style_tool, "request"),
    ):
        bound = convert_to_openai_tool(_structured(tool))["function"]["parameters"]
        assert set(bound["properties"]) == {field}
    assert WRITING_STYLE_READ_MANIFEST.mutation_policy == "read"
    for manifest in (WRITING_STYLE_LEARN_MANIFEST, WRITING_STYLE_FORGET_MANIFEST):
        assert manifest.mutation_policy == "draft" and not manifest.initiative_eligible


async def test_the_read_answers_what_the_settings_show(monkeypatch: pytest.MonkeyPatch) -> None:
    shown = WritingStyleResponse(
        enabled=True,
        mails_to_read=30,
        profile="Opens with « Salut ».",
        mails_read=12,
        learned_at=LEARNED_AT,
    )

    async def read(db: AsyncSession, actor_id: UUID) -> WritingStyleResponse:
        assert actor_id == ACTOR
        return shown

    monkeypatch.setattr(application_writing_style_tools, "read_writing_style", read)
    monkeypatch.setattr(application_writing_style_tools, "get_db_context", _no_session)

    answer = await _call(
        application_writing_style_tools.get_lia_writing_style_tool, query=None, runtime=_runtime()
    )

    assert answer.success
    assert answer.structured_data == shown.model_dump(mode="json")


@pytest.mark.parametrize(
    ("raised", "code"),
    [
        (AuthorizationError(detail={"error_code": "CAPABILITY_DISABLED"}), "CAPABILITY_DISABLED"),
        (ResourceNotFoundError("writing_style"), "NOT_FOUND"),
    ],
)
async def test_a_card_that_cannot_be_prepared_says_why(
    monkeypatch: pytest.MonkeyPatch, raised: Exception, code: str
) -> None:
    async def refuse(
        db: AsyncSession,
        actor_id: UUID,
        request: WritingStyleLearnRequest,
        *,
        command_id: UUID | None = None,
    ) -> ApplicationActionDraftContent:
        raise raised

    monkeypatch.setattr(application_writing_style_tools, "prepare_writing_style_learning", refuse)
    monkeypatch.setattr(application_writing_style_tools, "get_db_context", _no_session)

    answer = await _call(
        application_writing_style_tools.learn_lia_writing_style_tool,
        request={"scope": "current_account"},
        runtime=_runtime(),
    )

    assert not answer.success and answer.error_code == code


async def _call(tool: object, **arguments: object) -> UnifiedToolOutput:
    coroutine = _structured(tool).coroutine
    assert coroutine is not None
    answer = await coroutine(**arguments)
    assert isinstance(answer, UnifiedToolOutput)
    return answer


@asynccontextmanager
async def _no_session() -> AsyncIterator[AsyncSession]:
    yield _Session([])
