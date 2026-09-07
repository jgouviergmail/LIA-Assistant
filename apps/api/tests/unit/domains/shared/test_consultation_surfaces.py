"""One net for every surface that reads without going through a tool.

Three surfaces were fixed one after another — the briefing, the relationship
debrief, the heartbeat sweep — and each was given its own hand-written half of
a guard. Measured on this codebase 2026-09-07, after those fixes:

- the register kept a THIRD copy of all thirty-one capability names,
  hand-transcribed;
- two tables written to bridge that gap were exported and read by NOBODY;
- the boot guard walked ``get_all_tools()`` only, so none of the thirty-one was
  checked where every other completeness rule is;
- one surface checked its capabilities for orphans, the other two did not;
- and the authorship each row carries was a free string typed at three call
  sites, validated by a guard that only read two other doors.

Every property below is asserted over :data:`CONSULTATION_SURFACES` as a whole,
so a fourth surface inherits all of them by being declared — which is the only
difference between a method and three fixes.
"""

from __future__ import annotations

import pytest

from src.domains.agents.effects.models import EffectSource
from src.domains.agents.effects.treatment_labels import (
    TREATMENT_DOMAIN_OVERRIDES,
    UNKNOWN_DOMAIN,
    treatment_domain,
)
from src.domains.agents.effects.user_data_readers import CONSULTATION_RECORDERS
from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY
from src.domains.shared.consultation_surfaces import (
    CONSULTATION_SURFACES,
    capability_domains,
    record_surface_consultations,
    surface_of,
)

pytestmark = pytest.mark.unit

_SURFACES = sorted(CONSULTATION_SURFACES)


class TestTheTwoRegistriesNameTheSameSurfaces:
    """A vocabulary for a surface nobody declares — or the reverse — is drift."""

    def test_every_declared_reader_has_a_vocabulary(self) -> None:
        missing = sorted(set(CONSULTATION_RECORDERS) - set(CONSULTATION_SURFACES))
        assert not missing, (
            f"declared as recording consultations but naming no capabilities: "
            f"{missing} — a surface that records under names the register "
            "cannot read shows « Unknown » to its owner"
        )

    def test_every_vocabulary_belongs_to_a_declared_reader(self) -> None:
        orphans = sorted(set(CONSULTATION_SURFACES) - set(CONSULTATION_RECORDERS))
        assert not orphans, (
            f"names capabilities but is not declared a reader: {orphans} — "
            "declare it in CONSULTATION_RECORDERS with the module that records it"
        )

    @pytest.mark.parametrize("key", _SURFACES)
    def test_a_surface_key_matches_its_own_declaration(self, key: str) -> None:
        assert CONSULTATION_SURFACES[key].key == key

    @pytest.mark.parametrize("key", _SURFACES)
    def test_no_surface_declares_an_empty_vocabulary(self, key: str) -> None:
        """A surface with no section records nothing — the state this ends."""
        assert CONSULTATION_SURFACES[key].domains, f"{key} names no section"

    @pytest.mark.parametrize("key", _SURFACES)
    def test_a_declaration_cannot_be_edited_at_runtime(self, key: str) -> None:
        """``frozen=True`` protects the attribute, never what it points at.

        This is a module-level global the register reads; one stray write and
        its table says something the surface never declared.
        """
        with pytest.raises(TypeError):
            CONSULTATION_SURFACES[key].domains["ghost"] = "nowhere"  # type: ignore[index]


class TestThePrefixesStayApart:
    """Two surfaces sharing a prefix would file each other's rows."""

    @pytest.mark.parametrize("key", _SURFACES)
    def test_a_prefix_is_bounded_and_ends_the_way_the_register_expects(self, key: str) -> None:
        prefix = CONSULTATION_SURFACES[key].prefix
        assert prefix, f"{key} has no prefix"
        assert prefix.endswith(":"), f"{key}: {prefix!r} does not separate its sections"
        assert prefix.strip() == prefix

    def test_no_two_surfaces_share_a_prefix(self) -> None:
        prefixes = [surface.prefix for surface in CONSULTATION_SURFACES.values()]
        assert len(set(prefixes)) == len(prefixes), f"colliding prefixes: {prefixes}"

    def test_no_prefix_is_a_prefix_of_another(self) -> None:
        """``surface_of`` returns the FIRST match, so nesting would misfile."""
        prefixes = [surface.prefix for surface in CONSULTATION_SURFACES.values()]
        for one in prefixes:
            for other in prefixes:
                if one is not other:
                    assert not other.startswith(one), f"{other!r} nests inside {one!r}"

    @pytest.mark.parametrize("key", _SURFACES)
    def test_a_capability_resolves_back_to_its_surface(self, key: str) -> None:
        surface = CONSULTATION_SURFACES[key]
        for section in surface.domains:
            assert surface_of(surface.capability(section)) is surface

    def test_a_tool_name_belongs_to_no_surface(self) -> None:
        assert surface_of("search_emails_tool") is None


class TestEveryCapabilityIsReadable:
    """A consultation nobody can name is worse than none (ADR-263)."""

    @pytest.mark.parametrize("key", _SURFACES)
    def test_the_register_resolves_every_capability_to_its_declared_domain(self, key: str) -> None:
        surface = CONSULTATION_SURFACES[key]
        for section, domain in surface.domains.items():
            capability = surface.capability(section)
            resolved = treatment_domain(capability)
            assert resolved != UNKNOWN_DOMAIN, f"{capability} headlines as « Unknown »"
            assert resolved == domain, (
                f"the register reads {capability} as {resolved!r} while {key} "
                f"declares {domain!r} — the two halves have drifted"
            )

    @pytest.mark.parametrize("key", _SURFACES)
    def test_every_declared_domain_is_a_bounded_noun(self, key: str) -> None:
        """Taxonomy noun, or a wording someone had to write six times.

        ``DOMAIN_REGISTRY`` is the taxonomy of ROUTABLE agents, and two sources
        the heartbeat opens have no agent at all — a journal and a declared
        interest are read, never routed to. The codebase already carries that
        distinction (``skill``, ``python_sandbox`` and ``unknown`` predate this
        module), so the bound that actually matters is the other one: a domain
        must be worded in all six languages. That is deliberate work nobody
        does by accident, which is what keeps free text out of a label set that
        must stay closed.
        """
        from src.core.i18n_treatments import TREATMENT_DOMAIN_LABELS

        for section, domain in CONSULTATION_SURFACES[key].domains.items():
            assert domain != UNKNOWN_DOMAIN, f"{key}:{section} declares the fallback"
            for language, labels in TREATMENT_DOMAIN_LABELS.items():
                assert domain in labels, (
                    f"{key}:{section} reads as {domain!r}, which has no wording "
                    f"in {language} — the row would show a technical name. Add "
                    "it to DOMAIN_REGISTRY, or word it in all six languages."
                )

    def test_the_taxonomy_covers_all_but_the_sources_that_have_no_agent(self) -> None:
        """Named, so an accidental third one is not absorbed in silence."""
        outside = {
            domain
            for surface in CONSULTATION_SURFACES.values()
            for domain in surface.domains.values()
            if domain not in DOMAIN_REGISTRY
        }
        assert outside == {"interest", "journal"}, (
            f"a consultation domain left the taxonomy without being argued: " f"{sorted(outside)}"
        )


class TestTheRegisterHoldsExactlyWhatTheSurfacesDeclare:
    """The register MERGES the declaration rather than transcribing it.

    Drift between the two tables used to be a real risk caught by three
    hand-written halves; it is now impossible by construction, so the tests
    that would have watched for it would be green by absence. What remains
    falsifiable is what the merge itself can get wrong: a collision with the
    tool half, and a prefix the resolver never reaches.
    """

    def test_no_tool_override_collides_with_a_surface_capability(self) -> None:
        """The surface half wins the merge, so a collision would be silent."""
        from src.domains.agents.effects.treatment_labels import _TOOL_DOMAIN_OVERRIDES

        collisions = sorted(set(_TOOL_DOMAIN_OVERRIDES) & set(capability_domains()))
        assert not collisions, (
            f"declared on both sides of the merge: {collisions} — the surface "
            "half wins and the tool entry would be dropped in silence"
        )

    def test_the_merged_table_holds_every_capability(self) -> None:
        """Cheap, and it fails the day the merge stops being a merge."""
        for capability, domain in capability_domains().items():
            assert TREATMENT_DOMAIN_OVERRIDES.get(capability) == domain

    def test_no_prefix_is_intercepted_before_the_override_table(self) -> None:
        """``treatment_domain`` answers MCP and draft names BEFORE the table.

        A surface declaring one of those prefixes would resolve through a
        branch that never reads its declaration — the same shape as the
        unreachable guard branch of 2026-09-06, pointing at the register.
        """
        from src.core.constants import MCP_TOOL_NAME_PREFIX
        from src.domains.agents.effects.treatment_labels import DRAFT_TOOL_PREFIX

        for key, surface in CONSULTATION_SURFACES.items():
            for intercepted in (MCP_TOOL_NAME_PREFIX, DRAFT_TOOL_PREFIX):
                assert not surface.prefix.startswith(intercepted), (
                    f"{key} declares {surface.prefix!r}, which "
                    f"``treatment_domain`` answers at {intercepted!r} before it "
                    "ever reads the override table"
                )


class TestTheBootGuardChecksThemToo:
    """It walked ``get_all_tools()`` alone until 2026-09-07.

    None of the thirty-one direct-read capabilities was checked where every
    other completeness rule is checked, so a fourth surface would have shipped
    with no boot check at all.
    """

    def test_an_unreadable_capability_refuses_the_boot(self) -> None:
        from unittest.mock import patch

        from src.domains.agents.effects.treatment_labels import (
            assert_treatment_domain_completeness,
            reset_domain_cache,
        )
        from src.domains.shared.consultation_surfaces import ConsultationSurface

        broken = {
            "ghost": ConsultationSurface(
                key="ghost",
                prefix="ghost:",
                source="user",
                domains={"nowhere": "a_domain_no_language_words"},
            )
        }
        reset_domain_cache()
        with (
            patch(
                "src.domains.shared.consultation_surfaces.CONSULTATION_SURFACES",
                broken,
            ),
            patch(
                "src.domains.agents.tools.tool_registry.get_all_tools",
                return_value=[],
            ),
            pytest.raises(AssertionError, match="ghost:nowhere"),
        ):
            assert_treatment_domain_completeness()

    def test_the_real_declaration_boots(self) -> None:
        from unittest.mock import patch

        from src.domains.agents.effects.treatment_labels import (
            assert_treatment_domain_completeness,
        )

        with patch(
            "src.domains.agents.tools.tool_registry.get_all_tools",
            return_value=[],
        ):
            assert_treatment_domain_completeness()


class TestTheAuthorshipIsDeclaredNotTyped:
    """Three call sites typed this literal before; a typo dropped the row."""

    @pytest.mark.parametrize("key", _SURFACES)
    def test_every_surface_declares_a_real_authorship(self, key: str) -> None:
        known = {member.value for member in EffectSource}
        source = CONSULTATION_SURFACES[key].source
        assert source in known, (
            f"{key} records its rows as {source!r}, which EffectSource cannot "
            "emit — the origin filter would drop every one of them in silence"
        )

    def test_the_three_authorships_in_use_are_all_represented(self) -> None:
        """Nobody schedules a briefing; nobody asks for a sweep.

        If a refactor ever collapses them onto one value, this fails rather
        than quietly crediting LIA with page loads it never chose to make.

        ``scheduled`` joined on 2026-09-07 with the documentary spaces, and
        deliberately: a space is a STANDING INSTRUCTION the person wrote —
        « keep this folder indexed » — so its reads are neither their live
        request nor LIA's own idea. It is the same word this codebase already
        uses for a reminder: their own deferred instruction.
        """
        declared = {surface.source for surface in CONSULTATION_SURFACES.values()}
        assert declared == {
            EffectSource.USER.value,
            EffectSource.PROACTIVE.value,
            EffectSource.SCHEDULED.value,
        }, (
            "a surface introduced a third authorship. That may well be right — "
            "a reader driven by a routine would be `scheduled` — but it is a "
            "decision, so widen this set deliberately rather than by default."
        )


class TestTheSeamHasOneCaller:
    """A surface that records by hand escapes everything above.

    ``record_consultation`` takes a capability and an authorship as free
    strings. Called directly, a surface bypasses the declaration — so its
    capability is checked by no boot guard, its domain by no wording test, and
    its authorship by nothing at all. That is exactly the state the three
    hand-written implementations were in until 2026-09-07: one of them typed
    ``source="proactive"`` and nothing anywhere would have caught
    ``"proactve"``.
    """

    def test_only_the_registry_calls_the_recording_seam(self) -> None:
        import ast
        from pathlib import Path

        src = Path(__file__).resolve().parents[4] / "src"
        # ONE entry. Measured 2026-09-07: the seam has exactly one caller, so
        # the two extra names first written here (the seam's own module and
        # the register that installs it — neither of which CALLS it) were dead
        # permissions, and a dead permission is a door left ajar.
        allowed = {"domains/shared/consultation_surfaces.py"}
        offenders: list[str] = []
        for path in src.rglob("*.py"):
            relative = path.relative_to(src).as_posix()
            if relative in allowed:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError, UnicodeDecodeError:  # pragma: no cover - not our tree
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                if name in {"record_consultation", "record_out_of_turn_consultation"}:
                    offenders.append(f"{relative}:{node.lineno}")
        assert not offenders, (
            f"records a consultation without going through the registry: "
            f"{offenders} — declare the surface in CONSULTATION_SURFACES and "
            "call record_surface_consultations, so its capability, its domain "
            "and its authorship are all checked"
        )


class TestTheOneRecordingLoop:
    """What the three copies did, asserted once."""

    def _rows(self, **kwargs: object) -> list:
        from src.domains.agents.effects.treatments import treatment_collector

        with treatment_collector(run_id="surface-run") as rows:
            record_surface_consultations(**kwargs)  # type: ignore[arg-type]
        return rows

    def test_an_opened_source_is_recorded_under_its_capability(self) -> None:
        rows = self._rows(
            surface="heartbeat",
            user_id="11111111-1111-1111-1111-111111111111",
            opened=["emails", "calendar"],
            duration_ms=12,
        )
        assert {row.tool_name for row in rows} == {"heartbeat:emails", "heartbeat:calendar"}
        assert {row.outcome for row in rows} == {"ok"}

    def test_a_source_that_could_not_be_read_is_failed_not_empty(self) -> None:
        rows = self._rows(
            surface="briefing",
            user_id="11111111-1111-1111-1111-111111111111",
            opened=["mails", "tasks"],
            failed=["tasks"],
            duration_ms=3,
        )
        assert {row.tool_name: row.outcome for row in rows} == {
            "briefing:mails": "ok",
            "briefing:tasks": "failed",
        }

    def test_the_declared_authorship_reaches_the_row(self) -> None:
        assert (
            self._rows(
                surface="heartbeat",
                user_id="11111111-1111-1111-1111-111111111111",
                opened=["weather"],
                duration_ms=1,
            )[0].source
            == EffectSource.PROACTIVE.value
        )
        assert (
            self._rows(
                surface="relation_debrief",
                user_id="11111111-1111-1111-1111-111111111111",
                opened=["contact"],
                duration_ms=1,
            )[0].source
            == EffectSource.USER.value
        )

    def test_a_section_the_surface_does_not_declare_records_nothing(self) -> None:
        """It would headline as « Unknown », which the register refuses."""
        rows = self._rows(
            surface="briefing",
            user_id="11111111-1111-1111-1111-111111111111",
            opened=["mails", "not_a_section"],
            duration_ms=1,
        )
        assert [row.tool_name for row in rows] == ["briefing:mails"]

    def test_an_unknown_surface_records_nothing_and_raises_nothing(self) -> None:
        assert (
            self._rows(
                surface="no_such_surface",
                user_id="11111111-1111-1111-1111-111111111111",
                opened=["mails"],
                duration_ms=1,
            )
            == []
        )

    def test_an_explicit_run_id_wins_over_the_collectors(self) -> None:
        rows = self._rows(
            surface="relation_debrief",
            user_id="11111111-1111-1111-1111-111111111111",
            opened=["emails"],
            duration_ms=1,
            run_id="debrief-explicit",
        )
        assert rows[0].run_id == "debrief-explicit"

    def test_without_a_run_id_the_collectors_own_is_used(self) -> None:
        rows = self._rows(
            surface="heartbeat",
            user_id="11111111-1111-1111-1111-111111111111",
            opened=["emails"],
            duration_ms=1,
        )
        assert rows[0].run_id == "surface-run"

    def test_outside_a_collector_nothing_is_recorded_and_nothing_raises(self) -> None:
        record_surface_consultations(
            surface="heartbeat",
            user_id="11111111-1111-1111-1111-111111111111",
            opened=["emails"],
            duration_ms=1,
        )

    def test_the_duration_is_carried_by_every_row(self) -> None:
        """Concurrent sources share one figure rather than an invented split."""
        rows = self._rows(
            surface="heartbeat",
            user_id="11111111-1111-1111-1111-111111111111",
            opened=["emails", "tasks", "weather"],
            duration_ms=210,
        )
        assert {row.duration_ms for row in rows} == {210}

    def test_a_recording_failure_never_reaches_the_caller(self) -> None:
        """Observing must never break the observed — the whole loop is guarded."""
        from unittest.mock import patch

        with patch(
            "src.domains.shared.consultation_surfaces.record_consultation",
            side_effect=RuntimeError("register down"),
        ):
            record_surface_consultations(
                surface="briefing",
                user_id="11111111-1111-1111-1111-111111111111",
                opened=["mails"],
                duration_ms=1,
            )
