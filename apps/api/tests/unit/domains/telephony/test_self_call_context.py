"""Unit tests for the context an owner call carries (lot 4).

The block is assembled from the SAME readers the chat uses, section by
section, under a token budget, in a priority order, with every cut stated —
and every section actually opened is filed on the ``phone_call`` consultation
surface. The fetchers are injected here so the tests exercise the assembly
and the register, not five repositories.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

import src.domains.telephony.self_call_context as ctx
from src.core.config import settings
from src.domains.telephony.budget import fit_lines, token_count
from src.domains.telephony.self_call_context import (
    SECTION_ORDER,
    ContextSection,
    build_owner_context,
)


@pytest.mark.unit
def test_fit_lines_keeps_whole_lines_in_order_and_states_the_cut() -> None:
    lines = [f"line {i} " + " ".join(["word"] * 20) for i in range(30)]
    text, cut = fit_lines(lines, budget_tokens=token_count("\n".join(lines[:5])) + 2)
    kept = text.splitlines()
    assert kept[0] == lines[0]
    assert cut is True
    assert 1 < len(kept) < 30
    assert kept == lines[: len(kept)]


@pytest.mark.unit
def test_fit_lines_always_keeps_the_first_line() -> None:
    text, cut = fit_lines(["a very long first line " * 50, "second"], budget_tokens=3)
    assert text.startswith("a very long first line")
    assert cut is True


@pytest.mark.unit
def test_fit_lines_under_budget_keeps_everything() -> None:
    text, cut = fit_lines(["one", "two"], budget_tokens=1000)
    assert text == "one\ntwo"
    assert cut is False


def _fetchers(**sections: list[str] | Exception | None) -> dict:
    async def make(value):  # noqa: ANN001, ANN202
        if isinstance(value, Exception):
            raise value
        return value

    return {key: (lambda v=value: make(v)) for key, value in sections.items()}


def _capture_recorder(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    recorded: list[dict] = []
    monkeypatch.setattr(ctx, "record_surface_consultations", lambda **kw: recorded.append(kw))
    return recorded


@pytest.mark.unit
async def test_sections_are_rendered_in_priority_order_with_localized_headings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _capture_recorder(monkeypatch)
    text = await build_owner_context(
        uuid4(),
        language="fr",
        rich_context_enabled=True,
        fetchers=_fetchers(
            memories=["likes early mornings"],
            agenda=["10:00 dentist"],
            reminders=["call the bank"],
            open_loops=["answer Y about the quote"],
            recent_exchanges=["user: hello", "assistant: hi"],
        ),
    )
    positions = [
        text.index(line) for line in ("early mornings", "dentist", "bank", "quote", "hello")
    ]
    assert positions == sorted(positions)
    assert "## " in text
    (record,) = recorded
    assert record["surface"] == "phone_call"
    assert list(record["opened"]) == list(SECTION_ORDER)
    assert list(record["failed"]) == []


@pytest.mark.unit
async def test_a_failed_section_is_filed_failed_and_the_block_still_renders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _capture_recorder(monkeypatch)
    text = await build_owner_context(
        uuid4(),
        language="en",
        rich_context_enabled=True,
        fetchers=_fetchers(
            memories=["fact"],
            agenda=RuntimeError("calendar down"),
            reminders=[],
            open_loops=[],
            recent_exchanges=[],
        ),
    )
    assert "fact" in text
    (record,) = recorded
    assert "agenda" in list(record["failed"])
    assert "agenda" in list(record["opened"])


@pytest.mark.unit
async def test_a_source_the_person_does_not_have_is_not_filed_as_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No calendar connector: nothing was opened, so nothing is filed — a
    consultation row for a source that does not exist would be a false
    claim (ADR-263: a cache hit is not a consultation, and neither is this)."""
    recorded = _capture_recorder(monkeypatch)
    text = await build_owner_context(
        uuid4(),
        language="en",
        rich_context_enabled=True,
        fetchers=_fetchers(
            memories=["fact"], agenda=None, reminders=[], open_loops=[], recent_exchanges=[]
        ),
    )
    assert "fact" in text
    (record,) = recorded
    assert "agenda" not in list(record["opened"])
    assert "reminders" in list(record["opened"])  # an EMPTY section was still opened


@pytest.mark.unit
async def test_the_switch_off_renders_nothing_and_opens_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _capture_recorder(monkeypatch)
    calls: list[str] = []

    async def spy() -> list[str]:
        calls.append("opened")
        return ["x"]

    text = await build_owner_context(
        uuid4(),
        language="en",
        rich_context_enabled=False,
        fetchers=dict.fromkeys(SECTION_ORDER, spy),
    )
    assert text == ""
    assert calls == []
    assert recorded == []


@pytest.mark.unit
async def test_the_budget_is_spent_in_priority_order_and_the_cut_is_stated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capture_recorder(monkeypatch)
    monkeypatch.setattr(settings, "telephony_self_context_max_tokens", 60, raising=False)
    text = await build_owner_context(
        uuid4(),
        language="en",
        rich_context_enabled=True,
        fetchers=_fetchers(
            memories=[f"memory {i} " + "word " * 10 for i in range(20)],
            agenda=["an event that will not fit"],
            reminders=[],
            open_loops=[],
            recent_exchanges=[],
        ),
    )
    assert "memory 0" in text
    assert "will not fit" not in text
    assert token_count(text) <= 60 + 40  # the headings and the cut notice
    assert "more not shown" in text


@pytest.mark.unit
async def test_empty_sections_are_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = _capture_recorder(monkeypatch)
    text = await build_owner_context(
        uuid4(),
        language="de",
        rich_context_enabled=True,
        fetchers=_fetchers(
            memories=[], agenda=[], reminders=["x"], open_loops=[], recent_exchanges=[]
        ),
    )
    assert text.count("## ") == 1
    # Empty is still opened: the calendar WAS read, it just held nothing.
    (record,) = recorded
    assert set(record["opened"]) == set(SECTION_ORDER)


@pytest.mark.unit
def test_context_section_declares_its_domain_on_the_surface() -> None:
    from src.domains.shared.consultation_surfaces import CONSULTATION_SURFACES

    surface = CONSULTATION_SURFACES["phone_call"]
    for key in SECTION_ORDER:
        assert key in surface.domains, key
    assert isinstance(ContextSection(key="agenda", lines=["x"]), ContextSection)


# ---------------------------------------------------------------------------
# The recent exchanges reach the voice as PROSE (cold review, 2026-09-16)
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_recent_exchanges_are_flattened_visible_only_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An assistant answer is often an HTML card: the voice must read its
    words, not its markup — through the flattener the caller hands in, since
    the flattening lives in ``agents`` which telephony must not import."""
    from types import SimpleNamespace
    from uuid import uuid4

    import src.domains.conversations.repository as crepo
    import src.infrastructure.cache.conversation_cache as ccache
    import src.infrastructure.database.session as dbsession
    from src.domains.telephony.self_call_context import _fetch_recent_exchanges

    seen: dict[str, object] = {}

    async def _conversation_id(_user_id):  # noqa: ANN001
        return str(uuid4())

    class _Repo:
        def __init__(self, _db) -> None:  # noqa: ANN001
            pass

        async def get_messages_for_conversation(self, conversation_id, **kwargs):  # noqa: ANN001
            seen["kwargs"] = kwargs
            return [
                SimpleNamespace(
                    role="assistant", content="<div class='lia-card'>Dentist at ten</div>"
                ),
                SimpleNamespace(role="user", content="  what's   next  "),
            ]

    class _Db:
        async def __aenter__(self):  # noqa: ANN204
            return object()

        async def __aexit__(self, *exc):  # noqa: ANN002, ANN204
            return False

    monkeypatch.setattr(ccache, "get_conversation_id_cached", _conversation_id)
    monkeypatch.setattr(crepo, "ConversationRepository", _Repo)
    monkeypatch.setattr(dbsession, "get_db_context", lambda: _Db())

    lines = await _fetch_recent_exchanges(
        uuid4(),
        flatten=lambda text: text.replace("<div class='lia-card'>", "").replace("</div>", ""),
    )

    assert lines == ["user: what's next", "assistant: Dentist at ten"]
    assert seen["kwargs"].get("include_hidden", False) is False  # type: ignore[union-attr]


@pytest.mark.unit
def test_default_fetchers_require_the_flattener() -> None:
    """Like the memory fetcher: a caller cannot forget it and ship a voice
    that reads HTML aloud."""
    from uuid import uuid4

    from src.domains.telephony.self_call_context import default_fetchers

    async def _memories() -> list[str]:
        return []

    with pytest.raises(TypeError):
        default_fetchers(uuid4(), language="fr", timezone="UTC", memory_fetcher=_memories)  # type: ignore[call-arg]
