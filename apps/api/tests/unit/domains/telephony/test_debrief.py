"""T01 structured call debrief — schema contract and persistence wiring.

What must hold:
- ``ReturnProposal`` still validates with ONLY the two historical fields (a
  provider/model returning the v1 shape must not lose the whole return);
- ``debrief_dict`` carries exactly the five T01 fields, ``exclude_none``;
- ``process_completed_call`` persists the debrief and ships it in the
  notification metadata — and an all-empty debrief persists as None
  (absence, not noise), which is also the synthesis-fallback path.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

import src.domains.telephony.return_synthesis as rs
from src.domains.telephony.models import PhoneCallStatus
from src.domains.telephony.schemas import ReturnProposal


@pytest.mark.unit
class TestReturnProposalSchema:
    def test_v1_shape_still_validates(self) -> None:
        proposal = ReturnProposal(summary="Recap", proposal_text="J'ai appelé Marie")
        assert proposal.commitments == []
        assert proposal.follow_up_draft is None
        assert proposal.uncertainties == []

    def test_debrief_dict_carries_the_five_fields_exclude_none(self) -> None:
        proposal = ReturnProposal(
            summary="s",
            proposal_text="p",
            commitments=["Marie confirme mardi 19h."],
            follow_up_tasks=["Réserver la table."],
            uncertainties=["Le supplément terrasse n'est pas confirmé."],
        )
        debrief = proposal.debrief_dict()
        assert debrief == {
            "commitments": ["Marie confirme mardi 19h."],
            "follow_up_tasks": ["Réserver la table."],
            "follow_up_reminders": [],
            "uncertainties": ["Le supplément terrasse n'est pas confirmé."],
        }
        # Text fields never leak into the persisted debrief.
        assert "summary" not in debrief
        assert "proposal_text" not in debrief


def _payload() -> dict:
    return {
        "data": {
            "metadata": {"call_duration_secs": 30},
            "status": "done",
            "analysis": {
                "transcript_summary": "she agreed",
                "data_collection_results": {"agreed": {"value": True}},
            },
            "transcript": [{"role": "agent", "message": "hi"}],
        }
    }


def _active_call() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        status=PhoneCallStatus.IN_PROGRESS,
        objective="ask availability",
        callee_display="Marie",
        created_at=datetime.now(UTC),
    )


def _install(monkeypatch, *, proposal: ReturnProposal) -> dict:
    captured: dict = {}
    call = _active_call()

    class _FakeRepo:
        def __init__(self, db) -> None:  # noqa: ANN001
            pass

        async def get_by_call_id(self, _cid):
            return call

        async def mark_completed(self, cid, **kwargs):
            captured["mark"] = {"call_id": cid, **kwargs}
            return True

        async def mark_notification_delivered(self, cid) -> None:
            captured["delivered"] = cid

    async def _get_user(_model, _pk):
        return SimpleNamespace(language="fr", timezone="Europe/Paris")

    @contextlib.asynccontextmanager
    async def _ctx():
        yield SimpleNamespace(get=_get_user)

    class _FakeDispatcher:
        async def dispatch(self, **kwargs):
            captured["dispatch"] = kwargs

    async def _fake_synth(**_kwargs):
        return (proposal, None)

    monkeypatch.setattr(rs, "TelephonyRepository", _FakeRepo)
    monkeypatch.setattr(rs, "get_db_context", _ctx)
    monkeypatch.setattr(rs, "NotificationDispatcher", lambda: _FakeDispatcher())
    monkeypatch.setattr(rs, "synthesize_return", _fake_synth)
    return captured


@pytest.mark.unit
async def test_debrief_is_persisted_and_shipped_in_metadata(monkeypatch) -> None:
    proposal = ReturnProposal(
        summary="Recap",
        proposal_text="J'ai appelé Marie",
        commitments=["Marie confirme mardi 19h."],
        uncertainties=["Supplément terrasse non confirmé."],
    )
    captured = _install(monkeypatch, proposal=proposal)

    await rs.process_completed_call(uuid4(), _payload())

    persisted = captured["mark"]["debrief"]
    assert persisted["commitments"] == ["Marie confirme mardi 19h."]
    assert captured["dispatch"]["metadata"]["debrief"] == persisted


@pytest.mark.unit
async def test_empty_debrief_persists_as_none_and_stays_out_of_metadata(monkeypatch) -> None:
    # The synthesis-fallback path builds exactly this all-empty proposal.
    proposal = ReturnProposal(summary="Recap", proposal_text="J'ai appelé Marie")
    captured = _install(monkeypatch, proposal=proposal)

    await rs.process_completed_call(uuid4(), _payload())

    assert captured["mark"]["debrief"] is None
    assert "debrief" not in captured["dispatch"]["metadata"]
