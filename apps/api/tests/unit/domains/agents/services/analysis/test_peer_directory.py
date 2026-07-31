"""Peer-connection awareness for the query analyzer (D1, defect 2026-07-30).

Proved defect (dev logs, request ids 303d7ce3 / 43e9bded / c4a35e4e): "Est-ce
que Jerome G est dispo demain ?" was analyzed ``primary_domain=event,
secondary_domains=["contact"]`` three times out of four. The peer tools were
therefore never candidates; the planner scheduled ``get_events_tool`` (the
ASKING user's own calendar) plus ``get_contacts_tool``, both failed the scope
check, and the whole plan was invalidated — the user was told "no service is
configured" while the connection, the share and the peer's calendar were all
healthy. The SAME sentence had routed ``secondary_domains=["peer"]`` at
13:23:34, which is what makes the failure a coin toss rather than a bug with a
stable repro.

Root cause: nothing tells the analyzer that "Jerome G" is another USER of this
instance. The ``peer`` domain description says "Connections with OTHER USERS
of this LIA instance" — a correct description the LLM cannot apply, because
the set of those users is exactly the fact it is missing.

This module is the fix in two layers, tested here:

1. **Awareness** (root cause): the user's accepted connections are injected in
   the analyzer prompt, so the LLM can recognise the name.
2. **Determinism** (guarantee): when a connected peer is named and the LLM
   still answered with a peer-confusable domain, ``peer`` is ADDED. Additive
   on purpose — "suis-je libre demain pour voir Jerome" legitimately needs the
   user's own calendar too, so nothing is ever removed.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.services.analysis.peer_directory import (
    PEER_CONFUSABLE_DOMAINS,
    PEER_DIRECTORY_EMPTY,
    PEER_DOMAIN,
    apply_peer_domain_correction,
    detect_mentioned_peers,
    format_peer_directory,
    load_connected_peer_names,
)

PEERS = ["Jérôme G"]


# =========================================================================
# detect_mentioned_peers — recall
# =========================================================================


def test_exact_display_name_is_detected():
    """The plain case: the user types the peer's name as stored."""
    assert detect_mentioned_peers(["Est-ce que Jérôme G est dispo ?"], PEERS) == ["Jérôme G"]


def test_accent_and_case_folded_match_is_detected():
    """THE production defect: user typed "Jerome G", the row holds "Jérôme G".

    Accent folding is what the peer tools already do (``fold_name``); the
    analyzer-side detection must agree with them, or the routing and the tool
    would disagree on who exists.
    """
    assert detect_mentioned_peers(["Jerome G est-il disponible demain à 10h ?"], PEERS) == [
        "Jérôme G"
    ]


def test_first_name_alone_is_detected():
    """Users rarely retype a full name once the conversation is underway."""
    assert detect_mentioned_peers(["est-ce que jerome est dispo demain ?"], PEERS) == ["Jérôme G"]


def test_match_found_only_in_the_english_pivot():
    """The analyzer reasons on the English pivot — it must be searched too."""
    texts = ["est-il dispo ?", "is Jerome G available tomorrow?"]
    assert detect_mentioned_peers(texts, PEERS) == ["Jérôme G"]


def test_match_found_only_in_a_resolved_reference():
    """ "mon frère" resolves to the peer's name — the mapping VALUE carries it.

    Without this source, an entirely legitimate phrasing ("mon frère est-il
    dispo ?") is invisible to the detection, because the name never appears in
    what the user typed.
    """
    assert detect_mentioned_peers(["mon frère est-il dispo ?", "Jérôme G"], PEERS) == ["Jérôme G"]


def test_hyphenated_peer_name_matches_when_written_with_a_space():
    """Tokens split on any non-alphanumeric run, so punctuation never hides a name."""
    assert detect_mentioned_peers(["jean pierre est dispo ?"], ["Jean-Pierre Dupont"]) == [
        "Jean-Pierre Dupont"
    ]


def test_several_peers_are_all_reported_without_duplicates():
    """One name repeated across several texts is reported once."""
    peers = ["Jérôme G", "Marie Dupont"]
    texts = ["Jerome et Marie sont-ils dispos ?", "are Jerome and Marie available?"]
    assert detect_mentioned_peers(texts, peers) == ["Jérôme G", "Marie Dupont"]


# =========================================================================
# detect_mentioned_peers — precision (no false positives)
# =========================================================================


def test_substring_inside_a_longer_word_is_not_a_match():
    """ "Jean" must not fire on "jeans" — word boundaries, never substrings."""
    assert detect_mentioned_peers(["j'ai acheté des jeans"], ["Jean Dupont"]) == []


def test_short_token_alone_is_not_a_match():
    """The "G" of "Jérôme G" must never match on its own.

    A one- or two-letter token appears in nearly every sentence; matching it
    would make the correction fire on every turn.
    """
    assert detect_mentioned_peers(["G comme dans gagné, ok ?"], PEERS) == []


def test_unrelated_query_matches_nothing():
    assert detect_mentioned_peers(["quelle est la météo demain ?"], PEERS) == []


@pytest.mark.parametrize("texts", [[], [""], [None], [None, ""]])
def test_empty_texts_match_nothing(texts):
    assert detect_mentioned_peers(texts, PEERS) == []


@pytest.mark.parametrize("peers", [[], [""], ["   "], [None]])
def test_empty_peer_directory_matches_nothing(peers):
    """A user with no connections must never pay for this feature."""
    assert detect_mentioned_peers(["Jerome G est dispo ?"], peers) == []


# =========================================================================
# apply_peer_domain_correction
# =========================================================================


def test_production_defect_is_corrected():
    """The exact analyzer output of request 303d7ce3 gains the peer domain."""
    assert apply_peer_domain_correction(["event", "contact"], ["Jérôme G"]) == [
        "event",
        "contact",
        PEER_DOMAIN,
    ]


def test_correction_is_additive_and_preserves_order():
    """Nothing is removed: the user's own calendar may still be relevant."""
    corrected = apply_peer_domain_correction(["task", "event"], ["Jérôme G"])
    assert corrected[:2] == ["task", "event"]
    assert corrected[-1] == PEER_DOMAIN


def test_peer_already_present_is_not_duplicated():
    """The 13:23 run already routed correctly — it must be left untouched."""
    assert apply_peer_domain_correction(["event", PEER_DOMAIN], ["Jérôme G"]) == [
        "event",
        PEER_DOMAIN,
    ]


def test_no_mention_leaves_domains_untouched():
    assert apply_peer_domain_correction(["event", "contact"], []) == ["event", "contact"]


def test_non_confusable_domain_is_left_untouched():
    """ "envoie un mail à Jerome" is an email turn, not a peer read.

    The gate is what keeps a common first name from dragging the peer tools
    into every plan that happens to contain it.
    """
    assert apply_peer_domain_correction(["email"], ["Jérôme G"]) == ["email"]


def test_empty_domains_are_left_untouched():
    """A conversation turn carries no domain — it must not be promoted."""
    assert apply_peer_domain_correction([], ["Jérôme G"]) == []


def test_every_confusable_domain_triggers_the_correction():
    """Each gate member is exercised, so shrinking the set breaks a test."""
    for domain in PEER_CONFUSABLE_DOMAINS:
        assert apply_peer_domain_correction([domain], ["Jérôme G"]) == [domain, PEER_DOMAIN]


def test_gate_covers_exactly_the_shared_and_confusable_domains():
    """Contract: calendar + tasks are shareable (spec A1); contact is the confusion."""
    assert PEER_CONFUSABLE_DOMAINS == frozenset({"event", "task", "contact"})


def test_correction_never_mutates_the_caller_list():
    """The analyzer keeps `original_domains` for its debug payload."""
    domains = ["event"]
    apply_peer_domain_correction(domains, ["Jérôme G"])
    assert domains == ["event"]


# =========================================================================
# format_peer_directory
# =========================================================================


def test_directory_block_lists_display_names():
    block = format_peer_directory(["Jérôme G", "Marie Dupont"])
    assert "Jérôme G" in block
    assert "Marie Dupont" in block


def test_empty_directory_block_is_an_explicit_sentinel():
    """An empty section would read as a truncated prompt to the LLM."""
    assert format_peer_directory([]) == PEER_DIRECTORY_EMPTY


def test_directory_block_is_bounded():
    """A large address book must not blow the analyzer prompt budget."""
    block = format_peer_directory([f"Peer Number {i}" for i in range(500)])
    assert len(block.splitlines()) <= 51


def test_directory_block_escapes_prompt_braces():
    """`str.format` runs on this template — a brace in a name would crash it.

    ``full_name`` is user-controlled free text, so this is reachable input,
    not a hypothetical.
    """
    assert "{" not in format_peer_directory(["Ann {x} Lee"]).replace("{{", "")


# =========================================================================
# load_connected_peer_names
# =========================================================================


@pytest.mark.asyncio
async def test_disabled_flag_short_circuits_before_any_db_access():
    """Deployments without peers must not pay one query per chat turn."""
    with (
        patch("src.core.config.settings.peers_enabled", False),
        patch(
            "src.infrastructure.database.session.get_db_context",
            side_effect=AssertionError("must not touch the database"),
        ),
    ):
        assert await load_connected_peer_names(str(uuid4())) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", ["", "   ", "not-a-uuid", None])
async def test_unusable_user_id_yields_no_names(user_id):
    """`langgraph_user_id` is absent on automated runs — never raise there."""
    with patch("src.core.config.settings.peers_enabled", True):
        assert await load_connected_peer_names(user_id) == []


@pytest.mark.asyncio
async def test_enabled_flag_returns_repository_display_names():
    user_id = uuid4()
    repo = MagicMock()
    repo.list_accepted_peer_display_names = AsyncMock(return_value=["Jérôme G"])
    session = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("src.core.config.settings.peers_enabled", True),
        patch(
            "src.domains.agents.services.analysis.peer_directory.get_db_context",
            return_value=ctx,
        ),
        patch(
            "src.domains.agents.services.analysis.peer_directory.PeersRepository",
            return_value=repo,
        ),
    ):
        assert await load_connected_peer_names(str(user_id)) == ["Jérôme G"]

    repo.list_accepted_peer_display_names.assert_awaited_once_with(user_id)


# =========================================================================
# Registry coherence & PII discipline
# =========================================================================


def test_peer_domain_exists_in_the_taxonomy():
    """A renamed domain key would make the correction add a dead domain.

    Domain names are strings on both sides of a registry lookup, so nothing
    but this assertion connects them.
    """
    from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

    assert PEER_DOMAIN in DOMAIN_REGISTRY


def test_every_confusable_domain_exists_in_the_taxonomy():
    """A gate entry that matches no domain can never fire — silent dead code."""
    from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

    assert PEER_CONFUSABLE_DOMAINS <= set(DOMAIN_REGISTRY)


def test_correction_never_logs_a_peer_name_at_info(caplog):
    """Peer names are PII: counters and domains at INFO, names at DEBUG only."""
    import logging

    with caplog.at_level(logging.INFO):
        apply_peer_domain_correction(["event"], ["Jérôme G"])

    emitted = " ".join(record.getMessage() for record in caplog.records)
    assert "peer_domain_correction_applied" in emitted
    assert "Jérôme" not in emitted
    assert "Jerome" not in emitted


@pytest.mark.asyncio
async def test_database_failure_degrades_to_no_names():
    """Routing must never break because the peers table is unreachable.

    Losing the directory costs the awareness layer; raising here would cost
    the whole turn.
    """
    with (
        patch("src.core.config.settings.peers_enabled", True),
        patch(
            "src.domains.agents.services.analysis.peer_directory.get_db_context",
            side_effect=RuntimeError("pool exhausted"),
        ),
    ):
        assert await load_connected_peer_names(str(uuid4())) == []
