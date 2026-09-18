"""The egress question (ADR-298): what the card carries — and what it never does.

The answer is settled in the ReAct loop (``react_egress_question``), which
re-invokes the very call that asked: the card therefore carries no replay,
no script and no item, only what the person decides on."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.domains.agents.drafts.models import DraftType
from src.domains.agents.python_sandbox.egress.draft import ask_for_hosts, summarize_turn_data
from src.domains.agents.python_sandbox.egress.hosts import HostDecision, HostStatus

pytestmark = pytest.mark.unit

MODULE = "src.domains.agents.python_sandbox.egress.draft"
USER = uuid.uuid4()
ITEMS = {
    "e1": {"type": "EMAIL", "subject": "Vol"},
    "e2": {"type": "EMAIL", "subject": "Hôtel"},
    "c1": {"type": "CONTACT", "name": "Paul"},
    "d1": {"type": "DRAFT", "content": {}},
}


def _decision(unknown: tuple[str, ...] = ("status.example.org",)) -> HostDecision:
    statuses = {"api.example.org": HostStatus.OPERATOR}
    statuses.update(dict.fromkeys(unknown, HostStatus.UNKNOWN))
    return HostDecision(statuses=statuses, unknown=unknown, credentials=(), share_turn_data=True)


class TestTheTurnDataSummary:
    def test_counts_data_by_kind_and_ignores_drafts(self) -> None:
        assert summarize_turn_data(ITEMS, max_bytes=100_000, language="fr") == {
            "counts": {"email": 2, "contact": 1},
            "available": True,
            "language": "fr",
        }

    def test_says_when_the_data_cannot_travel(self) -> None:
        summary = summarize_turn_data(ITEMS, max_bytes=10, language="en")
        assert summary["available"] is False and summary["counts"] == {"email": 2, "contact": 1}


class TestAskingTheQuestion:
    def test_the_draft_carries_the_hosts_the_purpose_and_the_counts(self) -> None:
        with patch(
            f"{MODULE}.get_settings",
            return_value=SimpleNamespace(skills_script_max_input_kb=64),
        ):
            output = ask_for_hosts(
                decision=_decision(), purpose="probe the service", items=ITEMS, language="fr"
            )
        assert output.tool_metadata["requires_confirmation"] is True
        assert output.tool_metadata["draft_type"] == DraftType.SANDBOX_EGRESS.value
        draft_id = output.tool_metadata["draft_id"]
        content = output.registry_updates[draft_id].payload["content"]
        assert content["hosts"] == ["api.example.org", "status.example.org"]
        assert content["hosts_unknown"] == ["status.example.org"]
        assert content["hosts_label"] == "status.example.org"
        assert content["purpose"] == "probe the service"
        assert content["data_summary"]["counts"] == {"email": 2, "contact": 1}
        # Nothing of the person's data and nothing of the script travels on the
        # card: the loop re-invokes the call once the person has answered.
        assert set(content) == {"hosts", "hosts_unknown", "hosts_label", "purpose", "data_summary"}
        assert "Vol" not in json.dumps(content) and "Paul" not in json.dumps(content)

    def test_data_too_large_is_said_on_the_card(self) -> None:
        with patch(
            f"{MODULE}.get_settings",
            return_value=SimpleNamespace(skills_script_max_input_kb=0),
        ):
            output = ask_for_hosts(decision=_decision(), purpose="p", items=ITEMS, language="en")
        content = output.registry_updates[output.tool_metadata["draft_id"]].payload["content"]
        assert content["data_summary"]["available"] is False
