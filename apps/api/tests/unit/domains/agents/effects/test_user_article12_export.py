"""The unified extraction, for the account holder's own activity (ADR-263).

Article 12 asks for one machine-readable record of what the system did. The
administrator has had it since lot 9; the person the records are ABOUT had
only the per-register exports, so assembling their own file meant downloading
five documents and correlating them by hand — which is exactly the work the
unified extraction exists to remove.

Two properties this file exists for, and neither is provable from the handler:

- the route takes **no account parameter at all**, so there is nothing to
  tamper with — the scope is the session, as it is for every other reader
  surface (`/effects/statistics`, `/effects/export`);
- the file it produces obeys the **same contract** as the administrator's, not
  a user variant: same columns, same exclusions, same pseudonymisation. A
  second contract for the same rows would be a second place for a column to
  slip from « forbidden » to « exported ».
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.effects.export_router import rate_limit_export, router

pytestmark = [pytest.mark.unit]


READER = uuid.uuid4()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_active_session] = lambda: SimpleNamespace(
        id=READER, is_superuser=False, language="fr", display_timezone="Europe/Paris"
    )
    app.dependency_overrides[get_db] = lambda: SimpleNamespace()
    # Overridden through FastAPI, not patched: the limiter is bound into the
    # route's `dependencies` at decoration time, so patching the module
    # attribute leaves the real one running — it reached for Redis, retried
    # five times and failed open, which made the suite slow and its green
    # meaningless about the limiter.
    app.dependency_overrides[rate_limit_export] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


def _served(rows: dict[str, list[Any]] | None = None) -> Any:
    """Stub the register reads, capturing the scope each one was asked for."""
    seen: list[Any] = []

    async def _read(db: Any, asked: Any, cap: int) -> list[Any]:
        seen.append(asked)
        return (rows or {}).get(asked.register, [])

    patcher = patch("src.domains.agents.effects.export_router.read_register", side_effect=_read)
    patcher.seen = seen  # type: ignore[attr-defined]
    return patcher


def _lines(body: str) -> list[dict[str, Any]]:
    return [json.loads(one) for one in body.strip().split("\n")]


class TestTheReaderCanExtractTheirOwnRecord:
    def test_the_route_is_served(self) -> None:
        with (
            _served(),
            patch("src.domains.agents.effects.export_router.rate_limit_export", return_value=None),
        ):
            response = _client().get("/api/v1/effects/export/article12")

        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("application/x-ndjson")
        assert "article12" in response.headers["content-disposition"]

    def test_every_source_is_read_for_the_CALLER_only(self) -> None:
        # The scope is the session. Not a default that a parameter could
        # override — a scope there is no way to express.
        patcher = _served()
        with (
            patcher,
            patch("src.domains.agents.effects.export_router.rate_limit_export", return_value=None),
        ):
            _client().get("/api/v1/effects/export/article12")

        scopes = {tuple(asked.user_ids or []) for asked in patcher.seen}  # type: ignore[attr-defined]
        assert scopes == {(READER,)}

    def test_the_route_takes_no_account_parameter(self) -> None:
        import inspect

        from src.domains.agents.effects.export_router import export_article12

        parameters = set(inspect.signature(export_article12).parameters)
        assert "user_ids" not in parameters
        assert "user_id" not in parameters

    def test_naming_an_account_in_the_query_changes_nothing(self) -> None:
        # FastAPI ignores an undeclared query parameter; this pins that the
        # route does not grow one by accident.
        patcher = _served()
        with (
            patcher,
            patch("src.domains.agents.effects.export_router.rate_limit_export", return_value=None),
        ):
            response = _client().get(f"/api/v1/effects/export/article12?user_ids={uuid.uuid4()}")

        assert response.status_code == 200
        scopes = {tuple(asked.user_ids or []) for asked in patcher.seen}  # type: ignore[attr-defined]
        assert scopes == {(READER,)}

    def test_the_file_covers_the_five_records_and_names_each_line(self) -> None:
        with (
            _served(),
            patch("src.domains.agents.effects.export_router.rate_limit_export", return_value=None),
        ):
            body = _client().get("/api/v1/effects/export/article12").text

        header = _lines(body)[0]
        assert header["lia_record"] == "lia.article12"
        assert set(header["sources"]) == {
            "actions",
            "consultations",
            "decisions",
            "inference",
            "integrity",
        }

    def test_the_header_states_the_same_pseudonymisation_promise(self) -> None:
        # Same contract as the administrator's file, not a user variant.
        with (
            _served(),
            patch("src.domains.agents.effects.export_router.rate_limit_export", return_value=None),
        ):
            header = _lines(_client().get("/api/v1/effects/export/article12").text)[0]

        assert header["pseudonymised"] is True
        assert "HMAC" in header["identifiers"]
        assert header["filters"]["user_ids"] is not None

    def test_the_readers_own_id_is_pseudonymised_in_the_header(self) -> None:
        # Their own file still names them by handle: it is what makes the file
        # safe to hand to a third party without editing it first.
        with (
            _served(),
            patch("src.domains.agents.effects.export_router.rate_limit_export", return_value=None),
        ):
            header = _lines(_client().get("/api/v1/effects/export/article12").text)[0]

        assert str(READER) not in json.dumps(header)


class TestTheTwoSurfacesShareOneImplementation:
    """The extraction already existed for administrators.

    What the reader's route adds is a SCOPE, not a second extraction — so the
    composition, the header and the reads must have exactly one implementation
    each. Two copies would drift the day a sixth record joins, and the drift
    would show up as one audience seeing a record the other does not.
    """

    def test_both_routes_compose_with_the_same_renderer(self) -> None:
        import inspect

        from src.domains.agents.effects import admin_router, export_router

        for module in (admin_router, export_router):
            source = inspect.getsource(module)
            assert "render_article12(" in source
            assert "known_sources()" in source
            assert "extract_of(" in source

    def test_neither_route_reimplements_the_reads(self) -> None:
        import inspect

        from src.domains.agents.effects import admin_router, export_router
        from src.domains.agents.effects.technical_reads import read_register

        for module in (admin_router, export_router):
            assert "read_register(" in inspect.getsource(module)
            # The dispatch lives in one place: a route that grew its own
            # `if register ==` branch would be a second authority on which
            # table answers for which record.
            assert "if asked.register ==" not in inspect.getsource(module)

        assert 'asked.register == "actions"' in inspect.getsource(read_register)

    def test_the_two_routes_differ_only_in_scope(self) -> None:
        import inspect

        from src.domains.agents.effects.admin_router import export_article12 as admin_route
        from src.domains.agents.effects.export_router import export_article12 as reader_route

        admin_parameters = set(inspect.signature(admin_route).parameters)
        reader_parameters = set(inspect.signature(reader_route).parameters)

        # The operator names accounts; the reader has one and cannot say so.
        assert "user_ids" in admin_parameters
        assert admin_parameters - reader_parameters == {"user_ids", "current_user"}
        assert reader_parameters - admin_parameters == {"user"}
