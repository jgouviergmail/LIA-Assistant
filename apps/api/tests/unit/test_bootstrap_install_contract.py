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
  unexpected provider keys, malformed JSON);
- bootstrap performs admin + every required key upsert INSIDE one
  transaction and never mutates the seeded LLM overrides;
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
from src.domains.llm_config.install_contract import (
    CURRENT_CORE_LLM_TYPES,
    CURRENT_CORE_PROVIDER_IDS,
    OPTIONAL_SEEDED_CAPABILITIES,
    effective_core_provider,
    required_current_core_provider_ids,
    seeded_provider_overrides,
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
    # Audited seed facts (B10-bis): deepseek core rows + NULL router.
    assert overrides["planner"] == "deepseek"
    assert overrides["response"] == "deepseek"
    assert overrides["router"] is None
    assert overrides["vision_analysis"] == "gemini"
    assert len(overrides) >= 41


def test_anti_drift_catches_an_out_of_set_slot() -> None:
    with patch(
        "src.domains.llm_config.install_contract.seeded_provider_overrides",
        return_value={**seeded_provider_overrides(), "planner": "anthropic"},
    ):
        assert "anthropic" in required_current_core_provider_ids()
        assert (
            required_current_core_provider_ids() != CURRENT_CORE_PROVIDER_IDS
        ), "a third-party core slot must change the derived set (CI red)"


def test_optional_capabilities_are_the_audited_trio() -> None:
    assert OPTIONAL_SEEDED_CAPABILITIES == {
        "vision_analysis": "gemini",
        "voice_tts": "elevenlabs",
        "mcp_app_react_agent": "anthropic",
    }


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


# ---------------------------------------------------------------------------
# Payload validation (stable non-secret codes)
# ---------------------------------------------------------------------------


def test_valid_payload_parses() -> None:
    payload = parse_payload(json.dumps(VALID_PAYLOAD))
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
                        "gemini": "z",
                    },
                }
            ),
            "unexpected_provider_keys:gemini",
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


def _fake_db() -> MagicMock:
    db = MagicMock()
    begin_ctx = MagicMock()
    begin_ctx.__aenter__ = AsyncMock(return_value=None)
    begin_ctx.__aexit__ = AsyncMock(return_value=False)
    db.begin = MagicMock(return_value=begin_ctx)
    return db


async def test_bootstrap_runs_everything_inside_one_transaction(
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = parse_payload(json.dumps(VALID_PAYLOAD))
    db = _fake_db()
    admin_id = uuid4()
    calls: list[str] = []

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

    assert calls[0] == "admin"
    assert sorted(calls[1:]) == ["key:deepseek", "key:openai"]
    db.begin.assert_called_once()  # ONE transaction wraps admin + all keys
    assert result.status == "bootstrapped"
    assert result.optional_unkeyed == OPTIONAL_SEEDED_CAPABILITIES
    # The result never carries a secret.
    assert CANARY not in json.dumps(
        {
            "status": result.status,
            "providers": list(result.providers),
            "optional": result.optional_unkeyed,
        }
    )


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
