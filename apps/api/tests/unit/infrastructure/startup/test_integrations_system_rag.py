"""The startup FAQ indexation step: never blocking, never misfiled.

This lifespan step had no tests at all, and two of its properties had gone wrong
in production without anyone seeing it.

**The failure was filed under the wrong subsystem.** The indexer's exception was
allowed to escape the ``get_db_context`` block, so the context manager logged
``database_session_error`` at ERROR with a full traceback under
``src.infrastructure.database.session``. Over 14 days, 69 embedding-quota
rejections were recorded as database errors — anyone triaging them started in the
wrong layer. Catching inside the session turns that into one ERROR from the
domain plus one WARNING here.

**A boot must never be held up by it.** The system FAQ is optional. Both the
indexer failing and the session itself failing to open must degrade to a warning,
which is what the outer guard is for — and it is easy to lose while refactoring
the inner one.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.startup import integrations as integrations_module


@pytest.fixture
def captured_logs(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    """Capture the step's log calls by level.

    Args:
        monkeypatch: pytest monkeypatch fixture.

    Returns:
        Mapping of level name to ``(event, fields)`` pairs.
    """
    captured: dict[str, list[tuple[str, dict[str, Any]]]] = {
        "info": [],
        "warning": [],
        "error": [],
    }

    def _recorder(level: str) -> Any:
        def _log(event: str, **fields: Any) -> None:
            captured[level].append((event, fields))

        return _log

    for level in captured:
        monkeypatch.setattr(integrations_module.logger, level, _recorder(level))
    return captured


def _install_session(monkeypatch: pytest.MonkeyPatch, session: Any) -> list[str]:
    """Make the step use ``session``, recording how the context is left.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        session: Session double to yield.

    Returns:
        A list receiving "exited_cleanly" when the context manager saw no
        exception, which is the property that keeps ``database_session_error``
        out of the logs.
    """
    lifecycle: list[str] = []

    class _Context:
        async def __aenter__(self) -> Any:
            return session

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            lifecycle.append("exited_with_exception" if exc_type else "exited_cleanly")
            return False

    import src.infrastructure.database.session as session_module

    monkeypatch.setattr(session_module, "get_db_context", lambda: _Context())
    return lifecycle


def _install_indexer(monkeypatch: pytest.MonkeyPatch, indexer: Any) -> None:
    """Make the step build ``indexer``.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        indexer: Indexer double.
    """
    import src.domains.rag_spaces.system_indexer as indexer_module

    monkeypatch.setattr(indexer_module, "SystemSpaceIndexer", lambda _db: indexer)


@pytest.fixture(autouse=True)
def enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn the feature on for every test in this module.

    Args:
        monkeypatch: pytest monkeypatch fixture.
    """
    monkeypatch.setattr(
        integrations_module.settings, "rag_spaces_system_enabled", True, raising=False
    )


@pytest.mark.unit
class TestOutcomeReporting:
    """Each outcome gets exactly one line, at the right level."""

    async def test_success_reports_the_chunk_count(
        self, monkeypatch: pytest.MonkeyPatch, captured_logs: dict[str, list[Any]]
    ) -> None:
        """A successful indexation says how much it wrote, and warns about nothing.

        Args:
            monkeypatch: pytest monkeypatch fixture.
            captured_logs: Captured log calls.
        """
        _install_session(monkeypatch, AsyncMock())
        _install_indexer(
            monkeypatch,
            SimpleNamespace(
                index_faq_space=AsyncMock(return_value={"status": "success", "chunks_created": 269})
            ),
        )

        await integrations_module.index_system_rag_spaces()

        assert captured_logs["info"] == [("system_rag_startup_indexed", {"chunks_created": 269})]
        assert captured_logs["warning"] == []

    async def test_skip_carries_its_reason(
        self, monkeypatch: pytest.MonkeyPatch, captured_logs: dict[str, list[Any]]
    ) -> None:
        """ "Skipped" alone cannot distinguish a no-op boot from a lost claim.

        Args:
            monkeypatch: pytest monkeypatch fixture.
            captured_logs: Captured log calls.
        """
        _install_session(monkeypatch, AsyncMock())
        _install_indexer(
            monkeypatch,
            SimpleNamespace(
                index_faq_space=AsyncMock(
                    return_value={"status": "skipped", "reason": "claimed_by_another_worker"}
                )
            ),
        )

        await integrations_module.index_system_rag_spaces()

        assert captured_logs["info"] == [
            ("system_rag_startup_skipped", {"reason": "claimed_by_another_worker"})
        ]

    async def test_error_status_is_a_warning(
        self, monkeypatch: pytest.MonkeyPatch, captured_logs: dict[str, list[Any]]
    ) -> None:
        """A returned error status is reported without being raised.

        Args:
            monkeypatch: pytest monkeypatch fixture.
            captured_logs: Captured log calls.
        """
        _install_session(monkeypatch, AsyncMock())
        _install_indexer(
            monkeypatch,
            SimpleNamespace(
                index_faq_space=AsyncMock(
                    return_value={"status": "error", "error": "Knowledge directory not found"}
                )
            ),
        )

        await integrations_module.index_system_rag_spaces()

        assert captured_logs["warning"] == [
            ("system_rag_startup_error", {"error": "Knowledge directory not found"})
        ]


@pytest.mark.unit
class TestFailureIsNotMisfiled:
    """The session context must never see the indexer's exception."""

    async def test_the_session_exits_cleanly_after_a_failure(
        self, monkeypatch: pytest.MonkeyPatch, captured_logs: dict[str, list[Any]]
    ) -> None:
        """This is what stops ``database_session_error`` from being logged.

        Args:
            monkeypatch: pytest monkeypatch fixture.
            captured_logs: Captured log calls.
        """
        session = AsyncMock()
        lifecycle = _install_session(monkeypatch, session)
        _install_indexer(
            monkeypatch,
            SimpleNamespace(index_faq_space=AsyncMock(side_effect=RuntimeError("429 quota"))),
        )

        await integrations_module.index_system_rag_spaces()

        assert lifecycle == ["exited_cleanly"]
        session.rollback.assert_awaited_once()

    async def test_the_warning_names_the_exception_type(
        self, monkeypatch: pytest.MonkeyPatch, captured_logs: dict[str, list[Any]]
    ) -> None:
        """A message alone does not say which failure class it was.

        Args:
            monkeypatch: pytest monkeypatch fixture.
            captured_logs: Captured log calls.
        """
        _install_session(monkeypatch, AsyncMock())
        _install_indexer(
            monkeypatch,
            SimpleNamespace(index_faq_space=AsyncMock(side_effect=RuntimeError("429 quota"))),
        )

        await integrations_module.index_system_rag_spaces()

        assert len(captured_logs["warning"]) == 1
        event, fields = captured_logs["warning"][0]
        assert event == "system_rag_startup_failed"
        assert fields == {"error": "429 quota", "error_type": "RuntimeError"}


@pytest.mark.unit
class TestBootIsNeverBlocked:
    """No failure in this step may propagate into the lifespan."""

    async def test_an_indexer_failure_does_not_propagate(
        self, monkeypatch: pytest.MonkeyPatch, captured_logs: dict[str, list[Any]]
    ) -> None:
        """The optional FAQ must not be able to abort a boot.

        Args:
            monkeypatch: pytest monkeypatch fixture.
            captured_logs: Captured log calls.
        """
        _install_session(monkeypatch, AsyncMock())
        _install_indexer(
            monkeypatch,
            SimpleNamespace(index_faq_space=AsyncMock(side_effect=RuntimeError("boom"))),
        )

        await integrations_module.index_system_rag_spaces()  # must not raise

    async def test_a_session_that_cannot_open_does_not_propagate(
        self, monkeypatch: pytest.MonkeyPatch, captured_logs: dict[str, list[Any]]
    ) -> None:
        """The outer guard, which the inner refactor could easily have removed.

        Args:
            monkeypatch: pytest monkeypatch fixture.
            captured_logs: Captured log calls.
        """
        import src.infrastructure.database.session as session_module

        class _FailingContext:
            async def __aenter__(self) -> Any:
                raise ConnectionError("could not connect to postgres")

            async def __aexit__(self, *_: Any) -> bool:
                return False

        monkeypatch.setattr(session_module, "get_db_context", lambda: _FailingContext())

        await integrations_module.index_system_rag_spaces()  # must not raise

        assert captured_logs["warning"] == [
            (
                "system_rag_startup_failed",
                {"error": "could not connect to postgres", "error_type": "ConnectionError"},
            )
        ]

    async def test_a_rollback_that_fails_does_not_propagate(
        self, monkeypatch: pytest.MonkeyPatch, captured_logs: dict[str, list[Any]]
    ) -> None:
        """A dead connection makes even the cleanup raise.

        Args:
            monkeypatch: pytest monkeypatch fixture.
            captured_logs: Captured log calls.
        """
        session = AsyncMock()
        session.rollback = AsyncMock(side_effect=ConnectionError("connection is closed"))
        _install_session(monkeypatch, session)
        _install_indexer(
            monkeypatch,
            SimpleNamespace(index_faq_space=AsyncMock(side_effect=RuntimeError("boom"))),
        )

        await integrations_module.index_system_rag_spaces()  # must not raise

        assert captured_logs["warning"][-1][0] == "system_rag_startup_failed"


@pytest.mark.unit
class TestFeatureFlag:
    """Disabled means nothing happens at all."""

    async def test_disabled_does_not_touch_the_database(
        self, monkeypatch: pytest.MonkeyPatch, captured_logs: dict[str, list[Any]]
    ) -> None:
        """With the feature off, not even a session is opened.

        Args:
            monkeypatch: pytest monkeypatch fixture.
            captured_logs: Captured log calls.
        """
        monkeypatch.setattr(
            integrations_module.settings, "rag_spaces_system_enabled", False, raising=False
        )
        sentinel = MagicMock(side_effect=AssertionError("the session must not be opened"))
        import src.infrastructure.database.session as session_module

        monkeypatch.setattr(session_module, "get_db_context", sentinel)

        await integrations_module.index_system_rag_spaces()

        assert captured_logs == {"info": [], "warning": [], "error": []}
