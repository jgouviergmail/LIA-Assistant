"""Contract: shared psycopg (libpq) configuration for the LangGraph pools.

The checkpointer and Store pools historically duplicated their conninfo
resolution (``settings.database_url`` → psycopg form) and connection kwargs,
and neither passed ``connect_timeout`` — connection establishment was left to
kernel TCP behavior (audit follow-up of the AC-010 SQLAlchemy fix, which
bounded the SQLAlchemy engines but not the psycopg pools).

These tests pin the shared helper: URL resolution from settings, an explicit
test-only override (reliable injection for the pools, independent of the
settings object), and pool kwargs that always carry ``connect_timeout``.

They all take ``psycopg_url_from_settings``, which SAVES and RESTORES the
process-wide override around each test. Restoring matters as much as clearing:
these tests used to end on ``set_psycopg_url_override(None)``, which does not
undo the override — it destroys it, pointing every later DB-backed test in the
same xdist worker at the developer database instead of the container.
(The frozen-run incident at ``checkpointer_initializing`` had a different
cause — the CREATE INDEX CONCURRENTLY deadlock, fixed by
``tests/conftest.py::_provision_langgraph_tables`` and pinned by its own
regression contract.)
"""

from __future__ import annotations

from psycopg.rows import dict_row

from src.core.config import settings
from src.infrastructure.database.psycopg_pool_config import (
    psycopg_pool_kwargs,
    resolve_psycopg_url,
    set_psycopg_url_override,
)


class TestResolvePsycopgUrl:
    def test_resolves_from_settings_in_psycopg_form(self, psycopg_url_from_settings: None) -> None:
        url = resolve_psycopg_url()
        assert url.startswith("postgresql://")
        assert "+asyncpg" not in url
        assert url == str(settings.database_url).replace("postgresql+asyncpg://", "postgresql://")

    def test_explicit_override_wins_over_settings(self, psycopg_url_from_settings: None) -> None:
        set_psycopg_url_override("postgresql://u:p@127.0.0.1:45999/injected")
        assert resolve_psycopg_url() == "postgresql://u:p@127.0.0.1:45999/injected"

    def test_clearing_override_restores_settings_resolution(
        self, psycopg_url_from_settings: None
    ) -> None:
        set_psycopg_url_override("postgresql://u:p@127.0.0.1:45999/injected")
        set_psycopg_url_override(None)
        assert resolve_psycopg_url() == str(settings.database_url).replace(
            "postgresql+asyncpg://", "postgresql://"
        )


class TestPsycopgPoolKwargs:
    def test_carries_saver_required_kwargs(self) -> None:
        """Parity with upstream AsyncPostgresSaver.from_conn_string requirements."""
        kwargs = psycopg_pool_kwargs()
        assert kwargs["autocommit"] is True
        assert kwargs["prepare_threshold"] == 0
        assert kwargs["row_factory"] is dict_row

    def test_carries_connect_timeout_from_settings(self) -> None:
        """connect_timeout bounds the establishment of each pool connection.

        Read from settings, never hardcoded: the test environment shortens it
        via .env.test, production keeps the default.
        """
        kwargs = psycopg_pool_kwargs()
        assert kwargs["connect_timeout"] == settings.database_connect_timeout

    def test_returns_a_fresh_dict_per_call(self) -> None:
        """Callers must not share (and accidentally mutate) one dict."""
        assert psycopg_pool_kwargs() is not psycopg_pool_kwargs()
