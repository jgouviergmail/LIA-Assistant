"""Fresh seed and repair preserve the last published OCEAN/PAD profiles."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit
ROOT = repo_root_or_skip()
VERSIONS = ROOT / "apps/api/alembic/versions"
REPAIR = VERSIONS / "2026_10_16_0900-b62a8d193f04_repair_personality_traits_seed.py"
ORIGINAL = VERSIONS / "2026_04_01_0003-assign_big_five_traits_to_personalities.py"
SEED = ROOT / "infrastructure/database/seeds/personalities_seed.sql"
VERIFY = ROOT / "infrastructure/database/seeds/verify_reference_seeds.sql"
TRAITS = (
    "trait_openness",
    "trait_conscientiousness",
    "trait_extraversion",
    "trait_agreeableness",
    "trait_neuroticism",
)
PADS = ("pad_pleasure_override", "pad_arousal_override", "pad_dominance_override")
CODES = (
    "cynic",
    "normal",
    "depressed",
    "enthusiastic",
    "friend",
    "philosopher",
    "influencer",
    "professor",
    "rasta",
    "teenager",
    "jarvis",
    "haipai",
    "trump",
    "antagonist",
)


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CANONICAL = {
    code: (UUID(row[0]), tuple(row[1:]))
    for code, row in zip(CODES, _load(ORIGINAL).PERSONALITY_TRAITS, strict=True)
}
CURRENT_ANTAGONIST_ID = UUID("61178ee5-76e1-4984-a983-0f451dc74305")


@pytest.fixture
def database():
    """Execute real SQL against isolated tables, without application DB or provider."""
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    profiles = sa.Table(
        "personalities",
        metadata,
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("code", sa.String, nullable=False),
        sa.Column("is_default", sa.Boolean),
        *(sa.Column(name, sa.Float) for name in (*TRAITS, *PADS)),
    )
    users = sa.Table(
        "users",
        metadata,
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("personality_id", sa.Uuid),
    )
    states = sa.Table(
        "psyche_states",
        metadata,
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("user_id", sa.Uuid),
        *(sa.Column(name, sa.Float) for name in TRAITS),
        sa.Column("mood_pleasure", sa.Float),
        sa.Column("relationship_trust", sa.Float),
        sa.Column("self_efficacy", sa.JSON),
        sa.Column("active_emotions", sa.JSON),
    )
    metadata.create_all(engine)
    try:
        with engine.begin() as connection:
            yield connection, profiles, users, states
    finally:
        engine.dispose()


def _repair(connection, monkeypatch):
    module = _load(REPAIR)
    monkeypatch.setattr(module.op, "get_bind", lambda: connection)
    module.upgrade()


def _profile(connection, profiles, code="cynic", **values):
    identifier = CANONICAL[code][0]
    connection.execute(
        profiles.insert().values(id=identifier, code=code, is_default=code == "cynic", **values)
    )
    return identifier


def _state(connection, users, states, personality_id, **overrides):
    user_id, state_id = uuid4(), uuid4()
    connection.execute(users.insert().values(id=user_id, personality_id=personality_id))
    connection.execute(
        states.insert().values(
            id=state_id,
            user_id=user_id,
            **dict.fromkeys(TRAITS, 0.5),
            mood_pleasure=-0.17,
            relationship_trust=0.83,
            self_efficacy={"technical": {"score": 0.91, "weight": 8}},
            active_emotions=[{"name": "joy", "intensity": 0.4}],
        )
    )
    if overrides:
        connection.execute(states.update().where(states.c.id == state_id).values(**overrides))
    return state_id


def _snapshot(connection, table):
    return [
        dict(row) for row in connection.execute(sa.select(table).order_by(table.c.id)).mappings()
    ]


def _seed_rows():
    """Execute the actual first INSERT, including its quoted multiline prompts."""
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.connection.driver_connection.create_function("NOW", 0, lambda: "2026-10-16")
            columns = "id TEXT,code TEXT,emoji TEXT,is_default BOOLEAN,is_active BOOLEAN,sort_order INT,prompt_instruction TEXT,created_at TEXT,updated_at TEXT,"
            columns += ",".join(f"{name} FLOAT" for name in (*TRAITS, *PADS))
            connection.exec_driver_sql(f"CREATE TABLE personalities ({columns})")
            insert = (
                SEED.read_text(encoding="utf-8")
                .split("INSERT INTO personalities (", 1)[1]
                .split("-- TRANSLATIONS", 1)[0]
            )
            insert = "INSERT INTO personalities (" + insert[: insert.rfind(";") + 1]
            connection.exec_driver_sql(insert)
            return {
                row["code"]: dict(row)
                for row in connection.exec_driver_sql("SELECT * FROM personalities").mappings()
            }
    finally:
        engine.dispose()


@pytest.mark.parametrize("code", CODES)
def test_fresh_seed_retains_last_published_traits_and_pad_values(code):
    row = _seed_rows()[code]
    identifier, expected = CANONICAL[code]
    assert UUID(row["id"]) == (CURRENT_ANTAGONIST_ID if code == "antagonist" else identifier)
    assert tuple(row[name] for name in (*TRAITS, *PADS)) == expected


def test_upgrade_restores_lost_profiles_and_only_neutral_matching_states(database, monkeypatch):
    connection, profiles, users, states = database
    cynic = _profile(connection, profiles)
    enthusiastic = _profile(connection, profiles, "enthusiastic")
    explicit = _state(connection, users, states, enthusiastic)
    default = _state(connection, users, states, None)
    dangling = _state(connection, users, states, uuid4())
    changed = _state(connection, users, states, cynic, trait_agreeableness=0.4)
    before = {row["id"]: row for row in _snapshot(connection, states)}
    _repair(connection, monkeypatch)
    after = {row["id"]: row for row in _snapshot(connection, states)}
    for identifier, code in [(explicit, "enthusiastic"), (default, "cynic"), (dangling, "cynic")]:
        assert tuple(after[identifier][name] for name in TRAITS) == CANONICAL[code][1][:5]
        assert {key: value for key, value in after[identifier].items() if key not in TRAITS} == {
            key: value for key, value in before[identifier].items() if key not in TRAITS
        }
    assert after[changed] == before[changed]
    profiles_after = _snapshot(connection, profiles)
    changes = connection.connection.driver_connection.total_changes
    _repair(connection, monkeypatch)
    assert connection.connection.driver_connection.total_changes == changes
    assert _snapshot(connection, profiles) == profiles_after
    assert _snapshot(connection, states) == sorted(after.values(), key=lambda row: row["id"])


@pytest.mark.parametrize("configured", (*TRAITS, *PADS))
def test_upgrade_preserves_any_partial_admin_configuration(database, monkeypatch, configured):
    connection, profiles, users, states = database
    identifier = _profile(connection, profiles, **{configured: 0.0})
    _state(connection, users, states, identifier)
    before = (_snapshot(connection, profiles), _snapshot(connection, states))
    _repair(connection, monkeypatch)
    assert (_snapshot(connection, profiles), _snapshot(connection, states)) == before


def test_upgrade_requires_stock_uuid_and_code_and_preserves_custom_rows(database, monkeypatch):
    connection, profiles, users, states = database
    stock_id, other_id = CANONICAL["cynic"][0], uuid4()
    connection.execute(
        profiles.insert(),
        [
            {"id": stock_id, "code": "custom", "is_default": True},
            {"id": other_id, "code": "cynic", "is_default": False},
        ],
    )
    _state(connection, users, states, stock_id)
    _state(connection, users, states, other_id)
    before = (_snapshot(connection, profiles), _snapshot(connection, states))
    _repair(connection, monkeypatch)
    assert (_snapshot(connection, profiles), _snapshot(connection, states)) == before


def test_upgrade_does_not_rewrite_state_for_an_already_configured_stock_profile(
    database, monkeypatch
):
    connection, profiles, users, states = database
    cynic = _profile(
        connection, profiles, **dict(zip((*TRAITS, *PADS), CANONICAL["cynic"][1], strict=True))
    )
    _state(connection, users, states, cynic)
    before = _snapshot(connection, states)
    _repair(connection, monkeypatch)
    assert _snapshot(connection, states) == before


def test_upgrade_limits_state_alignment_to_profiles_repaired_in_this_execution(
    database, monkeypatch
):
    connection, profiles, users, states = database
    _profile(connection, profiles, **dict.fromkeys(TRAITS, 0.8))
    enthusiastic = _profile(connection, profiles, "enthusiastic")
    preserved = _state(connection, users, states, None)
    repaired = _state(connection, users, states, enthusiastic)
    before = {row["id"]: row for row in _snapshot(connection, states)}
    _repair(connection, monkeypatch)
    after = {row["id"]: row for row in _snapshot(connection, states)}
    assert after[preserved] == before[preserved]
    assert tuple(after[repaired][name] for name in TRAITS) == CANONICAL["enthusiastic"][1][:5]


@pytest.mark.parametrize("identifier", [CANONICAL["antagonist"][0], CURRENT_ANTAGONIST_ID])
def test_upgrade_handles_both_published_antagonist_stock_identities(
    database, monkeypatch, identifier
):
    connection, profiles, users, states = database
    connection.execute(profiles.insert().values(id=identifier, code="antagonist", is_default=False))
    _state(connection, users, states, identifier)
    _repair(connection, monkeypatch)
    profile = _snapshot(connection, profiles)[0]
    assert tuple(profile[name] for name in (*TRAITS, *PADS)) == CANONICAL["antagonist"][1]
    assert (
        tuple(_snapshot(connection, states)[0][name] for name in TRAITS)
        == CANONICAL["antagonist"][1][:5]
    )


@pytest.mark.parametrize(
    "column,value",
    [
        (TRAITS[0], None),
        (TRAITS[2], -0.1),
        (TRAITS[4], 1.1),
        (PADS[0], -1.1),
        (PADS[1], 1.1),
        ("code", "unknown"),
    ],
)
def test_seed_verifier_rejects_missing_invalid_or_unnamed_profiles(column, value):
    body = VERIFY.read_text(encoding="utf-8")
    match = re.search(r"-- OCEAN/PAD profiles(?P<query>.*?)IF c <> 14 THEN", body, re.S)
    assert match is not None, "seed verification must validate the named OCEAN profiles"
    query = match.group("query").strip().replace(" INTO c", "").rstrip(";")
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            columns = "code TEXT," + ",".join(f"{name} FLOAT" for name in (*TRAITS, *PADS))
            connection.exec_driver_sql(f"CREATE TABLE personalities ({columns})")
            for code, (_, values) in CANONICAL.items():
                record = dict(zip(("code", *TRAITS, *PADS), (code, *values), strict=True))
                connection.execute(
                    sa.text(
                        "INSERT INTO personalities ("
                        + ",".join(record)
                        + ") VALUES ("
                        + ",".join(":" + name for name in record)
                        + ")"
                    ),
                    record,
                )
            assert connection.exec_driver_sql(query).scalar_one() == 14
            connection.execute(
                sa.text(f"UPDATE personalities SET {column}=:value WHERE code='cynic'"),
                {"value": value},
            )
            assert connection.exec_driver_sql(query).scalar_one() == 13
    finally:
        engine.dispose()


def test_repair_chains_after_current_catalogue_revision_and_keeps_published_values():
    module = _load(REPAIR)
    assert module.revision == "b62a8d193f04"
    assert module.down_revision == "7f428c3e0a19"
    assert {code: tuple(values) for _, code, *values in module.PERSONALITY_PROFILES} == {
        code: values for code, (_, values) in CANONICAL.items()
    }
    assert len(module.PERSONALITY_PROFILES) == 14
    assert len(module.LEGACY_PROFILES) == 1
    for identifier, code, *_values in module.PERSONALITY_PROFILES:
        expected_id = CURRENT_ANTAGONIST_ID if code == "antagonist" else CANONICAL[code][0]
        assert UUID(identifier) == expected_id
    assert module.LEGACY_PROFILES[0][0] == str(CANONICAL["antagonist"][0])
