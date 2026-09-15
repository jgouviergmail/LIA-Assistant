"""The response prompt's dynamic tail: one wrapper per context, none when empty.

Prompt audit 2026-09-12 (A.2), measured by assembling the real prompt:

- ``prompts/__init__.py`` wrapped the RAG context in ``<RAGDocuments>`` (« always
  synthesize ») and the base file wrapped THAT in ``<UserDocuments>`` (« always cite »)
  — the same for the journal, the web search and the app knowledge;
- on a turn with no context the file still emitted six empty wrappers with their
  instruction, 246 tokens in the uncached tail of every turn, plus French literals
  such as « (aucun besoin anticipé) » under an instruction to weave them in;
- every value was escaped for ``ChatPromptTemplate`` inside ``get_response_prompt``
  AND the response node escaped the whole prompt again, so a query ``r={x}``
  reached the model as ``r={{x}}``.

These tests read the assembled prompt, never the file.
"""

from __future__ import annotations

import re

import pytest
from langchain_core.prompts import ChatPromptTemplate

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.core.prompt_store import parse_prompt_sections
from src.domains.agents.prompts import escape_braces, get_response_prompt, load_prompt

_EMPTY_WRAPPER = re.compile(r"<(\w+)(?:\s[^>]*)?>\s*</\1>")
_FRENCH_LITERALS = ("(aucun", "(pas de")


def _tail(prompt: str) -> str:
    return prompt[prompt.rfind(DYNAMIC_CONTEXT_MARKER) :]


def _bare_turn() -> str:
    return get_response_prompt(user_language="fr", user_query="salut")


class TestBareTurn:
    def test_no_empty_wrapper(self) -> None:
        tail = _tail(_bare_turn())
        assert not _EMPTY_WRAPPER.findall(tail), _EMPTY_WRAPPER.findall(tail)

    def test_no_french_literal(self) -> None:
        prompt = _bare_turn()
        assert not any(lit in prompt for lit in _FRENCH_LITERALS)

    def test_no_instruction_about_absent_content(self) -> None:
        tail = _tail(_bare_turn())
        assert "Weave ONE or TWO" not in tail
        assert "DIRECTIVE DE SÉCURITÉ ÉMOTIONNELLE" not in tail
        assert "<History>" not in tail  # the static <DataAuthority> may cite it

    def test_temporal_context_and_query_are_always_there(self) -> None:
        tail = _tail(_bare_turn())
        assert "<TemporalContext>" in tail
        assert "<UserQuery>" in tail and "salut" in tail

    def test_no_run_of_blank_lines(self) -> None:
        assert not re.search(r"\n{3,}", _tail(_bare_turn()).replace("\r\n", "\n"))


class TestOneWrapperPerContext:
    @pytest.mark.parametrize(
        ("kwarg", "tag", "legacy_inner_tag"),
        [
            ("rag_context", "UserDocuments", "RAGDocuments"),
            ("journal_context", "JournalContext", None),
            ("knowledge_context", "WebSearchContext", "KnowledgeEnrichment"),
            ("app_knowledge_context", "AppKnowledge", None),
        ],
    )
    def test_context_is_wrapped_exactly_once(
        self, kwarg: str, tag: str, legacy_inner_tag: str | None
    ) -> None:
        prompt = get_response_prompt(user_language="fr", user_query="q", **{kwarg: "CONTENT-42"})
        assert prompt.count(f"<{tag}") == 1, prompt.count(f"<{tag}")
        assert prompt.count(f"</{tag}>") == 1
        if legacy_inner_tag:
            assert f"<{legacy_inner_tag}" not in prompt
        assert "CONTENT-42" in prompt

    def test_description_comes_from_the_sections_file_once(self) -> None:
        sections = {
            k: (tag, desc)
            for k, tag, desc in parse_prompt_sections(load_prompt("response_context_sections"), 3)
        }
        tag, desc = sections["rag_context"]
        prompt = get_response_prompt(user_language="fr", user_query="q", rag_context="DOC")
        assert prompt.count(desc) == 1
        assert f"<{tag}>" in prompt

    def test_anticipated_needs_present_only_when_given(self) -> None:
        with_needs = get_response_prompt(
            user_language="fr", user_query="q", anticipated_needs=["may want a reminder"]
        )
        assert "<AnticipatedNeeds>" in with_needs and "- may want a reminder" in with_needs
        assert "Weave ONE or TWO" in with_needs

    def test_history_present_only_when_given(self) -> None:
        prompt = get_response_prompt(
            user_language="fr", user_query="q", conversation_history="user: hello"
        )
        assert "<History>" in prompt and "user: hello" in prompt

    def test_psychological_profile_present_only_when_given(self) -> None:
        prompt = get_response_prompt(
            user_language="fr", user_query="q", psychological_profile="PROFILE-7"
        )
        assert "<PsychologicalProfile>" in prompt and "PROFILE-7" in prompt
        assert "DIRECTIVE DE SÉCURITÉ ÉMOTIONNELLE" in prompt

    def test_every_declared_section_is_a_parameter_of_the_assembler(self) -> None:
        """A section nobody can fill is prose the model never sees."""
        import inspect

        params = set(inspect.signature(get_response_prompt).parameters)
        keys = [
            k
            for k, _tag, _desc in parse_prompt_sections(load_prompt("response_context_sections"), 3)
        ]
        assert keys, "sections file is empty"
        assert set(keys) <= params, set(keys) - params


class TestBracesReachTheModelOnce:
    def test_query_braces_are_not_escaped_by_the_assembler(self) -> None:
        prompt = get_response_prompt(user_language="fr", user_query="r={x}")
        assert "r={x}" in prompt and "{{x}}" not in prompt

    def test_through_the_response_node_escape_and_the_template(self) -> None:
        """What the response node does: escape the WHOLE prompt once, then template it."""
        prompt = get_response_prompt(
            user_language="fr",
            user_query="r={x}",
            rag_context='{"json": true}',
            conversation_history="user: \\frac{d}{2}",
        )
        rendered = ChatPromptTemplate.from_messages(
            [("system", escape_braces(prompt))]
        ).format_messages()
        content = str(rendered[0].content)
        assert "r={x}" in content and "r={{x}}" not in content
        assert '{"json": true}' in content
        assert "\\frac{d}{2}" in content
