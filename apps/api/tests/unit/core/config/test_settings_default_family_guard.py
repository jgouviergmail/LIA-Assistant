"""Guard: a settings field reads its default from a constant of its OWN family.

``openai_organization_id`` defaulted to ``CONTACTS_AGENT_LLM_MODEL_DEFAULT`` from
2026-03 to 2026-10, and a configuration-alignment pass later filled that
constant with the maintainer's real organization id: every installation the
installer wrote presented it to OpenAI with its own key (ADR-244 amendment
2026-10-18 b). Three ``hitl_*_llm_provider`` fields read ``HEARTBEAT_*``
constants the same way. A borrowed default is invisible where it is declared —
the field reads fine, the constant reads fine — so it is checked here.

The family of a name is its first word (a leading ``DEFAULT_`` is skipped):
``brave_search_cache_ttl_seconds`` may read ``BRAVE_SEARCH_CACHE_TTL``, a
spelling variant of its own setting. A field reading a constant of another
family is refused unless it is declared below with the reason it is right. The
table is shrink-only: an entry that no longer matches a field fails too, so a
fixed pair cannot leave a stale excuse behind.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CONFIG_DIR = Path(__file__).resolve().parents[4] / "src" / "core" / "config"

#: (field, constant) -> why reading another family's constant is right.
DECLARED_BORROWINGS: dict[tuple[str, str], str] = {
    ("effect_result_payload_max_bytes", "AGENT_EFFECT_RESULT_PAYLOAD_MAX_BYTES_DEFAULT"): (
        "the effect register is the agents' (ADR-263); the field drops the prefix"
    ),
    (
        "effect_claimed_orphan_staleness_seconds",
        "AGENT_EFFECT_CLAIMED_ORPHAN_STALENESS_SECONDS_DEFAULT",
    ): ("the effect register is the agents' (ADR-263); the field drops the prefix"),
    ("effect_label_value_max_chars", "AGENT_EFFECT_LABEL_VALUE_MAX_CHARS_DEFAULT"): (
        "the effect register is the agents' (ADR-263); the field drops the prefix"
    ),
    ("effect_export_batch_rows", "AGENT_EFFECT_EXPORT_BATCH_ROWS_DEFAULT"): (
        "the effect register is the agents' (ADR-263); the field drops the prefix"
    ),
    ("response_recent_entities_max_turn_age", "RECENT_ENTITIES_MAX_TURN_AGE_DEFAULT"): (
        "the recent-entities window is one rule; the response node is its reader"
    ),
    ("response_recent_entities_max_items", "RECENT_ENTITIES_MAX_ITEMS_DEFAULT"): (
        "the recent-entities window is one rule; the response node is its reader"
    ),
    ("contacts_cache_list_ttl_seconds", "GOOGLE_CONTACTS_LIST_CACHE_TTL"): (
        "the contacts cache constants carry the provider name of their first client"
    ),
    ("contacts_cache_search_ttl_seconds", "GOOGLE_CONTACTS_SEARCH_CACHE_TTL"): (
        "the contacts cache constants carry the provider name of their first client"
    ),
    ("contacts_cache_details_ttl_seconds", "GOOGLE_CONTACTS_DETAILS_CACHE_TTL"): (
        "the contacts cache constants carry the provider name of their first client"
    ),
    ("emails_body_part_tokens", "EMAIL_BODY_PART_TOKENS_DEFAULT"): (
        "singular and plural of one domain (`email`, the registry's own noun)"
    ),
    ("hue_bridge_timeout_seconds", "HTTP_TIMEOUT_HUE_API"): (
        "every external HTTP timeout lives in the HTTP_TIMEOUT_* registry"
    ),
    ("conversation_id_cache_ttl_seconds", "REDIS_CONVERSATION_ID_TTL_SECONDS_DEFAULT"): (
        "the constant names the store the cache lives in"
    ),
    ("live_voice_sample_model", "GEMINI_TTS_SAMPLE_MODEL_DEFAULT"): (
        "the Live voice sample runs on the one Gemini TTS client (ADR-299), "
        "so both read one model"
    ),
    ("algorithm", "JWT_ALGORITHM_DEFAULT"): "the field predates the family prefix",
}


def _family(name: str) -> str:
    """First word of a setting or constant name, ``DEFAULT_`` skipped."""
    parts = name.lower().split("_")
    if parts[0] == "default" and len(parts) > 1:
        parts = parts[1:]
    return parts[0]


def _default_constant(value: ast.expr | None) -> str | None:
    """The bare UPPER constant a field's default reads, if any."""
    if isinstance(value, ast.Call):
        for keyword in value.keywords:
            if keyword.arg == "default" and isinstance(keyword.value, ast.Name):
                return keyword.value.id
        return None
    if isinstance(value, ast.Name):
        return value.id
    return None


def _borrowings(config_dir: Path = CONFIG_DIR) -> set[tuple[str, str]]:
    """Every (field, constant) pair whose two names name different families."""
    pairs: set[tuple[str, str]] = set()
    for path in sorted(config_dir.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.ClassDef):
                continue
            for statement in node.body:
                if not isinstance(statement, ast.AnnAssign):
                    continue
                if not isinstance(statement.target, ast.Name):
                    continue
                constant = _default_constant(statement.value)
                if constant is None or not constant.isupper():
                    continue
                if _family(constant) != _family(statement.target.id):
                    pairs.add((statement.target.id, constant))
    return pairs


@pytest.mark.unit
def test_no_setting_borrows_another_familys_default() -> None:
    """A default read from another family's constant is declared, with its reason."""
    undeclared = sorted(_borrowings() - DECLARED_BORROWINGS.keys())
    assert not undeclared, (
        "Settings reading a constant named for ANOTHER setting: give the field a "
        f"constant of its own, or declare why the borrowing is right: {undeclared}"
    )


@pytest.mark.unit
def test_every_declared_borrowing_still_exists() -> None:
    """The table only shrinks: a pair that no longer exists leaves it."""
    stale = sorted(DECLARED_BORROWINGS.keys() - _borrowings())
    assert not stale, f"Remove these entries from DECLARED_BORROWINGS: {stale}"


@pytest.mark.unit
def test_the_scan_catches_the_incident_shape(tmp_path: Path) -> None:
    """The scan reports the very pair that leaked an organization id, and no variant."""
    (tmp_path / "llm.py").write_text(
        "class LLMSettings(BaseSettings):\n"
        "    openai_organization_id: str = Field(default=CONTACTS_AGENT_LLM_MODEL_DEFAULT)\n"
        "    brave_search_cache_ttl_seconds: int = Field(default=BRAVE_SEARCH_CACHE_TTL)\n"
        "    background_runs_stream_maxlen: int = DEFAULT_BACKGROUND_RUNS_STREAM_MAXLEN\n",
        encoding="utf-8",
    )
    assert _borrowings(tmp_path) == {("openai_organization_id", "CONTACTS_AGENT_LLM_MODEL_DEFAULT")}
