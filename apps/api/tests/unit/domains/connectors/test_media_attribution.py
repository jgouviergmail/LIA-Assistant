"""A proxy fetch is filed on the turn that built its URL — when it can prove it.

The URL carries the run id SIGNED over (run id, account) with the instance
secret. Without the signature any signed-in caller could file a fetch under
another account's run and, before that turn's summary row exists, create the
row under their own ``user_id``.
"""

from __future__ import annotations

import uuid

import pytest

from src.core.context import current_tracker
from src.domains.chat.service import TrackingContext
from src.domains.connectors.media_attribution import (
    RUN_PARAM,
    SIG_PARAM,
    attributed_run_id,
    media_spend_context,
    with_attribution,
)

pytestmark = pytest.mark.unit


def _params(url: str) -> dict[str, str]:
    query = url.split("?", 1)[1]
    return dict(part.split("=", 1) for part in query.split("&"))


class TestBuildingTheUrl:
    def test_outside_a_tracker_the_url_is_untouched(self) -> None:
        token = current_tracker.set(None)
        try:
            assert with_attribution("/api/v1/x/photo/abc") == "/api/v1/x/photo/abc"
        finally:
            current_tracker.reset(token)

    async def test_inside_a_tracker_the_url_carries_a_signed_run(self) -> None:
        user_id = uuid.uuid4()
        async with TrackingContext("run-1", user_id, "s", None):
            bare = with_attribution("/api/v1/x/photo/abc")
            queried = with_attribution("/api/v1/x/map?lat=1&lng=2")
        assert bare.startswith("/api/v1/x/photo/abc?")
        assert queried.startswith("/api/v1/x/map?lat=1&lng=2&")
        params = _params(bare)
        assert params[RUN_PARAM] == "run-1"
        assert attributed_run_id(params[RUN_PARAM], params[SIG_PARAM], user_id) == "run-1"

    async def test_a_run_id_with_reserved_characters_survives_the_round_trip(self) -> None:
        user_id = uuid.uuid4()
        from urllib.parse import unquote

        async with TrackingContext("phone_call_ab&cd", user_id, "s", None):
            url = with_attribution("/p")
        params = _params(url)
        run = unquote(params[RUN_PARAM])
        assert run == "phone_call_ab&cd"
        assert attributed_run_id(run, params[SIG_PARAM], user_id) == run


class TestReadingTheUrl:
    def test_a_signature_binds_the_run_to_one_account(self) -> None:
        owner, other = uuid.uuid4(), uuid.uuid4()
        params = _params(_signed("run-7", owner))
        assert attributed_run_id("run-7", params[SIG_PARAM], owner) == "run-7"
        stranger = attributed_run_id("run-7", params[SIG_PARAM], other)
        assert stranger != "run-7" and stranger.startswith("media_")

    def test_a_missing_or_forged_signature_files_under_a_fresh_run(self) -> None:
        user_id = uuid.uuid4()
        assert attributed_run_id("run-7", None, user_id).startswith("media_")
        assert attributed_run_id(None, "abc", user_id).startswith("media_")
        assert attributed_run_id("run-7", "0" * 24, user_id).startswith("media_")

    def test_the_context_files_under_the_attributed_run_and_the_caller(self) -> None:
        user_id = uuid.uuid4()
        params = _params(_signed("run-9", user_id))
        tracker = media_spend_context("run-9", params[SIG_PARAM], user_id)
        assert tracker.run_id == "run-9"
        assert tracker.user_id == user_id
        assert tracker.session_id == "media_proxy"
        assert tracker.conversation_id is None
        fresh = media_spend_context("run-9", "bad", user_id)
        assert fresh.run_id.startswith("media_") and fresh.user_id == user_id


def _signed(run_id: str, user_id: uuid.UUID) -> str:
    token = current_tracker.set(TrackingContext(run_id, user_id, "s", None))
    try:
        return with_attribution("/p")
    finally:
        current_tracker.reset(token)
