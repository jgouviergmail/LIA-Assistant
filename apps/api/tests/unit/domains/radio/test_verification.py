"""Nothing reaches a voice unchecked: each rule of the verifier, and the pack's isolation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.domains.radio.constants import (
    INTRO_OUTRO_MAX_LINES,
    LINE_MAX_CHARS,
    MAX_DROPPED_LINE_RATIO,
    REFS_MAX_PER_LINE,
    SCRIPT_TITLE_MAX_CHARS,
)
from src.domains.radio.facts import FactKind, FactPack, RadioFact, Sensitivity, SourceRef
from src.domains.radio.formats import FORMAT_SPECS, RadioFormat, RadioRole
from src.domains.radio.script import LineKind, ScriptDraft, ScriptLine, ScriptPart
from src.domains.radio.verification import (
    Refusal,
    VerificationResult,
    Violation,
    verify_script,
)

pytestmark = pytest.mark.unit

QUOTE_MAX = 40


def fact(
    fid: str,
    text: str,
    kind: FactKind = FactKind.NEWS,
    sensitivity: Sensitivity = Sensitivity.PUBLIC,
) -> RadioFact:
    return RadioFact(
        id=fid,
        kind=kind,
        text=text,
        key=f"k:{fid}",
        sensitivity=sensitivity,
        source=SourceRef(label="Outlet X"),
    )


NEWS_PACK = FactPack(
    format=RadioFormat.BULLETIN,
    facts=(
        fact("c1", "Local time: 09:02", FactKind.CLOCK),
        fact("n1", "Company X raised 3.9 billion dollars in a series F round."),
        fact("n2", "The parliament of country Y adopted the budget by 312 votes."),
    ),
)


def line(
    text: str,
    refs: list[str] | None = None,
    *,
    role: RadioRole = RadioRole.ANCHOR,
    part: ScriptPart = ScriptPart.BODY,
    kind: LineKind = LineKind.FACT,
) -> ScriptLine:
    return ScriptLine(role=role, part=part, kind=kind, text=text, refs=refs or [])


def verify(
    lines: list[ScriptLine],
    pack: FactPack = NEWS_PACK,
    title: str = "News",
    station: str = "LIA Radio",
) -> VerificationResult:
    return verify_script(
        ScriptDraft(title=title, lines=lines),
        pack,
        language="fr",
        quote_max_chars=QUOTE_MAX,
        station_name=station,
    )


INTRO = line(
    "Il est 9 heures, voici le journal.",
    ["c1"],
    role=RadioRole.HOST,
    part=ScriptPart.INTRO,
    kind=LineKind.TRANSITION,
)
OUTRO = line(
    "C'était le journal.", role=RadioRole.HOST, part=ScriptPart.OUTRO, kind=LineKind.TRANSITION
)


class TestFactPackIsolation:
    def test_ids_are_unique(self) -> None:
        with pytest.raises(ValidationError, match="unique"):
            FactPack(format=RadioFormat.BRIEF, facts=(fact("n1", "a"), fact("n1", "b")))

    @pytest.mark.parametrize(
        ("fmt", "kind"),
        [
            (RadioFormat.BULLETIN, FactKind.EMAIL),
            (RadioFormat.BRIEF, FactKind.EVENT),
            (RadioFormat.JOURNAL, FactKind.NEWS),
            (RadioFormat.JOURNAL, FactKind.ANALYSIS),
            (RadioFormat.OPENING, FactKind.EVENT),
            (RadioFormat.SIGN_OFF, FactKind.NEWS),
        ],
    )
    def test_a_pack_refuses_the_other_material(self, fmt: RadioFormat, kind: FactKind) -> None:
        with pytest.raises(ValidationError, match="material isolation"):
            FactPack(format=fmt, facts=(fact("x1", "something", kind),))

    @pytest.mark.parametrize(
        ("fmt", "kind"),
        [
            (RadioFormat.COLUMN, FactKind.NEWS),
            (RadioFormat.BULLETIN, FactKind.CLOCK),
            (RadioFormat.OPENING, FactKind.WEATHER),
            (RadioFormat.JOURNAL, FactKind.EVENT),
            (RadioFormat.JOURNAL, FactKind.COMMITMENT),
        ],
    )
    def test_a_pack_accepts_its_own_material(self, fmt: RadioFormat, kind: FactKind) -> None:
        pack = FactPack(format=fmt, facts=(fact("x1", "something", kind),))
        assert pack.by_id()["x1"].kind is kind
        assert pack.keys == ("k:x1",)


class TestLines:
    def test_a_clean_script_airs_whole_in_part_order(self) -> None:
        body = line("La société X a levé 3,9 milliards de dollars.", ["n1"])
        result = verify([body, OUTRO, INTRO])
        assert result.accepted
        assert [ln.part for ln in result.lines] == [
            ScriptPart.INTRO,
            ScriptPart.BODY,
            ScriptPart.OUTRO,
        ]
        assert result.dropped == ()

    def test_an_invented_source_is_dropped(self) -> None:
        result = verify([INTRO, line("Un fait.", ["n9"]), line("Un autre.", ["n2"])])
        assert (1, Violation.UNKNOWN_REF) in result.dropped

    def test_a_factual_line_must_cite_a_fact(self) -> None:
        result = verify([INTRO, line("Le budget est adopté.", []), line("Vote : 312.", ["n2"])])
        assert (1, Violation.MISSING_REF) in result.dropped

    def test_a_guest_the_format_does_not_cast_is_dropped(self) -> None:
        guest = line("Mon analyse.", ["n1"], role=RadioRole.EXPERT)
        result = verify([INTRO, guest, line("Le vote : 312.", ["n2"])])
        assert (1, Violation.ROLE_NOT_ALLOWED) in result.dropped

    def test_the_host_may_speak_in_any_format(self) -> None:
        result = verify([INTRO, line("Le vote : 312.", ["n2"], role=RadioRole.HOST)])
        assert result.accepted and result.dropped == ()

    def test_an_unsupported_number_is_dropped(self) -> None:
        result = verify([INTRO, line("La société X a levé 4,2 milliards.", ["n1"])])
        assert (1, Violation.UNSUPPORTED_NUMBER) in result.dropped

    def test_a_decimal_never_passes_for_an_integer(self) -> None:
        pack = FactPack(format=RadioFormat.BRIEF, facts=(fact("n1", "Inflation rose by 0.5 %."),))
        result = verify([line("L'inflation a progressé de 5 %.", ["n1"])], pack)
        assert (0, Violation.UNSUPPORTED_NUMBER) in result.dropped

    def test_the_station_is_named_with_its_digits(self) -> None:
        # « Radio 42 » names the station the listener called so; it states no 42.
        # Before: every line naming it was dropped as an unsupported number, and
        # an opening that names nothing else was refused.
        welcome = line(
            "Bienvenue sur radio 42, il est 9 h 02.",
            ["c1"],
            role=RadioRole.HOST,
            part=ScriptPart.INTRO,
            kind=LineKind.TRANSITION,
        )
        farewell = line(
            "Ici FM 98.5, à demain.",
            role=RadioRole.HOST,
            part=ScriptPart.OUTRO,
            kind=LineKind.TRANSITION,
        )
        body = line("Vote : 312.", ["n2"])
        assert verify([welcome, body], station="Radio 42").dropped == ()
        assert verify([INTRO, body, farewell], station="FM 98.5").dropped == ()

    def test_a_station_without_a_name_blanks_nothing(self) -> None:
        # An empty pattern matches between every character: blanking it would
        # read « 312 » as 3, 1 and 2 and drop a supported line.
        assert verify([INTRO, line("Vote : 312.", ["n2"])], station="").dropped == ()
        assert verify([INTRO, line("Vote : 312.", ["n2"])], station="  ").dropped == ()

    def test_the_stations_digits_license_no_number_outside_its_name(self) -> None:
        claim = line("Sur Radio 42 : 42 députés ont voté contre.", ["n2"])
        result = verify([INTRO, claim], station="Radio 42")
        assert (1, Violation.UNSUPPORTED_NUMBER) in result.dropped

    def test_a_number_from_another_fact_is_not_supported(self) -> None:
        result = verify([INTRO, line("Le budget a recueilli 312 voix.", ["n1"])])
        assert (1, Violation.UNSUPPORTED_NUMBER) in result.dropped

    def test_a_figure_past_a_chinese_multiplier_is_read_at_its_value(self) -> None:
        """« 60万 » says the fact's « 600 000 » (one family wrote Chinese figures so)."""
        fact_fr = fact("n1", "Près de 600 000 fidèles sont attendus.")
        pack = FactPack(format=RadioFormat.BRIEF, facts=(fact_fr,))
        assert verify([line("预计有近60万名信徒参加。", ["n1"])], pack).accepted
        wrong = verify([line("预计有近70万名信徒参加。", ["n1"])], pack)
        assert (0, Violation.UNSUPPORTED_NUMBER) in wrong.dropped

    def test_the_cited_facts_outlet_may_be_named_with_its_digits(self) -> None:
        # « France 24 » attributes the fact; it does not claim a 24. Measured on
        # a real bulletin: two of three dropped lines were this, not a figure.
        pack = FactPack(
            format=RadioFormat.BRIEF,
            facts=(
                RadioFact(
                    id="n1",
                    kind=FactKind.NEWS,
                    text="The parliament of country Y adopted the budget.",
                    key="k:n1",
                    sensitivity=Sensitivity.PUBLIC,
                    source=SourceRef(label="Channel 24"),
                ),
            ),
        )
        attributed = verify([line("Selon Channel 24, le budget est adopté.", ["n1"])], pack)
        assert attributed.dropped == ()
        uncited = verify(
            [
                line(
                    "Selon Channel 24, le budget est adopté.",
                    role=RadioRole.HOST,
                    kind=LineKind.TRANSITION,
                )
            ],
            pack,
        )
        assert (0, Violation.UNSUPPORTED_NUMBER) in uncited.dropped

    def test_a_transition_may_count_its_own_programme(self) -> None:
        transition = line(
            "Trois titres, puis 2 sujets.", role=RadioRole.HOST, kind=LineKind.TRANSITION
        )
        result = verify([INTRO, transition, line("Vote : 312.", ["n2"])])
        assert result.dropped == ()

    @pytest.mark.parametrize("claim", ["Plus de 25 morts.", "Un taux de 3,5 pour cent."])
    def test_a_transition_cannot_smuggle_a_claim(self, claim: str) -> None:
        transition = line(claim, role=RadioRole.HOST, kind=LineKind.TRANSITION)
        result = verify([INTRO, transition, line("Vote : 312.", ["n2"])])
        assert (1, Violation.UNSUPPORTED_NUMBER) in result.dropped

    def test_a_long_quote_is_dropped_and_a_short_one_airs(self) -> None:
        long_quote = "« " + "mot " * 15 + "»"
        short = line("Le ministre a dit « nous voterons ».", ["n2"])
        result = verify([INTRO, line(f"Il a déclaré {long_quote}", ["n2"]), short])
        assert (1, Violation.QUOTE_TOO_LONG) in result.dropped
        assert any("nous voterons" in ln.text for ln in result.lines)

    def test_empty_and_overlong_lines_are_dropped(self) -> None:
        result = verify(
            [
                INTRO,
                line("   ", ["n1"]),
                line("x" * (LINE_MAX_CHARS + 1), ["n1"]),
                line("312.", ["n2"]),
            ]
        )
        assert (1, Violation.EMPTY_TEXT) in result.dropped
        assert (2, Violation.LINE_TOO_LONG) in result.dropped

    def test_refs_are_repaired_not_refused(self) -> None:
        refs = ["n2", " n2 ", "n1"] + ["n1"] * 10
        result = verify([INTRO, line("Vote : 312.", refs)])
        assert result.lines[1].refs == ("n2", "n1")
        assert len(result.lines[1].refs) <= REFS_MAX_PER_LINE

    def test_music_carries_only_a_few_lines(self) -> None:
        intros = [INTRO] * (INTRO_OUTRO_MAX_LINES + 2)
        result = verify(intros + [line("Vote : 312.", ["n2"])])
        over = [v for _, v in result.dropped if v is Violation.TOO_MANY_TRANSITIONS]
        assert len(over) == 2
        assert sum(1 for ln in result.lines if ln.part is ScriptPart.INTRO) == INTRO_OUTRO_MAX_LINES


class TestPersonIsVoicedByTheHostAlone:
    """The last wall: no producer puts a record of the person in a guest's pack."""

    PACK = FactPack(
        format=RadioFormat.COLUMN,
        facts=(
            fact(
                "w1",
                "Rain expected at the listener's home.",
                FactKind.WEATHER,
                Sensitivity.PERSONAL,
            ),
            fact("n1", "A new camera sensor was presented in city Z."),
        ),
    )

    def test_the_columnist_cannot_speak_about_the_person(self) -> None:
        columnist = line("Il pleuvra chez toi.", ["w1"], role=RadioRole.COLUMNIST)
        result = verify(
            [INTRO, columnist, line("Un capteur.", ["n1"], role=RadioRole.COLUMNIST)], self.PACK
        )
        assert (1, Violation.PERSON_OUTSIDE_HOST) in result.dropped

    def test_the_host_can(self) -> None:
        host = line("Il pleuvra chez toi.", ["w1"], role=RadioRole.HOST, part=ScriptPart.INTRO)
        result = verify([host, line("Un capteur.", ["n1"], role=RadioRole.COLUMNIST)], self.PACK)
        assert result.accepted and result.dropped == ()


class TestColumn:
    """Measured 2026-09-26: with no kind for a view, every opinion line was dropped."""

    PACK = FactPack(
        format=RadioFormat.COLUMN,
        facts=(
            fact("c1", "Saturday 2026-09-26, 10:21", FactKind.CLOCK),
            fact("n1", "Near 260 climate marches are planned on Saturday, after a record summer."),
        ),
    )

    def test_the_columnists_view_airs_when_it_cites_its_story(self) -> None:
        views = [
            line(
                "À mes yeux, ces 260 marches comptent.",
                ["n1"],
                role=RadioRole.COLUMNIST,
                kind=LineKind.OPINION,
            ),
            line(
                "Je pense qu'un été record ne s'oublie pas.",
                ["n1"],
                role=RadioRole.COLUMNIST,
                kind=LineKind.OPINION,
            ),
        ]
        result = verify(views, self.PACK)
        assert result.accepted and result.dropped == ()

    def test_a_view_cites_its_story_and_is_the_columnists_alone(self) -> None:
        uncited = line(
            "Je pense que c'est important.", role=RadioRole.COLUMNIST, kind=LineKind.OPINION
        )
        anchored = line(
            "À mon avis, c'est capital.", ["n1"], role=RadioRole.HOST, kind=LineKind.OPINION
        )
        sound = line(
            "À mes yeux, 260 marches, c'est beaucoup.",
            ["n1"],
            role=RadioRole.COLUMNIST,
            kind=LineKind.OPINION,
        )
        result = verify([uncited, anchored, sound], self.PACK)
        assert (0, Violation.MISSING_REF) in result.dropped
        assert (1, Violation.OPINION_OUTSIDE_COMMENTATORS) in result.dropped
        assert [ln.text for ln in result.lines] == [sound.text]


class TestDebate:
    """ADR-324 decision 39: the speakers of a debate or a discussion hold views too — the
    moderator never does, and a speaker the programme does not voice never speaks."""

    PACK = FactPack(
        format=RadioFormat.DEBATE,
        facts=(fact("n1", "The city of Z will close its centre to cars from 2027."),),
    )

    def debate(self) -> list[ScriptLine]:
        return [
            line("La ville de Z fermera son centre aux voitures en 2027.", ["n1"]),
            line(
                "Pour moi, c'est une bonne nouvelle.",
                ["n1"],
                role=RadioRole.SPEAKER_A,
                kind=LineKind.OPINION,
            ),
            line(
                "À mes yeux, c'est trop brutal.",
                ["n1"],
                role=RadioRole.SPEAKER_B,
                kind=LineKind.OPINION,
            ),
            line(
                "Je crois que tu as tort.", ["n1"], role=RadioRole.SPEAKER_C, kind=LineKind.OPINION
            ),
        ]

    def test_every_speaker_holds_a_view_and_the_moderator_none(self) -> None:
        moderator = line("À mon avis, les deux ont raison.", ["n1"], kind=LineKind.OPINION)
        result = verify([*self.debate(), moderator], self.PACK)
        assert result.dropped == ((4, Violation.OPINION_OUTSIDE_COMMENTATORS),)
        assert [ln.role for ln in result.lines] == [
            RadioRole.ANCHOR,
            RadioRole.SPEAKER_A,
            RadioRole.SPEAKER_B,
            RadioRole.SPEAKER_C,
        ]

    def test_a_speaker_the_programme_does_not_voice_never_speaks(self) -> None:
        voiced = (RadioRole.ANCHOR, RadioRole.SPEAKER_A, RadioRole.SPEAKER_B)
        result = verify_script(
            ScriptDraft(title="Debate", lines=self.debate()),
            self.PACK,
            language="fr",
            quote_max_chars=QUOTE_MAX,
            station_name="LIA Radio",
            roles=voiced,
        )
        assert result.dropped == ((3, Violation.ROLE_NOT_ALLOWED),)


class TestMechanicalRepairs:
    PACK = FactPack(
        format=RadioFormat.BULLETIN,
        facts=(
            fact("c1", "Saturday 2026-09-26, 10:21", FactKind.CLOCK),
            fact("n2", "The parliament of country Y adopted the budget by 312 votes."),
        ),
    )

    def test_the_time_said_without_citing_the_clock_cites_it(self) -> None:
        greeting = line(
            "Il est 10 h 21, voici le journal.",
            role=RadioRole.HOST,
            part=ScriptPart.INTRO,
            kind=LineKind.TRANSITION,
        )
        result = verify([greeting, line("Vote : 312.", ["n2"])], self.PACK)
        assert result.dropped == ()
        assert result.lines[0].refs == ("c1",)

    def test_a_greeting_naming_the_station_and_the_time_cites_the_clock(self) -> None:
        # The repair reads the line as the editor does: « Radio 42 » is a
        # mention, so the clock alone sources what is left.
        greeting = line(
            "Ici Radio 42, il est 10 h 21.",
            role=RadioRole.HOST,
            part=ScriptPart.INTRO,
            kind=LineKind.TRANSITION,
        )
        result = verify([greeting, line("Vote : 312.", ["n2"])], self.PACK, station="Radio 42")
        assert result.dropped == ()
        assert result.lines[0].refs == ("c1",)

    def test_a_number_the_clock_does_not_state_is_still_dropped(self) -> None:
        claim = line("Il est 10 h 21 : 25 morts.", role=RadioRole.HOST, kind=LineKind.TRANSITION)
        result = verify([claim, line("Vote : 312.", ["n2"])], self.PACK)
        assert (0, Violation.UNSUPPORTED_NUMBER) in result.dropped

    def test_an_opening_written_over_its_music_is_its_body(self) -> None:
        # Measured 2026-09-26: both model families wrote the whole welcome over
        # the music, and both openings were refused for having no body.
        pack = FactPack(
            format=RadioFormat.OPENING,
            facts=(fact("c1", "Saturday 2026-09-26, 10:21", FactKind.CLOCK),),
        )
        welcome = [
            line(text, role=RadioRole.HOST, part=part, kind=LineKind.TRANSITION)
            for text, part in (
                ("Bonjour, bienvenue sur LIA Radio.", ScriptPart.INTRO),
                ("Nous sommes samedi, il est 10 h 21.", ScriptPart.INTRO),
                ("On commence avec les titres.", ScriptPart.INTRO),
                ("Restez avec nous.", ScriptPart.OUTRO),
            )
        ]
        result = verify(welcome, pack)
        assert result.accepted and result.dropped == ()
        assert {ln.part for ln in result.lines} == {ScriptPart.BODY}


class TestAnalysis:
    PACK = FactPack(
        format=RadioFormat.ANALYSIS,
        facts=(
            fact("n1", "Country Y adopted the budget by 312 votes."),
            fact(
                "a1", "Context: the vote follows two failed attempts since 2024.", FactKind.ANALYSIS
            ),
        ),
    )

    def test_an_analysis_line_must_cite_the_analysis(self) -> None:
        result = verify(
            [
                line("C'est un tournant.", ["n1"], role=RadioRole.EXPERT, kind=LineKind.ANALYSIS),
                line(
                    "Deux échecs depuis 2024.",
                    ["a1"],
                    role=RadioRole.EXPERT,
                    kind=LineKind.ANALYSIS,
                ),
                line("Adopté par 312 voix.", ["n1"]),
            ],
            self.PACK,
        )
        assert (0, Violation.MISSING_REF) in result.dropped
        assert any("2024" in ln.text for ln in result.lines)

    def test_a_fact_line_cannot_rest_on_the_analysis_alone(self) -> None:
        result = verify(
            [line("Deux échecs depuis 2024.", ["a1"]), line("Adopté par 312 voix.", ["n1"])],
            self.PACK,
        )
        assert (0, Violation.MISSING_REF) in result.dropped

    @staticmethod
    def _story_pack(*, with_its_own_fact: bool = True) -> FactPack:
        story = SourceRef(label="Outlet X", story_key="s1")
        own = RadioFact(
            id="n1",
            kind=FactKind.NEWS,
            text="Country Y adopted the budget by 312 votes.",
            key="s1",
            sensitivity=Sensitivity.PUBLIC,
            source=story,
        )
        point = RadioFact(
            id="a1",
            kind=FactKind.ANALYSIS,
            text="Context: the vote follows two failed attempts since 2024.",
            key="s1#a1",
            sensitivity=Sensitivity.PUBLIC,
            source=story,
        )
        facts = (own, point) if with_its_own_fact else (point,)
        return FactPack(format=RadioFormat.ANALYSIS, facts=facts)

    @staticmethod
    def _point(fid: str, story_key: str) -> RadioFact:
        return RadioFact(
            id=fid,
            kind=FactKind.ANALYSIS,
            text="Context: the vote follows two failed attempts since 2024.",
            key=f"{story_key}#{fid}",
            sensitivity=Sensitivity.PUBLIC,
            source=SourceRef(label="Outlet X", story_key=story_key),
        )

    def test_the_anchor_telling_an_analysis_point_rests_on_its_story(self) -> None:
        """A point is the expert's reading of ONE story: a fact line telling it rests on
        that story, which the repair cites (measured 2026-09-27: half the anchors' fact
        lines cited analysis points alone, even when the writer was told not to)."""
        result = verify([line("Deux échecs depuis 2024.", ["a1"])], self._story_pack())
        assert result.dropped == ()
        assert result.lines[0].refs == ("a1", "n1")

    def test_the_repair_cites_the_points_own_story_and_no_other(self) -> None:
        other = RadioFact(
            id="n2",
            kind=FactKind.NEWS,
            text="Country Z held a vote.",
            key="s2",
            sensitivity=Sensitivity.PUBLIC,
            source=SourceRef(label="Outlet X", story_key="s2"),
        )
        pack = FactPack(format=RadioFormat.ANALYSIS, facts=(other, *self._story_pack().facts))
        result = verify([line("Deux échecs depuis 2024.", ["a1"])], pack)
        assert result.lines[0].refs == ("a1", "n1")

    def test_the_repair_takes_the_storys_fact_never_another_of_its_points(self) -> None:
        own, point = self._story_pack().facts
        pack = FactPack(format=RadioFormat.ANALYSIS, facts=(self._point("a2", "s1"), point, own))
        result = verify([line("Deux échecs depuis 2024.", ["a1"])], pack)
        assert result.lines[0].refs == ("a1", "n1")

    def test_a_line_already_resting_on_its_story_keeps_its_refs(self) -> None:
        result = verify([line("Deux échecs depuis 2024.", ["n1", "a1"])], self._story_pack())
        assert result.lines[0].refs == ("n1", "a1")

    def test_a_point_whose_story_is_not_in_the_pack_is_still_missing_its_ref(self) -> None:
        result = verify(
            [line("Deux échecs depuis 2024.", ["a1"])], self._story_pack(with_its_own_fact=False)
        )
        assert (0, Violation.MISSING_REF) in result.dropped

    def test_points_of_two_stories_are_left_to_the_rule(self) -> None:
        pack = FactPack(
            format=RadioFormat.ANALYSIS, facts=(*self._story_pack().facts, self._point("a2", "s2"))
        )
        result = verify([line("Deux échecs depuis 2024.", ["a1", "a2"])], pack)
        assert (0, Violation.MISSING_REF) in result.dropped

    def test_a_line_citing_all_it_may_is_left_to_the_rule(self) -> None:
        points = tuple(self._point(f"a{n}", "s1") for n in range(1, REFS_MAX_PER_LINE + 1))
        own = self._story_pack().facts[0]
        pack = FactPack(format=RadioFormat.ANALYSIS, facts=(own, *points))
        result = verify([line("Deux échecs depuis 2024.", [p.id for p in points])], pack)
        assert (0, Violation.MISSING_REF) in result.dropped

    def test_the_experts_line_keeps_its_own_refs(self) -> None:
        reading = line(
            "Deux échecs depuis 2024.", ["a1"], role=RadioRole.EXPERT, kind=LineKind.ANALYSIS
        )
        result = verify([reading], self._story_pack())
        assert result.lines[0].refs == ("a1",)


class TestRefusals:
    def test_no_body_left_refuses_the_segment(self) -> None:
        result = verify([INTRO, OUTRO])
        assert result.refusal is Refusal.NO_BODY and not result.accepted

    def test_far_past_the_maximum_refuses_rather_than_cuts(self) -> None:
        spec = FORMAT_SPECS[RadioFormat.BULLETIN]
        chunk = "Le vote a réuni 312 voix. " * 20
        many = [line(chunk.strip(), ["n2"]) for _ in range(spec.max_chars("fr") // len(chunk) * 2)]
        result = verify([INTRO] + many)
        assert result.refusal is Refusal.TOO_LONG

    def test_too_many_dropped_sourced_lines_refuse_the_segment(self) -> None:
        bad = [line("Faux : 999.", ["n2"]) for _ in range(2)]
        good = [line("Vote : 312.", ["n2"]) for _ in range(3)]
        result = verify([INTRO] + bad + good)
        assert result.refusal is Refusal.TOO_MANY_DROPPED

    def test_a_quarter_dropped_is_still_a_segment(self) -> None:
        bad = [line("Faux : 999.", ["n2"])]
        good = [line("Vote : 312.", ["n2"]) for _ in range(3)]
        result = verify([INTRO] + bad + good)
        assert result.accepted

    def test_the_title_is_repaired(self) -> None:
        result = verify([INTRO, line("Vote : 312.", ["n2"])], title="  Le   journal  " + "x" * 200)
        assert result.title.startswith("Le journal")
        assert len(result.title) <= SCRIPT_TITLE_MAX_CHARS


class TestStoryBound:
    """A format tells at most its stories: the ones past it are cut, never held against it."""

    @staticmethod
    def pack(fmt: RadioFormat, stories: int) -> FactPack:
        facts = tuple(fact(f"n{i}", f"Story {i} happened.") for i in range(1, stories + 1))
        return FactPack(format=fmt, facts=facts)

    @staticmethod
    def told(i: int, *also: int) -> ScriptLine:
        return line(f"Story {i} happened.", [f"n{i}", *(f"n{j}" for j in also)])

    def test_the_first_stories_told_are_kept_and_the_rest_cut(self) -> None:
        bound = FORMAT_SPECS[RadioFormat.BULLETIN].stories_max
        assert bound is not None
        result = verify(
            [self.told(i) for i in range(1, bound + 3)], self.pack(RadioFormat.BULLETIN, bound + 2)
        )
        assert result.accepted
        assert [kept.refs for kept in result.lines] == [(f"n{i}",) for i in range(1, bound + 1)]
        assert result.dropped == (
            (bound, Violation.STORY_BEYOND_FORMAT),
            (bound + 1, Violation.STORY_BEYOND_FORMAT),
        )

    def test_facts_told_together_are_one_story(self) -> None:
        """Two outlets on one event, cited in one line, count once — even told apart later."""
        result = verify(
            [self.told(1, 2), self.told(2), self.told(3)], self.pack(RadioFormat.BRIEF, 3)
        )
        assert [kept.refs for kept in result.lines] == [("n1", "n2"), ("n2",)]
        assert result.dropped == ((2, Violation.STORY_BEYOND_FORMAT),)

    def test_a_cut_never_counts_against_the_segment_but_a_fault_still_does(self) -> None:
        pack = self.pack(RadioFormat.BRIEF, 4)
        cut = [self.told(i) for i in (2, 3, 4)]
        assert verify([self.told(1), *cut], pack).accepted  # three lines of four cut
        faulty = line("Story 1 happened 999 times.", ["n1"])
        assert MAX_DROPPED_LINE_RATIO < 1 / 2
        result = verify([self.told(1), faulty, *cut], pack)
        assert result.refusal is Refusal.TOO_MANY_DROPPED  # one of the two it kept was false

    def test_the_journal_tells_the_listeners_things_unbounded(self) -> None:
        """The journal has no story bound: every one of the listener's facts may be told,
        and the clock line frames them without counting as one (ADR-324 decision 41)."""
        pack = FactPack(
            format=RadioFormat.JOURNAL,
            facts=(
                fact("c1", "Local time: 09:02", FactKind.CLOCK),
                fact("p1", "Call the plumber at 6 pm.", FactKind.REMINDER, Sensitivity.PERSONAL),
                fact("p2", "Renew the car insurance.", FactKind.TASK, Sensitivity.PERSONAL),
            ),
        )
        host = RadioRole.HOST
        result = verify(
            [
                line("It is 9:02.", ["c1"], role=host),
                line("Call the plumber at 6.", ["p1"], role=host),
                line("And renew the car insurance.", ["p2"], role=host),
            ],
            pack,
        )
        assert [kept.refs for kept in result.lines] == [("c1",), ("p1",), ("p2",)]
        assert result.dropped == ()
        assert result.accepted
