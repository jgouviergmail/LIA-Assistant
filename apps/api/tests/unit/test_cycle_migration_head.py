"""Real disposable Alembic graphs exercise explicit linear and merge rollback targets."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit
HELPER = repo_root_or_skip() / "scripts" / "db" / "cycle_migration_head.py"


def load_helper():
    spec = importlib.util.spec_from_file_location("cycle_migration_head", HELPER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def graph(tmp_path: Path, kind: str) -> Config:
    scripts = tmp_path / "alembic"
    versions = scripts / "versions"
    versions.mkdir(parents=True)
    (scripts / "env.py").write_text(
        "from alembic import context\n"
        "from sqlalchemy import create_engine\n"
        "engine = create_engine(context.config.get_main_option('sqlalchemy.url'))\n"
        "with engine.connect() as connection:\n"
        "    context.configure(connection=connection)\n"
        "    with context.begin_transaction():\n"
        "        context.run_migrations()\n"
        "engine.dispose()\n",
        encoding="utf-8",
    )
    revisions = [] if kind == "empty" else [("start_1", None, "probe")]
    if kind in {"linear", "merge", "multiple"}:
        revisions.append(("left_2", "start_1", "left_table"))
    if kind in {"merge", "multiple"}:
        revisions.append(("right_3", "start_1", "right_table"))
    if kind == "merge":
        revisions.append(("join_4", ("right_3", "left_2"), None))
    for revision, parent, table in revisions:
        upgrade = (
            f"op.create_table({table!r}, sa.Column('id', sa.Integer, primary_key=True))"
            if table
            else "pass"
        )
        downgrade = f"op.drop_table({table!r})" if table else "pass"
        (versions / f"{revision}.py").write_text(
            "from alembic import op\nimport sqlalchemy as sa\n"
            f"revision = {revision!r}\ndown_revision = {parent!r}\n"
            "branch_labels = None\ndepends_on = None\n"
            f"def upgrade():\n    {upgrade}\n"
            f"def downgrade():\n    {downgrade}\n",
            encoding="utf-8",
        )
    config = Config()
    config.set_main_option("script_location", str(scripts))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_path / 'replay.sqlite'}")
    return config


@pytest.mark.parametrize(
    ("kind", "head", "targets", "tables"),
    [
        ("root", "start_1", ["base"], {"probe"}),
        ("linear", "left_2", ["start_1"], {"probe", "left_table"}),
        (
            "merge",
            "join_4",
            ["left_2", "right_3"],
            {"probe", "left_table", "right_table"},
        ),
    ],
)
def test_cycles_every_explicit_parent_and_returns_to_the_single_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    head: str,
    targets: list[str],
    tables: set[str],
) -> None:
    helper = load_helper()
    config = graph(tmp_path, kind)
    command.upgrade(config, "head")
    engine = create_engine(config.get_main_option("sqlalchemy.url"))
    if kind != "root":
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO probe (id) VALUES (42)"))
    seen = []
    messages = []
    downgrade = command.downgrade

    def observe(config, target):
        seen.append(target)
        downgrade(config, target)

    monkeypatch.setattr(helper.command, "downgrade", observe)
    helper.cycle_head(config, emit=messages.append)
    assert seen == targets
    assert all(any(target in message for message in messages) for target in targets)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalars().all() == [head]
        assert set(inspect(connection).get_table_names()) == tables | {"alembic_version"}
        if kind != "root":
            assert connection.execute(text("SELECT id FROM probe")).scalars().all() == [42]
    engine.dispose()


@pytest.mark.parametrize("kind", ["empty", "multiple"])
def test_ambiguous_or_missing_heads_fail_before_any_database_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    helper = load_helper()
    config = graph(tmp_path, kind)

    def forbidden(*args, **kwargs):
        pytest.fail("invalid graph must not reach a database operation")

    monkeypatch.setattr(helper.command, "downgrade", forbidden)
    monkeypatch.setattr(helper.command, "upgrade", forbidden)
    with pytest.raises(RuntimeError, match="single Alembic head"):
        helper.cycle_head(config)
    assert not (tmp_path / "replay.sqlite").exists()
