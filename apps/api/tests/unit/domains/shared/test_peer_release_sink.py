"""A connection that ends hands back what it was holding (ADR-276, lot 5).

`workboard` imports `peers` (the service re-checks the connection at every
write), so `peers` importing `workboard` back would close a cycle — and the
coupling ratchet counts LOCAL imports, so hiding it inside a function would only
make the edge harder to see. The dependency is inverted through this seam, the
same shape the consultation register and the notification dispatcher already
use.

Two properties are pinned here, and each is a silence this seam exists to end:
with nothing installed the call answers « nothing was released » instead of
raising (a probe or a narrow test has no board open), and the boot REFUSES a
mute seam — ADR-270 measured what an undeclared import side effect costs.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from src.domains.shared import peer_release_sink
from src.domains.shared.peer_release_sink import (
    install_ticket_releaser,
    release_tickets_between,
    releaser_is_installed,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _restore_seam() -> Any:
    """Put the seam back exactly as it was: it is process-global state."""
    previous = peer_release_sink._releaser
    yield
    peer_release_sink._releaser = previous


class TestWithNothingInstalled:
    async def test_it_answers_that_nothing_moved(self) -> None:
        """A script, a probe or a narrow unit test has no board open; raising
        there would turn a bookkeeping concern into an outage."""
        peer_release_sink._releaser = peer_release_sink._ignore

        assert (
            await release_tickets_between(db=object(), user_a=uuid.uuid4(), user_b=uuid.uuid4())
            == {}
        )
        assert releaser_is_installed() is False


class TestOnceInstalled:
    async def test_every_field_reaches_the_board_by_name(self) -> None:
        """A seam taking ``**Any`` would let a caller misspell one and release
        nothing, in silence."""
        seen: dict[str, Any] = {}

        async def releaser(
            *, db: Any, user_a: uuid.UUID, user_b: uuid.UUID
        ) -> dict[uuid.UUID, int]:
            seen.update({"db": db, "user_a": user_a, "user_b": user_b})
            return {user_a: 2}

        install_ticket_releaser(releaser)
        owner, peer = uuid.uuid4(), uuid.uuid4()
        db = object()

        counts = await release_tickets_between(db=db, user_a=owner, user_b=peer)

        assert seen == {"db": db, "user_a": owner, "user_b": peer}
        assert counts == {owner: 2}
        assert releaser_is_installed() is True

    async def test_a_board_that_raises_never_costs_the_severance(self) -> None:
        """The connection is already gone in the same transaction: a bookkeeping
        failure must not roll it back, and the caller learns « nothing moved »
        rather than an exception it would have to catch."""

        async def broken(**_kwargs: Any) -> dict[uuid.UUID, int]:
            raise RuntimeError("the board is unavailable")

        install_ticket_releaser(broken)

        assert (
            await release_tickets_between(db=object(), user_a=uuid.uuid4(), user_b=uuid.uuid4())
            == {}
        )


class TestTheBootRefusesAMuteSeam:
    def test_importing_the_adapter_is_what_installs_it(self) -> None:
        # RELOAD, not import: another test in the session has almost certainly
        # imported the adapter already, and a cached import runs no module body
        # — so a plain import would prove nothing about the wiring.
        import importlib

        module = importlib.import_module("src.domains.workboard.release_adapter")
        peer_release_sink._releaser = peer_release_sink._ignore
        importlib.reload(module)

        assert releaser_is_installed() is True

    def test_the_boot_calls_the_step(self) -> None:
        """An import side effect nobody declares is an import that stops
        happening the day someone reorders a module (ADR-270)."""
        from pathlib import Path

        source = Path("src/infrastructure/startup/registries.py").read_text(encoding="utf-8")
        assert "_install_ticket_releaser" in source

    def test_it_refuses_to_boot_on_a_seam_nobody_claimed(self) -> None:
        from unittest.mock import patch

        from src.infrastructure.startup.registries import _install_ticket_releaser

        with patch(
            "src.domains.shared.peer_release_sink.releaser_is_installed", return_value=False
        ):
            with pytest.raises(RuntimeError, match="release"):
                _install_ticket_releaser()
