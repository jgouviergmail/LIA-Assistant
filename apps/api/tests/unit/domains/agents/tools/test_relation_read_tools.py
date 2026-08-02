"""Three read capabilities for the three CRM blocks the assistant could not read.

Before these, the ONLY way into calls / open commitments / relayed messages was
``get_person_overview_tool`` — which lives in the ``contact`` domain. So a
question about a call landed on ``telephony``, whose whole catalogue was ONE
tool: place a phone call. The system asks the planner to cover its primary
domain, and covering ``telephony`` meant WRITING. "De quand date mon dernier
appel à ma femme ?" was planned as a phone call to ask her (prod 2026-08-01).

Each tool therefore lives in the domain whose catalogue lacked a read — not on
``contact_agent`` with ``serves_domains``, which was measured to evict three
mutation tools per crowded combination.

All three project the SAME ``RelationsService.build_detail``: one resolution of
identity, so the tool and the relationship card can never disagree about who
someone is (ADR-185).
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

import src.domains.agents.tools.relation_read_tools as mod
from src.core.config import settings
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.relation_read_tools import (
    get_calls_tool,
    get_open_loops_tool,
    get_peer_messages_tool,
)

pytestmark = pytest.mark.unit

USER_ID = uuid4()
NOW = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)


def _detail(**overrides):
    base = {
        "display_name": "Alice Vernier",
        "identity_confidence": SimpleNamespace(value="high"),
        "is_peer": True,
        "open_loops": [
            SimpleNamespace(
                id="l1",
                subject="Envoyer le devis",
                direction="user_owes",
                days_open=3,
                due_hint=None,
            )
        ],
        "open_loops_total": 7,
        "recent_calls": [
            SimpleNamespace(
                id="c1",
                objective="Point chantier",
                outcome="completed",
                summary="OK pour jeudi",
                created_at=NOW,
            )
        ],
        "recent_calls_total": 12,
        "peer_messages": [
            SimpleNamespace(
                id="m1", direction="sent", content="Je t'appelle demain", occurred_at=NOW
            )
        ],
        "peer_messages_total": 4,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _runtime():
    """Same shape the other tool tests use — the decorator validates it."""
    return SimpleNamespace(context=SimpleNamespace(user_id=str(USER_ID)))


@pytest.fixture(autouse=True)
def _patch_service(monkeypatch: pytest.MonkeyPatch):
    """Patch the ONE read all three tools share, and the runtime validation."""
    calls: dict = {"names": [], "detail": _detail()}

    async def _build_detail(_user_id, name):
        calls["names"].append(name)
        return calls["detail"]

    monkeypatch.setattr(mod, "_relation_detail", _build_detail)
    monkeypatch.setattr(
        mod, "validate_runtime_config", lambda *_a, **_k: SimpleNamespace(user_id=str(USER_ID))
    )
    return calls


async def _run(tool, **kwargs) -> UnifiedToolOutput:
    """Invoke the underlying coroutine (the LangChain wrapper is not the SUT)."""
    return await tool.coroutine(person_name="ma femme", runtime=_runtime(), **kwargs)


class TestTheyReadTheRelationship:
    async def test_calls_are_returned(self) -> None:
        output = await _run(get_calls_tool)

        assert output.structured_data["calls"][0]["objective"] == "Point chantier"
        assert output.structured_data["person"] == "Alice Vernier"

    async def test_open_loops_are_returned(self) -> None:
        output = await _run(get_open_loops_tool)

        assert output.structured_data["open_loops"][0]["subject"] == "Envoyer le devis"

    async def test_relayed_messages_are_returned(self) -> None:
        output = await _run(get_peer_messages_tool)

        assert output.structured_data["peer_messages"][0]["content"] == "Je t'appelle demain"

    async def test_all_three_resolve_identity_the_same_way(self, _patch_service) -> None:
        """One resolution of identity — the tool and the card cannot diverge."""
        await _run(get_calls_tool)
        await _run(get_open_loops_tool)
        await _run(get_peer_messages_tool)

        assert _patch_service["names"] == ["ma femme", "ma femme", "ma femme"]


class TestTheCountIsExactOrAbsent:
    """A count shown to the user is a claim: exact, or it does not exist."""

    async def test_the_total_is_the_aggregate_not_the_page_length(self) -> None:
        output = await _run(get_calls_tool)

        assert output.structured_data["calls_total"] == 12
        assert len(output.structured_data["calls"]) == 1

    async def test_open_loops_total(self) -> None:
        assert (await _run(get_open_loops_tool)).structured_data["open_loops_total"] == 7

    async def test_relayed_messages_total(self) -> None:
        assert (await _run(get_peer_messages_tool)).structured_data["peer_messages_total"] == 4


class TestTheBoundIsAppliedAndPublished:
    async def test_the_default_limit_is_the_setting(self, _patch_service) -> None:
        many = [
            SimpleNamespace(
                id=f"c{i}", objective=f"Appel {i}", outcome=None, summary=None, created_at=NOW
            )
            for i in range(50)
        ]
        _patch_service["detail"] = _detail(recent_calls=many)

        output = await _run(get_calls_tool)

        assert len(output.structured_data["calls"]) == settings.relations_max_items_per_section

    async def test_an_explicit_limit_is_clamped_to_the_ceiling(self, _patch_service) -> None:
        many = [
            SimpleNamespace(
                id=f"c{i}", objective=f"Appel {i}", outcome=None, summary=None, created_at=NOW
            )
            for i in range(50)
        ]
        _patch_service["detail"] = _detail(recent_calls=many)

        output = await _run(get_calls_tool, limit=999)

        assert len(output.structured_data["calls"]) <= settings.relations_max_items_per_section

    @pytest.mark.parametrize("bad_limit", ["beaucoup", "", None, 3.9, -4, 0])
    async def test_an_unusable_limit_falls_back_instead_of_crashing(
        self, _patch_service, bad_limit
    ) -> None:
        """A model fills parameters from prose, so `limit` can arrive as
        anything. A page size is presentation, not intent: what cannot be read
        degrades to the default, and the question still gets an answer.

        The crash this pins down was real — the clamp ran OUTSIDE the try that
        turns failures into an honest error, so `int("beaucoup")` escaped the
        tool entirely instead of being repaired or reported.
        """
        _patch_service["detail"] = _detail(
            recent_calls=[
                SimpleNamespace(
                    id=f"c{i}", objective=f"Appel {i}", outcome=None, summary=None, created_at=NOW
                )
                for i in range(5)
            ]
        )

        output = await _run(get_calls_tool, limit=bad_limit)

        assert output.success is True
        assert 1 <= len(output.structured_data["calls"]) <= settings.relations_max_items_per_section

    def test_every_manifest_publishes_its_bound(self) -> None:
        """Whatever a validator can reject, its producer must be able to read."""
        from src.domains.agents.relations.catalogue_manifests import (
            RELATION_READ_MANIFESTS,
        )

        for manifest in RELATION_READ_MANIFESTS:
            limit = next(p for p in manifest.parameters if p.name == "limit")
            kinds = {constraint.kind for constraint in limit.constraints}
            assert "maximum" in kinds, f"{manifest.name} hides the cap it enforces"


class TestEmptyIsNotAFailure:
    async def test_no_call_at_all(self, _patch_service) -> None:
        _patch_service["detail"] = _detail(recent_calls=[], recent_calls_total=0)

        output = await _run(get_calls_tool)

        assert output.structured_data["calls"] == []
        assert output.structured_data["calls_total"] == 0


class TestFailureIsHonest:
    async def test_an_unreadable_relationship_fails_loudly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Never an empty list on error: that would claim there is nothing."""

        async def _boom(_user_id, _name):
            raise RuntimeError("db down")

        monkeypatch.setattr(mod, "_relation_detail", _boom)

        output = await _run(get_calls_tool)

        assert output.success is False


class TestNoPIIAtInfoLevel:
    async def test_the_person_name_is_never_logged_at_info(self, caplog) -> None:
        import logging

        with caplog.at_level(logging.INFO):
            await _run(get_calls_tool)

        assert "Alice Vernier" not in caplog.text
        assert "ma femme" not in caplog.text
