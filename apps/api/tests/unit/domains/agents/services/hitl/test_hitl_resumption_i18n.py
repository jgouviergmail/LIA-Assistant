"""HITL resumption reformulations (EDIT/REJECT) must be localized, never French.

When a user EDITs a HITL draft/plan, the reformulated intent replaces the
original user message in the conversation — it impersonates the user's voice and
is visible, so it must be in the user's language. Likewise the enriched message
injected on a tool-level REJECT is added to the conversation. A hardcoded French
phrase leaks into a German/Chinese user's transcript.
"""

from __future__ import annotations

import pytest

from src.core.i18n_hitl import (
    _REFORMULATION_TEMPLATES,
    HitlMessages,
    ReformulationKind,
)
from src.domains.agents.services.hitl.resumption_strategies import (
    build_edit_reformulated_intent,
    resolve_user_language,
)

pytestmark = [pytest.mark.unit]


async def test_resolve_user_language_reads_checkpointed_state() -> None:
    from unittest.mock import AsyncMock, MagicMock

    snapshot = MagicMock()
    snapshot.values = {"user_language": "de"}
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=snapshot)

    assert await resolve_user_language(graph, MagicMock()) == "de"


async def test_resolve_user_language_falls_back_on_error() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from src.core.i18n import DEFAULT_LANGUAGE

    graph = MagicMock()
    graph.aget_state = AsyncMock(side_effect=RuntimeError("checkpoint unreachable"))

    assert await resolve_user_language(graph, MagicMock()) == DEFAULT_LANGUAGE


def test_get_reformulation_is_localized() -> None:
    K = ReformulationKind
    assert HitlMessages.get_reformulation(K.SEARCH_QUERY, "de", value="jean") == "suche jean"
    assert HitlMessages.get_reformulation(K.SEARCH_QUERY, "zh-CN", value="jean") == "搜索 jean"
    assert HitlMessages.get_reformulation(K.SEND_TO, "it", value="marie") == "invia a marie"


def test_reformulation_templates_are_exhaustive() -> None:
    """Every ReformulationKind has a template in all six languages.

    Guarantees ``get_reformulation`` never fails or returns an empty message for
    a valid kind (the language coverage itself is enforced by the i18n parity
    guard; this asserts kind coverage).
    """
    from src.core.i18n import SUPPORTED_LANGUAGES

    missing_kinds = set(ReformulationKind) - set(_REFORMULATION_TEMPLATES)
    assert not missing_kinds, f"reformulation templates missing kinds: {sorted(missing_kinds)}"
    for kind, langs in _REFORMULATION_TEMPLATES.items():
        missing_langs = set(SUPPORTED_LANGUAGES) - set(langs)
        assert not missing_langs, f"{kind}: missing languages {sorted(missing_langs)}"


def test_get_reject_enriched_message_is_localized() -> None:
    de = HitlMessages.get_reject_enriched_message("nein", "de")
    assert "BENUTZERABLEHNUNG" in de
    assert "nein" in de
    assert "REFUS" not in de and "L'utilisateur" not in de

    zh = HitlMessages.get_reject_enriched_message("取消", "zh")  # frontend spelling → zh-CN
    assert "用户拒绝" in zh
    assert "REFUS" not in zh


def test_build_edit_reformulated_intent_localized_de() -> None:
    mods = [{"modification_type": "edit_params", "new_parameters": {"query": "jean"}}]
    assert build_edit_reformulated_intent(mods, "de") == "suche jean"


def test_build_edit_reformulated_intent_localized_zh() -> None:
    mods = [{"modification_type": "edit_params", "new_parameters": {"to": "marie@example.com"}}]
    assert build_edit_reformulated_intent(mods, "zh") == "发送给 marie@example.com"


def test_build_edit_reformulated_intent_generic_fallback_localized() -> None:
    mods = [{"modification_type": "edit_params", "new_parameters": {"count": 10}}]
    result = build_edit_reformulated_intent(mods, "de")
    assert result is not None
    assert "exécute" not in result  # no French
    assert "count=10" in result
