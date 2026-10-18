"""Install bootstrap + provider contract (ADR-215, B10/B10-bis/B11).

What must hold:
- the derived current-core provider set is exactly openai/deepseek —
  machine-derived from code defaults merged with the PARSED seed overrides
  (the seed overrides every qwen code default to deepseek, and every slot
  absent from the seed defaults to openai, so qwen is NOT a required key);
- moving one core slot (code default or seed) outside the set turns the
  anti-drift red;
- the admin path has no default password, no --password argv, and calls
  validate_password_strict BEFORE any database work;
- the stdin payload is validated with stable non-secret codes (missing or
  unexpected provider keys, malformed JSON); the optional Gemini key is
  accepted when given and skipped when left empty;
- every seeded slot outside the core whose provider needs a key is declared
  optional, so the final report names everything an install leaves degraded;
- bootstrap performs admin + every required key upsert INSIDE one
  transaction and never mutates the seeded LLM overrides; what it reports
  degraded is read from the keys the database holds, in that transaction;
- no canary secret ever reaches stdout or exception text.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from scripts.data.bootstrap_install import (
    BootstrapInputError,
    bootstrap,
    parse_payload,
)
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.domains.llm_config.install_contract import (
    CURRENT_CORE_LLM_TYPES,
    CURRENT_CORE_PROVIDER_IDS,
    KEYLESS_SEEDED_PROVIDERS,
    OPTIONAL_INSTALL_PROVIDER_IDS,
    OPTIONAL_PLATFORM_CAPABILITIES,
    OPTIONAL_SEEDED_CAPABILITIES,
    effective_core_provider,
    required_current_core_provider_ids,
    seeded_provider_overrides,
    unkeyed_capabilities,
)

pytestmark = pytest.mark.unit

CANARY = "sk-CANARY-9f8e7d6c5b4a"
VALID_PAYLOAD = {
    "admin": {
        "email": "admin@ops.tld",
        "password": "Xx12!!abcdA9$Z",
        "full_name": "Ops",
    },
    "provider_keys": {"openai": CANARY, "deepseek": "dk"},
}


# ---------------------------------------------------------------------------
# Derived provider contract (B10-bis)
# ---------------------------------------------------------------------------


def test_derived_set_is_exactly_the_audited_baseline() -> None:
    assert required_current_core_provider_ids() == CURRENT_CORE_PROVIDER_IDS
    assert set(CURRENT_CORE_PROVIDER_IDS) == {"openai", "deepseek"}


def test_every_core_slot_resolves_inside_the_baseline() -> None:
    for llm_type in CURRENT_CORE_LLM_TYPES:
        assert effective_core_provider(llm_type) in CURRENT_CORE_PROVIDER_IDS


def test_seed_parse_matches_known_rows() -> None:
    overrides = seeded_provider_overrides()
    # Audited seed facts (B10-bis, re-audited 2026-08-15 on the regenerated
    # production extraction): planner moved deepseek → openai, response stays
    # deepseek — the DERIVED provider set is unchanged (deepseek, openai).
    assert overrides["planner"] == "openai"
    assert overrides["response"] == "deepseek"
    # A row that pins a model but no provider parses as None (the resolver then
    # falls back to the code default). ``briefing`` is such a row; ``router``
    # used to be the example here until ADR-244 removed the slot.
    assert overrides["briefing"] is None
    assert overrides["vision_analysis"] == "gemini"
    # 39 after ADR-244 removed the two dead slots and the mcp_excalidraw orphan.
    assert len(overrides) >= 39


def test_anti_drift_catches_an_out_of_set_slot() -> None:
    with patch(
        "src.domains.llm_config.install_contract.seeded_provider_overrides",
        return_value={**seeded_provider_overrides(), "planner": "anthropic"},
    ):
        assert "anthropic" in required_current_core_provider_ids()
        assert (
            required_current_core_provider_ids() != CURRENT_CORE_PROVIDER_IDS
        ), "a third-party core slot must change the derived set (CI red)"


def test_every_keyed_slot_outside_the_core_is_declared_optional() -> None:
    """The declaration is held equal to the post-seed derivation, both ways.

    It was an audited snapshot, and the snapshot drifted: ``voice_transcription``
    moved to ElevenLabs and no installer report ever named it.
    """
    seeded = seeded_provider_overrides()
    derived = {
        llm_type: provider
        for llm_type in LLM_DEFAULTS
        if (provider := seeded.get(llm_type) or LLM_DEFAULTS[llm_type].provider)
        not in CURRENT_CORE_PROVIDER_IDS
        and provider not in KEYLESS_SEEDED_PROVIDERS
    }
    assert OPTIONAL_SEEDED_CAPABILITIES == derived


def test_what_needs_a_key_no_slot_names_can_be_given_one_at_install() -> None:
    assert set(OPTIONAL_PLATFORM_CAPABILITIES.values()) <= set(OPTIONAL_INSTALL_PROVIDER_IDS)


def test_a_given_key_takes_its_capabilities_off_the_degraded_list() -> None:
    core = frozenset(CURRENT_CORE_PROVIDER_IDS)
    without = unkeyed_capabilities(core)
    with_gemini = unkeyed_capabilities(core | {"gemini"})

    assert without["semantic_search"] == "gemini"
    assert without["vision_analysis"] == "gemini"
    assert "semantic_search" not in with_gemini and "vision_analysis" not in with_gemini
    assert with_gemini["voice_tts"] == "elevenlabs"


# ---------------------------------------------------------------------------
# Admin path hardening (B11)
# ---------------------------------------------------------------------------


def test_admin_script_has_no_default_password_or_argv_secret() -> None:
    import scripts.data.create_admin as create_admin
    from tests._repo_paths import repo_root_or_skip

    body = (repo_root_or_skip() / "apps/api/scripts/data/create_admin.py").read_text(
        encoding="utf-8"
    )
    assert "admin123" not in body
    assert '"--password"' not in body
    assert hasattr(create_admin, "ensure_admin")


async def test_ensure_admin_validates_before_any_query() -> None:
    from scripts.data.create_admin import ensure_admin

    db = MagicMock()
    db.execute = AsyncMock()
    with pytest.raises(ValueError):
        await ensure_admin(db, email="a@b.c", password="weak", full_name="X")
    db.execute.assert_not_awaited()


async def test_a_new_admin_speaks_the_instance_s_configured_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Left to the DDL default, the first administrator was French whatever
    DEFAULT_LANGUAGE said (ADR-323)."""
    from scripts.data.create_admin import ensure_admin
    from src.core.config import settings
    from src.core.constants import (
        PASSWORD_MIN_DIGITS,
        PASSWORD_MIN_LENGTH,
        PASSWORD_MIN_SPECIAL,
        PASSWORD_MIN_UPPERCASE,
        PASSWORD_SPECIAL_CHARS,
    )

    configured = "de"  # not "fr", the DDL default
    monkeypatch.setattr(settings, "default_language", configured)
    nobody = MagicMock()
    nobody.fetchone.return_value = None
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[nobody, MagicMock()])
    db.flush = AsyncMock()

    required = (
        "A" * PASSWORD_MIN_UPPERCASE
        + "1" * PASSWORD_MIN_DIGITS
        + PASSWORD_SPECIAL_CHARS[0] * PASSWORD_MIN_SPECIAL
    )
    password = required + "a" * max(0, PASSWORD_MIN_LENGTH - len(required))
    await ensure_admin(db, email="admin@example.com", password=password, full_name="Admin")

    insert_params = db.execute.await_args_list[1].args[1]
    assert insert_params["language"] == configured


# ---------------------------------------------------------------------------
# Payload validation (stable non-secret codes)
# ---------------------------------------------------------------------------


def test_valid_payload_parses() -> None:
    payload = parse_payload(json.dumps(VALID_PAYLOAD))
    assert payload.provider_keys == VALID_PAYLOAD["provider_keys"]


def test_the_optional_gemini_key_is_accepted_when_given() -> None:
    document = {
        **VALID_PAYLOAD,
        "provider_keys": {**VALID_PAYLOAD["provider_keys"], "gemini": "gk"},
    }
    payload = parse_payload(json.dumps(document))
    assert payload.provider_keys == {**VALID_PAYLOAD["provider_keys"], "gemini": "gk"}


def test_an_optional_key_left_empty_is_no_key() -> None:
    document = {
        **VALID_PAYLOAD,
        "provider_keys": {**VALID_PAYLOAD["provider_keys"], "gemini": ""},
    }
    payload = parse_payload(json.dumps(document))
    assert payload.provider_keys == VALID_PAYLOAD["provider_keys"]


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("not-json", "invalid_json"),
        (json.dumps({}), "missing_sections"),
        (
            json.dumps({"admin": {"email": "a@b.c"}, "provider_keys": {}}),
            "missing_admin_fields",
        ),
        (
            # Same rule as the login route: an admin bootstrapped with a
            # special-use TLD could never log in (v1.30.1 qualification).
            json.dumps(
                {
                    "admin": {**VALID_PAYLOAD["admin"], "email": "a@smoke.invalid"},
                    "provider_keys": VALID_PAYLOAD["provider_keys"],
                }
            ),
            "invalid_admin_email",
        ),
        (
            json.dumps(
                {
                    "admin": VALID_PAYLOAD["admin"],
                    "provider_keys": {"openai": "x", "qwen": "y"},
                }
            ),
            "missing_provider_keys:deepseek",
        ),
        (
            json.dumps(
                {
                    "admin": VALID_PAYLOAD["admin"],
                    "provider_keys": {
                        **VALID_PAYLOAD["provider_keys"],
                        "anthropic": "z",
                    },
                }
            ),
            "unexpected_provider_keys:anthropic",
        ),
    ],
)
def test_payload_errors_are_stable_and_value_free(raw: str, code: str) -> None:
    with pytest.raises(BootstrapInputError) as excinfo:
        parse_payload(raw)
    assert str(excinfo.value) == code
    assert CANARY not in str(excinfo.value)


# ---------------------------------------------------------------------------
# Transactional bootstrap
# ---------------------------------------------------------------------------


def _fake_db(
    stored: tuple[str, ...] = ("deepseek", "openai"), events: list[str] | None = None
) -> MagicMock:
    """A session whose transaction and stored-keys read are recorded in ``events``.

    ``stored``: the providers ``provider_api_keys`` answers with.
    """
    record = events if events is not None else []
    db = MagicMock()
    begin_ctx = MagicMock()

    async def _begin(*_args: object) -> None:
        record.append("begin")

    async def _commit(*_args: object) -> bool:
        record.append("commit")
        return False

    async def _scalars(*_args: object, **_kwargs: object) -> MagicMock:
        record.append("read_stored_keys")
        return MagicMock(all=MagicMock(return_value=list(stored)))

    begin_ctx.__aenter__ = AsyncMock(side_effect=_begin)
    begin_ctx.__aexit__ = AsyncMock(side_effect=_commit)
    db.begin = MagicMock(return_value=begin_ctx)
    db.scalars = AsyncMock(side_effect=_scalars)
    return db


async def test_bootstrap_runs_everything_inside_one_transaction(
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = parse_payload(json.dumps(VALID_PAYLOAD))
    calls: list[str] = []
    db = _fake_db(events=calls)
    admin_id = uuid4()

    async def _ensure(*_args, **_kwargs):
        calls.append("admin")
        return admin_id

    async def _upsert(_db, *, provider, key, updated_by):
        assert updated_by == admin_id
        calls.append(f"key:{provider}")

    with (
        patch("scripts.data.create_admin.ensure_admin", side_effect=_ensure),
        patch(
            "src.domains.llm_config.service.upsert_provider_key_uncommitted",
            side_effect=_upsert,
        ),
        patch(
            "src.domains.llm_config.cache.LLMConfigOverrideCache.invalidate_and_reload",
            new=AsyncMock(),
        ),
    ):
        result = await bootstrap(payload, db)

    assert calls[:2] == ["begin", "admin"]
    assert sorted(calls[2:4]) == ["key:deepseek", "key:openai"]
    # The stored keys are read after the writes, before the commit.
    assert calls[4:] == ["read_stored_keys", "commit"]
    db.begin.assert_called_once()  # ONE transaction wraps admin + all keys
    assert result.status == "bootstrapped"
    assert result.optional_unkeyed == unkeyed_capabilities(frozenset({"openai", "deepseek"}))
    assert result.optional_unkeyed["semantic_search"] == "gemini"
    # The result never carries a secret.
    assert CANARY not in json.dumps(
        {
            "status": result.status,
            "providers": list(result.providers),
            "optional": result.optional_unkeyed,
        }
    )


async def test_the_degraded_list_counts_the_keys_the_database_already_holds() -> None:
    """A resume that skips the optional key again keeps the row an earlier run stored.

    The list was computed from this run's payload: the resumed install was told
    semantic search and vision were degraded while the Gemini row sat in the table.
    """
    payload = parse_payload(json.dumps(VALID_PAYLOAD))
    assert "gemini" not in payload.provider_keys
    db = _fake_db(stored=("deepseek", "gemini", "openai"))
    with (
        patch(
            "scripts.data.create_admin.ensure_admin",
            new=AsyncMock(return_value=uuid4()),
        ),
        patch(
            "src.domains.llm_config.service.upsert_provider_key_uncommitted",
            new=AsyncMock(),
        ),
        patch(
            "src.domains.llm_config.cache.LLMConfigOverrideCache.invalidate_and_reload",
            new=AsyncMock(),
        ),
    ):
        result = await bootstrap(payload, db)

    assert result.optional_unkeyed == unkeyed_capabilities(
        frozenset({"deepseek", "gemini", "openai"})
    )
    assert "semantic_search" not in result.optional_unkeyed
    assert "vision_analysis" not in result.optional_unkeyed
    assert result.optional_unkeyed["voice_tts"] == "elevenlabs"
    # The keys this run wrote are still the ones it reports writing.
    assert result.providers == ("deepseek", "openai")


async def test_failure_on_second_provider_propagates_from_the_transaction() -> None:
    payload = parse_payload(json.dumps(VALID_PAYLOAD))
    db = _fake_db()

    async def _boom(_db, *, provider, key, updated_by):
        if provider != sorted(payload.provider_keys)[0]:
            raise RuntimeError("db down")

    with (
        patch(
            "scripts.data.create_admin.ensure_admin",
            new=AsyncMock(return_value=uuid4()),
        ),
        patch(
            "src.domains.llm_config.service.upsert_provider_key_uncommitted",
            side_effect=_boom,
        ),
    ):
        with pytest.raises(RuntimeError, match="db down"):
            await bootstrap(payload, db)
    # The context manager owns rollback: everything ran inside db.begin().
    db.begin.assert_called_once()


async def test_publication_failure_returns_stable_status() -> None:
    payload = parse_payload(json.dumps(VALID_PAYLOAD))
    db = _fake_db()
    with (
        patch(
            "scripts.data.create_admin.ensure_admin",
            new=AsyncMock(return_value=uuid4()),
        ),
        patch(
            "src.domains.llm_config.service.upsert_provider_key_uncommitted",
            new=AsyncMock(),
        ),
        patch(
            "src.domains.llm_config.cache.LLMConfigOverrideCache.invalidate_and_reload",
            new=AsyncMock(side_effect=ConnectionError("redis down")),
        ),
    ):
        result = await bootstrap(payload, db)
    assert result.status == "bootstrapped_publication_failed"


# ---------------------------------------------------------------------------
# Hermetic base-URL overrides (qualification seam)
# ---------------------------------------------------------------------------


def test_openai_and_deepseek_have_base_url_defaults() -> None:
    from src.infrastructure.llm.providers.adapter import _BASE_URL_DEFAULTS

    assert _BASE_URL_DEFAULTS["openai"] == "https://api.openai.com/v1"
    assert _BASE_URL_DEFAULTS["deepseek"] == "https://api.deepseek.com"


def test_base_url_env_overrides_are_honored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infrastructure.llm.providers.adapter import _get_base_url

    monkeypatch.setenv("OPENAI_BASE_URL", "http://fake:18080/v1")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "http://fake:18080/v1")
    assert _get_base_url("openai") == "http://fake:18080/v1"
    assert _get_base_url("deepseek") == "http://fake:18080/v1"


def test_responses_adapter_accepts_base_url() -> None:
    import inspect

    from src.infrastructure.llm.providers.responses_adapter import (
        create_responses_llm,
    )

    assert "base_url" in inspect.signature(create_responses_llm).parameters
