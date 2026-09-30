"""What a portal says is a stranger's text, type-checked and bounded (ADR-327)."""

from __future__ import annotations

import pytest

from src.domains.skill_library.portals import (
    AuditVerdict,
    SkillsShPortal,
    _entry,
    blocking_risk,
)
from tests.unit.domains.skill_library.fakes import FakeHub, audit_of, entry

pytestmark = pytest.mark.unit


class TestASearchResult:
    def test_a_github_source_is_a_repository(self) -> None:
        found = _entry(entry("acme/skills", "pdf"))
        assert found is not None and found.repository == "acme/skills"

    def test_a_site_source_is_listed_but_names_no_repository(self) -> None:
        raw = {**entry("acme/skills", "pdf"), "source": "open.example.cn"}
        found = _entry(raw)
        assert found is not None and found.repository is None

    @pytest.mark.parametrize(
        "raw",
        [
            None,
            "text",
            {**entry("acme/skills", "pdf"), "installs": "many"},
            {**entry("acme/skills", "pdf"), "name": ""},
            {**entry("acme/skills", "pdf"), "skillId": 3},
            {**entry("acme/skills", "pdf"), "name": "x" * 500},
        ],
        ids=["null", "string", "installs-text", "empty-name", "id-number", "name-too-long"],
    )
    def test_a_malformed_one_is_dropped(self, raw: object) -> None:
        assert _entry(raw) is None

    async def test_the_portal_s_answer_is_filtered_and_capped(self, hub: FakeHub) -> None:
        hub.search_results = [entry("a/b", "one"), {"bad": True}, entry("a/b", "two")]
        async with hub.client() as client:
            found = await SkillsShPortal().search(client, "pdf tools", 1)
        assert [e.skill_id for e in found] == ["one"]
        asked = next(s for s in hub.seen if s.host == "skills.sh")
        assert asked.query == {"q": ["pdf tools"], "limit": ["1"]}


class TestAnAudit:
    @pytest.mark.parametrize(
        ("risks", "level", "blocked"),
        [
            (["safe", "low"], "high", None),
            (["low", "high"], "high", "high"),
            (["critical", "medium"], "high", "critical"),
            (["medium"], "medium", "medium"),
            (["critical"], "none", None),
            (["unknown"], "low", None),
            ([], "low", None),
        ],
    )
    def test_the_worst_verdict_at_or_above_the_level_refuses(
        self, risks: list[str], level: str, blocked: str | None
    ) -> None:
        verdicts = [AuditVerdict("p", r, 0) for r in risks]
        assert blocking_risk(verdicts, level) == blocked

    async def test_an_unknown_risk_word_reads_as_unknown(self, hub: FakeHub) -> None:
        hub.audits = audit_of("pdf", snyk="catastrophic")
        async with hub.client() as client:
            found = await SkillsShPortal().audit(client, "acme/skills", ["pdf"])
        assert found == {"pdf": [AuditVerdict("snyk", "unknown", 0)]}

    async def test_an_audit_service_that_cannot_be_read_says_nothing(self, hub: FakeHub) -> None:
        hub.audits = None
        async with hub.client() as client:
            assert await SkillsShPortal().audit(client, "acme/skills", ["pdf"]) is None
