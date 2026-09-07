"""The 360° evidence assembly, frozen against what it produced before extraction.

``get_person_overview_tool`` owned this assembly. The debrief needs the same
answer, and a second implementation would make two surfaces disagree about who
someone is and what was read about them — the defect class ADR-185 exists to
prevent. So the assembly moved to ``relations/overview`` and the tool became its
first consumer.

``golden_overview_payloads.json`` was captured from the PRE-extraction tool over
a scope matrix. Every case below must reproduce it byte for byte: the extraction
is a refactor, and a refactor that changes an answer is not one.

The one thing that MUST change is measured separately, in
:class:`TestItOnlyPaysForWhatTheScopeAsks` — the pre-extraction tool read the
providers even when the reader had excluded every provider section.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.tools import person_tools
from src.domains.relations.overview import evidence as evidence_module
from src.domains.relations.overview import fallback as fallback_module
from src.domains.relations.overview_scope import (
    OverviewDirection,
    OverviewRole,
    OverviewSection,
)
from tests.unit.domains.relations.overview.fixtures import (
    DEFAULT_MEMORIES,
    EMPTY_CONTEXT,
    EMPTY_DETAIL,
    ERROR_CONTEXT,
    NO_ADDRESS_CONTEXT,
    PERSON,
    USER_ID,
    context,
    detail,
    scope,
)

pytestmark = pytest.mark.unit

GOLDEN = json.loads(
    (Path(__file__).parent / "golden_overview_payloads.json").read_text(encoding="utf-8")
)

#: The matrix, exactly as the golden file was captured from.
CASES: dict[str, dict[str, object]] = {
    "default": {},
    "no_sections": {"scope": scope(sections=[])},
    "local_only": {
        "scope": scope(
            sections=[
                OverviewSection.OPEN_LOOPS,
                OverviewSection.CALLS,
                OverviewSection.MEMORIES,
                OverviewSection.PEER_MESSAGES,
            ]
        )
    },
    "provider_only": {
        "scope": scope(
            sections=[
                OverviewSection.CONTACT,
                OverviewSection.EMAILS,
                OverviewSection.EVENTS,
            ]
        )
    },
    "emails_only": {"scope": scope(sections=[OverviewSection.EMAILS])},
    "events_only": {"scope": scope(sections=[OverviewSection.EVENTS])},
    "contact_only": {"scope": scope(sections=[OverviewSection.CONTACT])},
    "received_only": {"scope": scope(directions=[OverviewDirection.RECEIVED])},
    "organizer_only": {"scope": scope(roles=[OverviewRole.ORGANIZER])},
    "max_items_1": {"scope": scope(max_items=1)},
    "max_items_25": {"scope": scope(max_items=25)},
    "memories_unreadable": {"memories": None},
    "memories_empty": {"memories": []},
    "no_peer_link": {"detail": detail(peer_link=None, is_peer=False)},
    "provider_error": {"context": ERROR_CONTEXT},
    "no_address_with_fallback": {
        "context": NO_ADDRESS_CONTEXT,
        "by_name": (
            [{"subject": "S", "from": "f", "date": "1", "snippet": "x"}],
            [{"title": "T", "start": "2026-08-02", "location": None}],
        ),
    },
    "no_address_without_fallback": {"context": NO_ADDRESS_CONTEXT, "by_name": ([], [])},
    "empty_relation": {
        "detail": EMPTY_DETAIL,
        "context": EMPTY_CONTEXT,
        "memories": [],
    },
}

#: How many times the provider half may be read, per case. Everything the
#: reader excluded costs ZERO external calls — the pre-extraction tool charged
#: one read for every case in this table, including the two that want none.
EXPECTED_CONTEXT_READS: dict[str, int] = {
    "no_sections": 0,
    "local_only": 0,
    "memories_unreadable": 1,
    "memories_empty": 1,
}


async def _run_tool(**over: object) -> object:
    """Invoke the tool with every read stubbed at the new module's seam."""
    scope_value = over.get("scope") or scope()
    service = SimpleNamespace(
        get_overview_scope=AsyncMock(return_value=scope_value),
        build_detail=AsyncMock(
            return_value=over["detail"] if over.get("detail") is not None else detail()
        ),
    )
    ctx_service = SimpleNamespace(
        build=AsyncMock(
            return_value=over["context"] if over.get("context") is not None else context()
        )
    )
    mails, events = over.get("by_name") or ([], [])  # type: ignore[misc]
    memories = over["memories"] if "memories" in over else DEFAULT_MEMORIES
    with (
        patch.object(person_tools, "RelationsService", return_value=service),
        patch.object(evidence_module, "RelationsService", return_value=service),
        patch.object(evidence_module, "RelationContextService", return_value=ctx_service),
        patch.object(fallback_module, "fetch_recent_emails", AsyncMock(return_value=mails)),
        patch.object(fallback_module, "fetch_upcoming_events", AsyncMock(return_value=events)),
        patch.object(evidence_module, "fetch_person_memories", AsyncMock(return_value=memories)),
        patch.object(
            person_tools,
            "validate_runtime_config",
            return_value=SimpleNamespace(user_id=str(USER_ID)),
        ),
    ):
        result = await person_tools.get_person_overview_tool.coroutine(
            person_name=PERSON,
            runtime=SimpleNamespace(context=SimpleNamespace(user_id=str(USER_ID))),
        )
    return result, ctx_service.build.await_count


class TestItAnswersExactlyWhatItAnsweredBefore:
    """The extraction is a refactor. A refactor that changes an answer is not one."""

    @pytest.mark.parametrize("case", sorted(CASES))
    async def test_payload_matches_the_frozen_capture(self, case: str) -> None:
        result, _ = await _run_tool(**CASES[case])
        expected = GOLDEN[case]
        # Round-tripped through JSON so the comparison is on the SERIALISED
        # shape — which is what the model actually receives.
        actual = json.loads(json.dumps(result.structured_data, default=str, sort_keys=True))
        assert actual == json.loads(json.dumps(expected["structured_data"], sort_keys=True))

    @pytest.mark.parametrize("case", sorted(CASES))
    async def test_message_matches_the_frozen_capture(self, case: str) -> None:
        """The message field is the only channel reaching the response prompt."""
        result, _ = await _run_tool(**CASES[case])
        assert result.message == GOLDEN[case]["message"]

    def test_the_matrix_and_the_golden_file_cover_the_same_cases(self) -> None:
        """A case added on one side only would silently stop being checked."""
        assert set(CASES) == set(GOLDEN)


class TestItOnlyPaysForWhatTheScopeAsks:
    """A selection the system enforces must also be the one it BILLS for.

    Reading the providers for sections the reader excluded costs up to eleven
    external API calls — three mail searches per address, three addresses, plus
    the contact card and the calendar — and every one of them is dropped before
    the payload is built. That is ADR-184's trap pointing at cost: a selection
    published, then not honoured.
    """

    @pytest.mark.parametrize(
        "case,expected", sorted((k, v) for k, v in EXPECTED_CONTEXT_READS.items())
    )
    async def test_provider_reads_follow_the_scope(self, case: str, expected: int) -> None:
        _, reads = await _run_tool(**CASES[case])
        assert reads == expected

    async def test_every_other_case_still_reads_the_providers_once(self) -> None:
        """Narrowing must not become "never look" — the answer would be empty."""
        for case in sorted(set(CASES) - set(EXPECTED_CONTEXT_READS)):
            _, reads = await _run_tool(**CASES[case])
            assert reads == 1, case
