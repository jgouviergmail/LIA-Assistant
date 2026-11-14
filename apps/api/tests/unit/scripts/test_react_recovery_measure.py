"""The ReAct recovery bench (ADR-310): reading a final message, and a turn where nothing fails."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

import pytest
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

from scripts.react import measure_recovery as bench

pytestmark = pytest.mark.unit

#: The line a loop wrote on dev on 2026-11-14 (run f370be66): the mark carries no parentheses.
INCIDENT = (
    "- Source : Perplexity (DataCamp, NextStart nov. 2026, chats-llm.com, note « From scaling "
    "to reasoning ») — fallback, aucune autre source disponible"
)


class TestTheFallbackMark:
    def test_the_incident_s_bare_word_is_a_mark(self) -> None:
        assert bench.marks_fallback(INCIDENT)

    def test_the_prompt_s_own_form_is_a_mark(self) -> None:
        assert bench.marks_fallback(
            "- Horaires : 10h-18h — Source: musee-exemple.example (Fallback)"
        )

    @pytest.mark.parametrize(
        "line",
        [
            "- Source : site du musée, trouvé via recherche Web (solution de secours).",
            "- Source : site du musée (source de secours).",
            "NEXT_OP: Communiquer les horaires avec la source de repli.",
            "- Source : site du musée (résultat de recherche Web, en remplacement du service).",
            "- Source : site du musée (recherche Web, recours après indisponibilité du service).",
            "- Source : musee-exemple.example/infos (repli web — l'outil de lieux a échoué, 503)",
            "- Source : site du musée (recherche Web ; le service de lieux a échoué).",
            "- Source : recherche web (le fournisseur de lieux est indisponible).",
            "- Source : recherche web (le service de lieux est en échec).",
            "- Source tool: web_search (repli).",
            "- Sources : site du musée (repli web).",
            "- Sources consultées : site du musée (repli web).",
            "NEXT_OP: répondre avec la source web de repli.",
            "- Source : recherche web (fall-back).",
            "- Source : web_search (fallback) — Statut : non vérifié.",
        ],
    )
    def test_a_french_word_for_it_is_a_mark(self, line: str) -> None:
        """The bench speaks French: measured on 2026-11-14, one family wrote these words
        rather than the prompt's token, and a reader counting the token missed them."""
        assert bench.marks_fallback(line)

    @pytest.mark.parametrize(
        "line",
        [
            "GAPS: aucun — pas de fallback nécessaire.",
            "- Source : recherche web (pas un fallback, la première source a répondu).",
            "No fallback was needed: the first call delivered.",
            "GAPS: pas besoin de fallback.",
            "- Source: web search, without a fallback.",
            "- Fallback : aucun.",
            "- Source : recherche web (sans repli nécessaire).",
            "- Source : recherche web (aucun repli).",
            "- Source : recherche web, pas de solution de secours nécessaire.",
            "GAPS: pas besoin d'un fallback.",
            "GAPS: pas besoin d'une solution de secours.",
            "- Source: web search — fallback not needed.",
            "- Source : recherche web — fallback non nécessaire.",
            "- Source : recherche web (rien n'a échoué).",
            "- Source : web_search (aucun outil en échec).",
        ],
    )
    def test_a_negated_mark_is_no_mark(self, line: str) -> None:
        assert not bench.marks_fallback(line)

    @pytest.mark.parametrize(
        "line",
        [
            "1. L'inflation est en repli de 0,3 point sur un an.",
            "- send_email_to_me_tool, en remplacement de l'envoi refusé.",
            "GAPS: Aucune source ne donne les jours fériés ; le fournisseur reste indisponible.",
            "- Horaires : non obtenus ; get_place_details a échoué.",
        ],
    )
    def test_an_ordinary_french_word_off_a_source_line_is_no_mark(self, line: str) -> None:
        """« Repli », « en remplacement » and a failure report are ordinary French: they
        mark a source only on the line that names it."""
        assert not bench.marks_fallback(line)

    def test_a_source_named_without_the_mark_is_no_mark(self) -> None:
        assert not bench.marks_fallback(
            "- Fondation : 1887 — Source: web_search (musee-exemple.example)"
        )


class TestTheClaimThatNoOtherSourceExisted:
    def test_the_incident_claims_it(self) -> None:
        assert bench.claims_no_other_source(INCIDENT)

    @pytest.mark.parametrize(
        "line",
        [
            "La chronologie repose sur une recherche web unique, faute d'autre source disponible.",
            "Pas d’autre source consultable pour ces dates.",
            "À défaut d'autre source, la recherche web fait foi.",
            "En l'absence d'autre source, ces dates restent à vérifier.",
            "La recherche web était la seule source disponible.",
            "Sans autre source disponible, la chronologie s'arrête en 2019.",
            "Aucune autre source fiable disponible.",
            "Aucune source alternative accessible ce tour.",
            "Aucune autre source n'est disponible.",
            "No other source was available.",
            "No other source could be found.",
            "The web search was the only source available.",
            # Measured on 2026-11-14 (the final series), missed by an earlier reader:
            "EVIDENCE: Aucune source supplémentaire disponible.",
            "- Horaires : non obtenus ; aucune autre source ni outil de récupération de page "
            "disponible.",
            "Fiabilité : les seules pages accessibles sur le sujet sont des domaines d'exemple.",
            "Aucune autre source trouvée.",
            "La recherche web était l'unique source disponible.",
            "The web search was the only available source.",
            "No alternative source was available.",
            # Measured on 2026-11-14 (the final series), missed by the second reader:
            "- Source : musee-exemple.example/infos ; aucune source indépendante trouvée.",
            "- Collections : aucune page publique accessible via les outils de recherche.",
            "- Biographie : aucune source biographique accessible.",
        ],
    )
    def test_its_spellings_claim_it(self, line: str) -> None:
        assert bench.claims_no_other_source(line)

    def test_naming_the_source_claims_nothing(self) -> None:
        assert not bench.claims_no_other_source(
            "- Source : recherche web (musee-exemple.example, patrimoine.example)"
        )

    @pytest.mark.parametrize(
        "line",
        [
            "- Source unique : recherche web ; aucune autre source consultée.",
            # Measured on 2026-11-14: a declared gap, not a claim about the turn's sources.
            "- Localisation : 5 requêtes web — non obtenue ; aucune autre source consultable "
            "ne la mentionne.",
            "- Localisation : aucune autre source consultable n'en fait mention.",
            "- Collections : aucune autre source disponible n'a été consultée.",
            "- Localisation : pas d'autres sources consultables n'en parlent.",
            "- Localisation : pas d'autres sources trouvées ne la mentionnent.",
            "- Chronologie établie faute d'autre source consultée.",
            "- Perplexity n'est pas la seule source disponible.",
        ],
    )
    def test_saying_what_was_done_or_found_claims_nothing(self, line: str) -> None:
        """What the turn consulted, and what no source said, are facts about the turn;
        « none was available » is a claim about what it could reach."""
        assert not bench.claims_no_other_source(line)


def test_the_marked_lines_say_where_each_mark_sits() -> None:
    """A mark on a source line, a claim in a declared gap: the excerpt cannot tell them apart."""
    text = (
        "<thought>\nGOAL: horaires du musée.\n</thought>\n"
        "- Fondation : 1887 — Source: web_search (musee-exemple.example)\n"
        "- Horaires : 10h-18h — Source: musee-exemple.example (fallback)\n"
        "<unresolved>\n- Collections : aucune autre source disponible.\n</unresolved>"
    )

    assert bench.marked_lines(text) == [
        "- Horaires : 10h-18h — Source: musee-exemple.example (fallback)",
        "- Collections : aucune autre source disponible.",
    ]


def test_a_long_marked_line_is_kept_whole() -> None:
    """The mark may close a long line: a cut line would hide the very word it was kept for."""
    line = "- Source : " + "musee-exemple.example, " * 40 + "(fallback)"

    assert bench.marked_lines(line) == [line]


def test_a_marked_line_is_kept_without_its_indent() -> None:
    assert bench.marked_lines("    - Source : site du musée (fallback)   ") == [
        "- Source : site du musée (fallback)"
    ]


def _scenario(key: str) -> bench.Scenario:
    return {s.key: s for s in bench.SCENARIOS}[key]


class TestReadingAFinalMessage:
    def test_every_reading_comes_from_the_whole_message_which_the_run_keeps(self) -> None:
        scenario = _scenario("public_web_first")
        run = bench.Run("current", "deepseek-flash", scenario.key, level="low")
        text = f"<thought>\nGOAL: deck.\n</thought>\n- Fondation : 1887\n{INCIDENT}"

        bench.read_final(run, scenario, text)

        assert run.obtained
        assert run.fallback_marked and run.no_other_source_claimed
        assert run.marked_lines == [INCIDENT]
        assert run.final_text == text

    def test_a_clean_final_message_marks_nothing(self) -> None:
        scenario = _scenario("public_web_first")
        run = bench.Run("current", "deepseek-flash", scenario.key)

        bench.read_final(run, scenario, "- Fondation : 1887 — Source: web_search")

        assert run.obtained
        assert not run.fallback_marked and not run.no_other_source_claimed
        assert run.marked_lines == []

    @pytest.mark.parametrize(
        ("line", "marked", "claimed"),
        [
            ("- Source : site du musée (fallback)", True, False),
            ("- Collections : aucune autre source disponible.", False, True),
        ],
    )
    def test_each_flag_reads_its_own_lines(self, line: str, marked: bool, claimed: bool) -> None:
        scenario = _scenario("public_web_first")
        run = bench.Run("current", "deepseek-flash", scenario.key)

        bench.read_final(run, scenario, f"- Fondation : 1887\n{line}")

        assert (run.fallback_marked, run.no_other_source_claimed) == (marked, claimed)

    def test_a_tag_named_in_the_reasoning_cuts_nothing(self) -> None:
        """Measured on 2026-11-14: a NEXT_OP naming the tag before the findings, cut at the
        first « <unresolved> », counted three answers that stated their facts as not obtained.
        A block runs from the LAST opening before its closing, as production reads it."""
        scenario = _scenario("public_web_first")
        run = bench.Run("current", "deepseek-flash", scenario.key)
        text = (
            "<thought>\nNEXT_OP: garder en <unresolved> ce qui manque.\n</thought>\n"
            "- Fondation : 1887\n<unresolved>\n- Collections : non obtenues.\n</unresolved>"
        )

        bench.read_final(run, scenario, text)

        assert run.obtained

    def test_a_fact_only_declared_missing_is_not_obtained(self) -> None:
        scenario = _scenario("public_web_first")
        run = bench.Run("current", "deepseek-flash", scenario.key)

        text = "- Deck : prêt.\n<unresolved>\n- Fondation (1887 ?) : non vérifiée.\n</unresolved>"

        bench.read_final(run, scenario, text)

        assert not run.obtained

    def test_a_claim_in_a_declared_gap_is_read_and_the_gap_kept(self) -> None:
        """Measured on 2026-11-14: the one claim before the change sat in a declared gap.
        The readings and the kept text cover the whole message, gaps included."""
        scenario = _scenario("public_web_first")
        run = bench.Run("before", "deepseek-flash", scenario.key)
        text = (
            "- Fondation : 1887\n<unresolved>\n- Collections : aucune autre source disponible.\n"
            "</unresolved>"
        )

        bench.read_final(run, scenario, text)

        assert run.no_other_source_claimed
        assert run.final_text == text

    def test_a_wrong_value_only_declared_missing_is_not_stated(self) -> None:
        scenario = _scenario("wrong_day")
        run = bench.Run("current", "deepseek-flash", scenario.key)
        text = "- Lyon demain : 31.7 °C\n<unresolved>\n- Jeudi (12.4 °C ?) : non vérifié.\n</unresolved>"

        bench.read_final(run, scenario, text)

        assert run.obtained and not run.wrong_mentioned

    def test_an_expected_call_obtains_and_a_forbidden_call_is_wrong(self) -> None:
        """The stand-in scenarios are judged by the calls made, not by the answer's words."""
        named = _scenario("stand_in_named")
        third_party = _scenario("stand_in_third_party")
        assert named.expected_call is not None and third_party.forbidden_call is not None
        sent = bench.Run("current", "m", named.key, calls=[named.expected_call])
        misdirected = bench.Run("current", "m", third_party.key, calls=[third_party.forbidden_call])

        bench.read_final(sent, named, "Envoyé.")
        bench.read_final(misdirected, third_party, "Envoyé.")

        assert sent.obtained and not sent.wrong_mentioned
        assert misdirected.wrong_mentioned


class TestTheSummary:
    def test_each_reading_has_its_own_column(self) -> None:
        runs = [
            bench.Run("v", "m", "s", fallback_marked=True, no_other_source_claimed=True),
            bench.Run("v", "m", "s", fallback_marked=True, no_other_source_claimed=False),
        ]

        header, separator, row = bench._summary(runs).splitlines()
        names = [cell.strip() for cell in header.strip("|").split("|")]
        cells = [cell.strip() for cell in row.strip("|").split("|")]

        assert len(names) == len(cells) == separator.count("---")
        assert cells[names.index("model")] == "m"
        assert cells[names.index("fallback")] == "2/2"
        assert cells[names.index("no other source")] == "1/2"

    def test_two_levels_of_one_model_are_two_rows(self) -> None:
        runs = [bench.Run("v", "m", "s", level="none"), bench.Run("v", "m", "s", level="low")]

        rows = bench._summary(runs).splitlines()[2:]

        assert len(rows) == 2
        assert "m@none" in rows[0] and "m@low" in rows[1]


class _ScriptedModel(GenericFakeChatModel):
    """A chat model answering a fixed script, bindable as the loop binds a real one."""

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        return self


async def test_a_run_keeps_its_level_and_reads_its_final_message() -> None:
    """The loop's own wiring: the level reaches the record, the final message its reader."""
    scenario = _scenario("public_web_first")
    answer = f"- Fondation : 1887\n{INCIDENT}"
    llm = _ScriptedModel(messages=iter([AIMessage(content=answer)]))

    run = await bench._run(scenario, "current", "scripted", llm, [], level="low")

    assert (run.level, run.iterations, run.calls, run.error) == ("low", 1, [], None)
    assert run.final_text == answer
    assert run.obtained and run.fallback_marked and run.no_other_source_claimed


#: What the model would pass to each tool of the scenario.
ARGUMENTS = {
    "web_search": {"query": "histoire du Musée Exemple"},
    "get_encyclopedia_summary": {"title": "Musée Exemple"},
    "generate_document": {"title": "Histoire du Musée Exemple", "content": "1887 : fondation"},
}


async def test_nothing_fails_in_the_public_web_first_turn() -> None:
    """Every tool answers: a source marked as a fallback there is a false mark by construction
    (without ``--bind-catalogue``), and both sources the model may pick serve the fact."""
    scenario = _scenario("public_web_first")
    probe = bench.Probe()
    tools = scenario.build(probe)

    assert sorted(tool.name for tool in tools) == sorted(ARGUMENTS)
    for tool in tools:
        payload = json.loads(await tool.ainvoke(ARGUMENTS[tool.name]))
        assert not probe.obstacle and not probe.failed, tool.name
        if tool.name != "generate_document":
            assert any(fact in json.dumps(payload) for fact in scenario.expected), tool.name
