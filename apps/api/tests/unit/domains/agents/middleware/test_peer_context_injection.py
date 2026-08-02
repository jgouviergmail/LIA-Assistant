"""When a CONNECTED user is named, the answer already knows about them.

Until now, naming a peer only corrected the ROUTING (`apply_peer_domain_
correction` appends the `peer` domain) — no data was injected, so the assistant
announced a lookup for facts the database already held.

Three properties this pins down:

- **local sources only**: open commitments, calls, relayed messages. Memories
  are excluded on purpose — they are already injected by semantic relevance,
  and injecting them twice would double their weight in the prompt;
- **the user's 360° scope is sovereign**: a section unticked on the
  relationship card is not injected here either. The card is where the user
  said what a "point on this person" may read;
- **a false positive is a PII leak**: the detection matches whole words over
  the peer directory, so "ils vont se marier" never surfaces Marie's file.
"""

from __future__ import annotations

from collections.abc import Sequence
from types import SimpleNamespace
from uuid import uuid4

import pytest

import src.domains.agents.middleware.peer_context_injection as mod
from src.core.config import settings
from src.domains.agents.middleware.peer_context_injection import build_peer_context
from src.domains.relations.overview_scope import OverviewSection, RelationOverviewScope

pytestmark = pytest.mark.unit

USER_ID = uuid4()


def _detail(**overrides):
    """A RelationDetail-shaped stub: the injector reads attributes only."""
    base = {
        "display_name": "Alice Vernier",
        "open_loops": [SimpleNamespace(subject="Envoyer le devis", direction="i_owe", days_open=3)],
        "recent_calls": [
            SimpleNamespace(
                objective="Point chantier", outcome="completed", summary="OK pour jeudi"
            )
        ],
        "peer_messages": [SimpleNamespace(direction="sent", content="Je t'appelle demain")],
        "open_loops_total": 1,
        "recent_calls_total": 1,
        "peer_messages_total": 1,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "peer_context_injection_enabled", True, raising=False)
    monkeypatch.setattr(settings, "peers_enabled", True, raising=False)


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    peers: Sequence[str] = ("Alice Vernier",),
    scope: RelationOverviewScope | None = None,
    detail=None,
) -> dict:
    """Patch the three reads the injector performs, recording the calls."""
    calls: dict = {"details_for": []}

    async def _directory(_user_id):
        return list(peers)

    async def _scope(_user_id):
        return scope if scope is not None else RelationOverviewScope()

    async def _detail_for(_user_id, name):
        calls["details_for"].append(name)
        return detail if detail is not None else _detail()

    monkeypatch.setattr(mod, "_peer_directory", _directory)
    monkeypatch.setattr(mod, "_overview_scope", _scope)
    monkeypatch.setattr(mod, "_relation_detail", _detail_for)
    return calls


class TestTheFactsAreInjected:
    async def test_a_named_peer_brings_their_local_facts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch(monkeypatch)

        context = await build_peer_context(USER_ID, ["Où en suis-je avec Alice Vernier ?"])

        assert "Alice Vernier" in context
        assert "Envoyer le devis" in context
        assert "Point chantier" in context
        assert "Je t'appelle demain" in context

    async def test_an_indirect_mention_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ "ma femme" is resolved upstream; the resolved name is passed in too."""
        calls = _patch(monkeypatch)

        await build_peer_context(USER_ID, ["Quand ai-je appelé ma femme ?", "Alice Vernier"])

        assert calls["details_for"] == ["Alice Vernier"]

    async def test_only_one_peer_is_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Reading every named peer would multiply the DB cost of a single turn."""
        calls = _patch(monkeypatch, peers=["Alice Vernier", "Marie Martin"])

        await build_peer_context(USER_ID, ["Point avec Alice Vernier et Marie Martin"])

        assert len(calls["details_for"]) == 1


class TestTheScopeIsSovereign:
    async def test_an_unticked_section_is_not_injected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scope = RelationOverviewScope(
            sections=[s for s in OverviewSection if s is not OverviewSection.CALLS]
        )
        _patch(monkeypatch, scope=scope)

        context = await build_peer_context(USER_ID, ["Alice Vernier ?"])

        assert "Envoyer le devis" in context
        assert "Point chantier" not in context

    async def test_clearing_every_local_section_injects_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch(monkeypatch, scope=RelationOverviewScope(sections=[]))

        assert await build_peer_context(USER_ID, ["Alice Vernier ?"]) == ""

    async def test_memories_are_never_injected_here(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """They already arrive through semantic relevance; twice would double
        their weight in the prompt."""
        _patch(
            monkeypatch,
            detail=_detail(memories=[SimpleNamespace(id="m1", content="SECRET-MEMORY")]),
        )

        assert "SECRET-MEMORY" not in await build_peer_context(USER_ID, ["Alice Vernier ?"])

    async def test_the_item_cap_is_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        many = [
            SimpleNamespace(subject=f"Sujet {i}", direction="i_owe", days_open=i) for i in range(20)
        ]
        _patch(
            monkeypatch,
            scope=RelationOverviewScope(max_items=2),
            detail=_detail(open_loops=many),
        )

        context = await build_peer_context(USER_ID, ["Alice Vernier ?"])

        assert "Sujet 0" in context
        assert "Sujet 5" not in context


class TestNothingIsInjectedWithoutCause:
    async def test_no_peer_named(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch(monkeypatch)

        assert await build_peer_context(USER_ID, ["Quel temps fera-t-il demain ?"]) == ""

    async def test_a_substring_is_not_a_mention(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A false positive here leaks one person's private data into a turn
        that is not about them."""
        calls = _patch(monkeypatch, peers=["Marie Martin", "Léa"])

        context = await build_peer_context(USER_ID, ["Ils vont se marier en juin"])

        assert context == ""
        assert calls["details_for"] == []

    async def test_no_connections_at_all(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch(monkeypatch, peers=[])

        assert await build_peer_context(USER_ID, ["Alice Vernier ?"]) == ""

    async def test_the_flag_gates_everything(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _patch(monkeypatch)
        monkeypatch.setattr(settings, "peer_context_injection_enabled", False, raising=False)

        assert await build_peer_context(USER_ID, ["Alice Vernier ?"]) == ""
        assert calls["details_for"] == []

    async def test_peers_feature_off_gates_everything(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _patch(monkeypatch)
        monkeypatch.setattr(settings, "peers_enabled", False, raising=False)

        assert await build_peer_context(USER_ID, ["Alice Vernier ?"]) == ""
        assert calls["details_for"] == []

    async def test_a_peer_with_no_local_facts_injects_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty block would tell the model "there is nothing", which is a
        claim about data it was never shown."""
        _patch(monkeypatch, detail=_detail(open_loops=[], recent_calls=[], peer_messages=[]))

        assert await build_peer_context(USER_ID, ["Alice Vernier ?"]) == ""


class TestItReachesTheResponsePrompt:
    """A block nobody injects into the prompt is a block that does nothing."""

    def test_the_block_is_wrapped_and_present(self) -> None:
        from src.domains.agents.prompts import get_response_prompt

        prompt = get_response_prompt(
            user_query="Où en suis-je avec Alice ?",
            peer_context="### Engagements en cours\n- Envoyer le devis",
        )

        assert "<PeerContext>" in prompt
        assert "Envoyer le devis" in prompt

    def test_no_context_leaves_no_empty_section(self) -> None:
        from src.domains.agents.prompts import get_response_prompt

        prompt = get_response_prompt(user_query="Quel temps fait-il ?")

        assert "<PeerContext>" not in prompt


class TestFailureIsNeverFatal:
    async def test_a_read_failure_degrades_to_no_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch(monkeypatch)

        async def _boom(*_args, **_kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(mod, "_relation_detail", _boom)

        assert await build_peer_context(USER_ID, ["Alice Vernier ?"]) == ""
