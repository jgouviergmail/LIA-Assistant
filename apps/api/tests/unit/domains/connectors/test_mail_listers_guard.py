"""No module lists a mailbox without saying whether it tells where a message stands (ADR-379).

The assistant offered to answer mail the person had already answered because every
surface listed mail on its own — the chat tool, the heartbeat, the briefing, the
relationship views, the Tools — and none of them asked the mailbox what happened next.
Found one surface at a time, the next one forgets again. So the family is enumerated,
the way ``direct_client_callers`` enumerates the modules that reach a provider: the
list this guard walks is the CALL graph, complete by construction — a module cannot
list a mailbox without calling its listing.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.domains.connectors.mail_listers import MAIL_LISTERS, Standing

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[4] / "src"

#: The client layer implements the listing; everything else calls it.
_CLIENT_LAYER = "domains/connectors/clients/"
#: How a mailbox is listed: the search every client shares (``EmailClientProtocol``),
#: and Gmail's own search under labels.
_LISTINGS = frozenset({"search_emails", "search_in_labels"})
#: The door (``domains/connectors/mail_reply_states``), by what each standing asks of
#: it: a conversation read, the mailbox's own mark alone, or nothing.
_DOOR = frozenset({"attach_reply_states", "reply_states_of"})
_MARK = frozenset({"answered_mark"})
_THROUGH = {
    Standing.SITUATED: _DOOR,
    Standing.MARKED: _MARK,
    Standing.NOT_SITUATED: frozenset[str](),
}


def _called(tree: ast.AST) -> set[str]:
    """Every name a module CALLS: a function, or a method by its attribute."""
    return {
        node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }


def _calls_of(relative: str) -> set[str]:
    return _called(ast.parse((_SRC / relative).read_text(encoding="utf-8")))


def _listers() -> set[str]:
    """Every module outside the client layer that calls a mailbox's listing."""
    found: set[str] = set()
    for path in _SRC.rglob("*.py"):
        relative = path.relative_to(_SRC).as_posix()
        if relative.startswith(_CLIENT_LAYER):
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        if any(listing in source for listing in _LISTINGS) and _LISTINGS & _calls_of(relative):
            found.add(relative)
    return found


class TestEveryListerIsDeclared:
    def test_no_lister_is_undeclared(self) -> None:
        undeclared = sorted(_listers() - set(MAIL_LISTERS))
        assert not undeclared, (
            f"modules listing a mailbox with nothing said of reply states: {undeclared} — "
            "declare each in MAIL_LISTERS: SITUATED (it goes through "
            "mail_reply_states) or NOT_SITUATED with the reason a reply state says nothing there"
        )

    def test_no_declaration_outlives_its_module(self) -> None:
        stale = sorted(set(MAIL_LISTERS) - _listers())
        assert not stale, f"declared but no longer lists a mailbox: {stale}"

    def test_the_guard_walks_something(self) -> None:
        """A guard that runs for no case guards nothing."""
        assert "domains/agents/tools/emails_tools.py" in _listers()


def _mismatch(standing: Standing, called: set[str]) -> str | None:
    """Why what a module calls of the door is not what its standing declares, if so."""
    asked = _THROUGH[standing]
    if asked and not asked & called:
        return f"declared {standing.name} but never calls {sorted(asked)}"
    beyond = sorted(((_DOOR | _MARK) - asked) & called)
    return f"declared {standing.name} but calls {beyond}" if beyond else None


class TestADeclarationIsWhatTheModuleDoes:
    def test_every_standing_says_what_it_asks_of_the_door(self) -> None:
        assert set(_THROUGH) == set(Standing)

    def test_a_lister_goes_through_the_part_of_the_door_it_declares_and_no_other(self) -> None:
        wrong = {
            module: reason
            for module, lister in MAIL_LISTERS.items()
            if (reason := _mismatch(lister.standing, _calls_of(module))) is not None
        }
        assert not wrong, f"a declaration that is not what its module does: {wrong}"

    @pytest.mark.parametrize(
        ("standing", "called"),
        [
            (Standing.SITUATED, {"search_emails"}),  # lists, and asks the door nothing
            (Standing.MARKED, {"search_emails", "reply_states_of"}),  # reads conversations
            (Standing.MARKED, {"search_emails", "answered_mark", "attach_reply_states"}),
            (Standing.NOT_SITUATED, {"search_emails", "answered_mark"}),
            (Standing.NOT_SITUATED, {"search_emails", "attach_reply_states"}),
        ],
    )
    def test_a_false_declaration_is_refused(self, standing: Standing, called: set[str]) -> None:
        """A guard that runs for no failing case guards nothing."""
        assert _mismatch(standing, called) is not None

    def test_every_declaration_gives_a_reason_one_can_check(self) -> None:
        """A one-word reason is a box ticked, not a decision made."""
        thin = sorted(
            module for module, lister in MAIL_LISTERS.items() if len(lister.reason.split()) < 5
        )
        assert not thin, f"reasons too thin to be checked: {thin}"


def test_the_reason_the_discussion_source_reads_no_conversation_still_holds() -> None:
    """A written reason is checked while it stands.

    A proactive discussion's evidence is versioned and re-read at its version, so a
    conversation would be read strictly on every page: one listing, one read per hit and
    one conversation read per hit on a mailbox that reads one thread per call. The day
    a read's allowance holds that, the source must be situated, not told the mark alone.
    """
    from src.core.config import settings

    strict_page_calls = 1 + 2 * settings.discussion_research_item_limit
    assert strict_page_calls > settings.discussion_read_call_limit, (
        "a discussion read now affords a strict conversation read: situate "
        "domains/connectors/discussion_sources.py (its version must then carry the state)"
    )


class TestTheDetectorsReadCallsNotWords:
    """A docstring saying a module lists or situates is not a module that does."""

    def test_a_listing_call_is_seen(self) -> None:
        tree = ast.parse("async def f(client):\n    return await client.search_emails('in:inbox')")
        assert _LISTINGS & _called(tree)

    def test_a_mention_is_not_a_call(self) -> None:
        tree = ast.parse('"""This module uses search_emails and attach_reply_states."""\nX = 1')
        assert not (_LISTINGS | _DOOR) & _called(tree)

    def test_a_door_call_is_seen_whichever_way_it_is_imported(self) -> None:
        direct = ast.parse(
            "async def f(c, m):\n    await attach_reply_states(c, m, user_timezone=None)"
        )
        qualified = ast.parse(
            "async def f(c, m):\n    return await door.reply_states_of(c, m, user_timezone=None)"
        )
        assert _DOOR & _called(direct) and _DOOR & _called(qualified)
