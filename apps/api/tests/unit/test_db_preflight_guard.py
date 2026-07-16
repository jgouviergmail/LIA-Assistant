"""A promised database that is unavailable fails the job, it does not skip (F019).

The CI integration/migration jobs provision PostgreSQL and export
``LIA_REQUIRE_DB=1``. In that context an unreachable DB or a Testcontainers error
is a real infrastructure failure and must fail loudly; silently skipping whole
DB-backed test groups turns an outage into invisible zero coverage. Locally
(no promise) it must still degrade to a readable skip.
"""

from __future__ import annotations

import pytest

from tests.conftest import _db_unavailable


def test_fails_when_a_database_is_promised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIA_REQUIRE_DB", "1")
    with pytest.raises(pytest.fail.Exception):
        _db_unavailable("simulated Testcontainers/Docker outage")


def test_skips_when_no_database_is_promised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIA_REQUIRE_DB", raising=False)
    with pytest.raises(pytest.skip.Exception):
        _db_unavailable("no local test database")
