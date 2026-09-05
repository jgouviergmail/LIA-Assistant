"""An administrator extracting a readable register (ADR-263, lot 4).

The third and fourth extractions the owner asked for: a human-readable register
for one account, several, or all of them over a period — and the technical one
under the same scoping. Both reuse the engine the user's own export uses, so
the three documents cannot disagree about what a register says.

Two properties are this surface's own:

- **masked by default, unmasked on the record.** An administrator may
  legitimately need to read what an action said; nobody should be able to do so
  without leaving a trace. That applies to the ACTION register, whose label
  names people — the consultation register has nothing to mask, and pretending
  otherwise would be security theatre that costs an operator information.
- **"all accounts" is a request, not an omission.** Passing no account must
  mean the whole instance because an administrator asked for the whole
  instance, and the row count says how much that was.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.effects.admin_router import export_readable_admin

pytestmark = [pytest.mark.unit]

ADMIN = uuid.uuid4()
ALICE = uuid.uuid4()
BOB = uuid.uuid4()


def _action(user_id: uuid.UUID = ALICE, **overrides: Any) -> Any:
    row = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "label": None,
        "tool_name": "send_email_tool",
        "mutation_policy": "confirm",
        "status": "succeeded",
        "source": "user",
        "execution_mode": "pipeline",
        "approval_kind": "tool_confirm",
        "provider_ref": "msg-1",
        "error_code": None,
        "thread_id": "conv-1",
        "claimed_at": datetime(2026, 9, 3, 10, 0, tzinfo=UTC),
        "closed_at": datetime(2026, 9, 3, 10, 0, 1, tzinfo=UTC),
    }
    row.update(overrides)
    return SimpleNamespace(**row)


def _treatment(user_id: uuid.UUID = ALICE, **overrides: Any) -> Any:
    row = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "tool_name": "get_emails_tool",
        "mutation_policy": "read",
        "outcome": "ok",
        "source": "user",
        "execution_mode": "pipeline",
        "thread_id": "conv-1",
        "duration_ms": 120,
        "occurred_at": datetime(2026, 9, 3, 10, 0, tzinfo=UTC),
    }
    row.update(overrides)
    return SimpleNamespace(**row)


class _Repository:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows
        self.seen: dict[str, Any] = {}

    def __call__(self, _db: Any) -> Any:
        return self

    async def list_for_export(self, **kwargs: Any) -> list[Any]:
        self.seen = kwargs
        return self._rows

    @staticmethod
    def decrypted_label(_row: Any) -> dict[str, Any]:
        return {"i18n_key": "effects.labels.send_email_tool", "values": {"recipient": "Marie"}}


def _admin(is_superuser: bool = True) -> Any:
    return SimpleNamespace(
        id=ADMIN, is_superuser=is_superuser, language="fr", timezone="Europe/Paris"
    )


def _request() -> Any:
    return SimpleNamespace(client=SimpleNamespace(host="10.0.0.1"), headers={"user-agent": "x"})


async def _run(**kwargs: Any) -> Any:
    repository = kwargs.pop("repository")
    db = AsyncMock()
    db.add = lambda _row: None
    with (
        patch("src.domains.agents.effects.repository.EffectLedgerRepository", repository),
        patch("src.domains.agents.effects.treatment_repository.TreatmentRepository", repository),
    ):
        return await export_readable_admin(request=_request(), db=db, **kwargs)


class TestOnlyAnAdministrator:
    async def test_an_ordinary_user_is_refused(self) -> None:
        with pytest.raises(Exception):  # noqa: B017 - the raiser's own type
            await _run(
                register="actions",
                export_format="markdown",
                user_ids=None,
                since=None,
                until=None,
                unmask=False,
                current_user=_admin(is_superuser=False),
                repository=_Repository([_action()]),
            )


class TestTheScopeIsWhatWasAsked:
    async def test_one_account_narrows_the_query(self) -> None:
        repository = _Repository([_action()])

        await _run(
            register="actions",
            export_format="markdown",
            user_ids=[ALICE],
            since=None,
            until=None,
            unmask=False,
            current_user=_admin(),
            repository=repository,
        )

        assert repository.seen["user_ids"] == [ALICE]

    async def test_several_accounts_narrow_it_to_several(self) -> None:
        repository = _Repository([_action(), _action(BOB)])

        await _run(
            register="actions",
            export_format="csv",
            user_ids=[ALICE, BOB],
            since=None,
            until=None,
            unmask=False,
            current_user=_admin(),
            repository=repository,
        )

        assert repository.seen["user_ids"] == [ALICE, BOB]

    async def test_no_account_means_every_account(self) -> None:
        """An omission that means "everything" must be a request, not a bug."""
        repository = _Repository([_action(), _action(BOB)])

        response = await _run(
            register="actions",
            export_format="csv",
            user_ids=None,
            since=None,
            until=None,
            unmask=False,
            current_user=_admin(),
            repository=repository,
        )

        assert repository.seen["user_ids"] is None
        assert response.headers["x-register-rows"] == "2"

    async def test_the_period_travels(self) -> None:
        since = datetime(2026, 9, 1, tzinfo=UTC)
        until = datetime(2026, 9, 4, tzinfo=UTC)
        repository = _Repository([_action()])

        await _run(
            register="actions",
            export_format="markdown",
            user_ids=None,
            since=since,
            until=until,
            unmask=False,
            current_user=_admin(),
            repository=repository,
        )

        assert repository.seen["since"] == since
        assert repository.seen["until"] == until


class TestTheWordingIsMaskedUnlessAsked:
    async def test_an_action_wording_is_withheld_by_default(self) -> None:
        response = await _run(
            register="actions",
            export_format="markdown",
            user_ids=None,
            since=None,
            until=None,
            unmask=False,
            current_user=_admin(),
            repository=_Repository([_action()]),
        )

        body = response.body.decode()
        assert "Marie" not in body
        assert "send_email_tool" in body, "masking must not hide WHICH capability acted"

    async def test_unmasking_reveals_and_is_recorded(self) -> None:
        repository = _Repository([_action()])
        db = AsyncMock()
        audited: list[Any] = []
        db.add = audited.append

        with (
            patch("src.domains.agents.effects.repository.EffectLedgerRepository", repository),
            patch(
                "src.domains.agents.effects.treatment_repository.TreatmentRepository",
                repository,
            ),
        ):
            response = await export_readable_admin(
                request=_request(),
                register="actions",
                export_format="markdown",
                user_ids=None,
                since=None,
                until=None,
                unmask=True,
                db=db,
                current_user=_admin(),
            )

        assert "Marie" in response.body.decode()
        assert len(audited) == 1, "an unmasked export left no trace"

    async def test_a_consultation_export_has_nothing_to_mask(self) -> None:
        """No label, no arguments: masking here would cost information for nothing."""
        response = await _run(
            register="consultations",
            export_format="markdown",
            user_ids=None,
            since=None,
            until=None,
            unmask=False,
            current_user=_admin(),
            repository=_Repository([_treatment()]),
        )

        body = response.body.decode()
        assert "E-mails" in body
        assert "•••" not in body


class TestTheDocumentSaysWhatItIs:
    async def test_the_file_is_named_after_the_register(self) -> None:
        response = await _run(
            register="consultations",
            export_format="csv",
            user_ids=None,
            since=None,
            until=None,
            unmask=False,
            current_user=_admin(),
            repository=_Repository([_treatment()]),
        )

        assert "consultations" in response.headers["content-disposition"]

    async def test_a_truncated_export_says_so(self) -> None:
        from src.core.config import settings

        rows = [_treatment() for _ in range(settings.effect_technical_export_max_rows)]

        response = await _run(
            register="consultations",
            export_format="csv",
            user_ids=None,
            since=None,
            until=None,
            unmask=False,
            current_user=_admin(),
            repository=_Repository(rows),
        )

        assert response.headers["x-register-truncated"] == "true"


class TestTheTechnicalExportServesBothRegisters:
    """The consultation register had NO technical export: an administrator
    could analyse what the assistant did and nothing of what it looks at."""

    async def _run(self, **kwargs: Any) -> Any:
        repository = kwargs.pop("repository")
        db = AsyncMock()
        with (
            patch("src.domains.agents.effects.repository.EffectLedgerRepository", repository),
            patch(
                "src.domains.agents.effects.treatment_repository.TreatmentRepository", repository
            ),
        ):
            from src.domains.agents.effects.admin_router import export_technical

            return await export_technical(db=db, **kwargs)

    async def test_consultations_are_exportable_and_pseudonymised(self) -> None:
        repository = _Repository([_treatment()])

        response = await self._run(
            register="consultations",
            since=None,
            until=None,
            user_ids=[ALICE],
            tool_name=None,
            mutation_policy=None,
            status=None,
            source=None,
            execution_mode=None,
            current_user=_admin(),
            repository=repository,
        )

        body = response.body.decode()
        assert "get_emails_tool" in body
        assert str(ALICE) not in body, "an account id reached a pseudonymised export"
        assert "conv-1" not in body, "a conversation id reconstructs someone's day"
        assert repository.seen["user_ids"] == [ALICE]

    async def test_the_file_is_named_after_the_register(self) -> None:
        response = await self._run(
            register="consultations",
            since=None,
            until=None,
            user_ids=None,
            tool_name=None,
            mutation_policy=None,
            status=None,
            source=None,
            execution_mode=None,
            current_user=_admin(),
            repository=_Repository([_treatment()]),
        )

        assert "consultations" in response.headers["content-disposition"]

    async def test_a_filter_the_register_cannot_honour_is_REPORTED_not_ignored(self) -> None:
        """Silently dropping a filter makes an unfiltered file look filtered."""
        import json

        response = await self._run(
            register="consultations",
            since=None,
            until=None,
            user_ids=None,
            tool_name=None,
            mutation_policy=None,
            status=None,
            source=None,
            execution_mode="react",
            current_user=_admin(),
            repository=_Repository([_treatment()]),
        )

        header = json.loads(response.body.decode().splitlines()[0])
        assert "execution_mode" in header["filters"]["ignored_filters"]

    async def test_the_action_export_is_unchanged(self) -> None:
        response = await self._run(
            register="actions",
            since=None,
            until=None,
            user_ids=None,
            tool_name=None,
            mutation_policy=None,
            status=None,
            source=None,
            execution_mode=None,
            current_user=_admin(),
            repository=_Repository([_action()]),
        )

        assert "actions" in response.headers["content-disposition"]
        assert "send_email_tool" in response.body.decode()
