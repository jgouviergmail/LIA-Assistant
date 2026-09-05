"""What an administrator may read, and what it costs them (ADR-263).

Three properties:

- **superuser only**, on both surfaces — the register of other people's
  actions is not an ordinary admin page;
- **masked by default**: a wording names people, so reading it is a deliberate
  act, not the consequence of opening a page;
- **an unmasking is written down**. An administrator may legitimately need to
  read what an action said; nobody should be able to do so silently.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from src.domains.agents.effects.admin_router import (
    MASKED_LABEL,
    export_technical,
    read_admin_view,
)
from src.domains.agents.effects.models import EffectStatus

pytestmark = [pytest.mark.unit]


def _row(user_id: uuid.UUID | None = None) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        schema_version=1,
        user_id=user_id or uuid.uuid4(),
        thread_id="thread-1",
        run_id="run-1",
        idempotency_key="step:s1",
        tool_name="control_hue_light_tool",
        mutation_policy="reversible",
        status=SimpleNamespace(value="succeeded"),
        source=SimpleNamespace(value="user"),
        execution_mode="pipeline",
        approval_kind=None,
        approval_ref=None,
        retry_of=None,
        error_code=None,
        args_digest="d" * 64,
        draft_digest=None,
        result_digest=None,
        catalogue_fingerprint=None,
        result_truncated=False,
        claimed_at=datetime(2026, 9, 4, 10, 0, tzinfo=UTC),
        closed_at=None,
        label="ENCRYPTED",
        result_payload=None,
        provider_ref="provider-1",
        claim_token=uuid.uuid4(),
    )


class _Repository:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows
        self.seen: dict[str, Any] = {}

    async def list_for_export(self, **kwargs: Any) -> list[Any]:
        self.seen = kwargs
        return self._rows


class _Session:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.commits = 0

    def add(self, entry: Any) -> None:
        self.added.append(entry)

    async def commit(self) -> None:
        self.commits += 1


def _request() -> Any:
    return SimpleNamespace(client=SimpleNamespace(host="10.0.0.1"), headers={"user-agent": "t"})


def _superuser() -> Any:
    return SimpleNamespace(id=uuid.uuid4(), is_superuser=True, language="fr")


def _ordinary_user() -> Any:
    return SimpleNamespace(id=uuid.uuid4(), is_superuser=False, language="fr")


def _patched(repository: _Repository) -> Any:
    return patch(
        "src.domains.agents.effects.repository.EffectLedgerRepository",
        side_effect=lambda _db: repository,
    )


class TestOnlyASuperuserReads:
    async def test_the_technical_export_refuses_an_ordinary_user(self) -> None:
        with pytest.raises(HTTPException) as caught:
            await export_technical(db=object(), current_user=_ordinary_user())
        assert caught.value.status_code == 403

    async def test_the_readable_view_refuses_an_ordinary_user(self) -> None:
        with pytest.raises(HTTPException) as caught:
            await read_admin_view(request=_request(), db=object(), current_user=_ordinary_user())
        assert caught.value.status_code == 403

    async def test_the_article12_extraction_refuses_an_ordinary_user(self) -> None:
        # The widest read in the application: five records over every account.
        # Its docstring said « must be a superuser » while nothing checked it.
        from src.domains.agents.effects.admin_router import export_article12

        with pytest.raises(HTTPException) as caught:
            await export_article12(db=object(), current_user=_ordinary_user())
        assert caught.value.status_code == 403

    async def test_the_cross_account_extraction_refuses_an_ordinary_user(self) -> None:
        from src.domains.agents.effects.admin_router import export_readable_admin

        with pytest.raises(HTTPException) as caught:
            await export_readable_admin(
                request=_request(), db=object(), current_user=_ordinary_user()
            )
        assert caught.value.status_code == 403


class TestTheReadableViewIsMaskedByDefault:
    async def test_no_wording_without_an_explicit_unmask(self) -> None:
        repository = _Repository([_row()])
        with _patched(repository):
            rows = await read_admin_view(
                request=_request(), db=_Session(), current_user=_superuser()
            )

        assert rows[0].label == MASKED_LABEL
        assert rows[0].masked is True

    async def test_nothing_is_audited_when_nothing_was_revealed(self) -> None:
        repository = _Repository([_row()])
        session = _Session()
        with _patched(repository):
            await read_admin_view(request=_request(), db=session, current_user=_superuser())

        assert session.added == []
        assert session.commits == 0

    async def test_unmasking_reveals_and_is_written_down(self) -> None:
        repository = _Repository([_row()])
        session = _Session()
        with (
            _patched(repository),
            patch(
                "src.domains.agents.effects.repository.EffectLedgerRepository.decrypted_label",
                staticmethod(
                    lambda _row: {
                        "i18n_key": "effects.labels.control_hue_light_tool",
                        "values": {"target": "Salon"},
                    }
                ),
            ),
        ):
            rows = await read_admin_view(
                request=_request(), db=session, current_user=_superuser(), unmask=True
            )

        assert rows[0].masked is False
        assert "Salon" in rows[0].label
        assert len(session.added) == 1
        assert session.added[0].action == "effect_register_unmasked"
        assert session.added[0].details["row_count"] == 1
        assert session.commits == 1

    async def test_the_wording_follows_the_administrators_language(self) -> None:
        repository = _Repository([_row()])
        german_admin = SimpleNamespace(id=uuid.uuid4(), is_superuser=True, language="de")
        with (
            _patched(repository),
            patch(
                "src.domains.agents.effects.repository.EffectLedgerRepository.decrypted_label",
                staticmethod(
                    lambda _row: {
                        "i18n_key": "effects.labels.control_hue_light_tool",
                        "values": {"target": "Salon"},
                    }
                ),
            ),
        ):
            rows = await read_admin_view(
                request=_request(), db=_Session(), current_user=german_admin, unmask=True
            )

        assert "Licht" in rows[0].label


class TestTheTechnicalExport:
    async def test_it_returns_json_lines_naming_nobody(self) -> None:
        row = _row()
        repository = _Repository([row])
        with _patched(repository):
            response = await export_technical(db=object(), current_user=_superuser())

        body = bytes(response.body).decode("utf-8")
        assert "application/x-ndjson" in response.media_type
        assert str(row.user_id) not in body
        assert "ENCRYPTED" not in body
        assert "provider-1" not in body
        assert '"pseudonymised": true' in body

    async def test_the_filters_travel_to_the_query_and_the_header(self) -> None:
        repository = _Repository([])
        since = datetime(2026, 9, 1, tzinfo=UTC)
        with _patched(repository):
            response = await export_technical(
                since=since,
                status=EffectStatus.FAILED,
                db=object(),
                current_user=_superuser(),
            )

        assert repository.seen["since"] == since
        assert repository.seen["status"] is EffectStatus.FAILED
        body = bytes(response.body).decode("utf-8")
        assert '"status": "failed"' in body

    async def test_the_cap_comes_from_settings_and_is_published(self) -> None:
        from src.core.config import get_settings

        repository = _Repository([])
        with _patched(repository):
            response = await export_technical(db=object(), current_user=_superuser())

        assert repository.seen["limit"] == get_settings().effect_technical_export_max_rows
        assert '"row_cap"' in bytes(response.body).decode("utf-8")

    async def test_the_file_is_offered_as_a_download(self) -> None:
        repository = _Repository([])
        with _patched(repository):
            response = await export_technical(db=object(), current_user=_superuser())

        assert "attachment" in response.headers["content-disposition"]
