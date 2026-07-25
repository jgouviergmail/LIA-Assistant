"""Revoking a push token must require owning it.

``POST /notifications/unregister-token`` deletes by token VALUE. It was doing so
without any ownership filter, while its sibling ``delete_token_by_id`` in the
same repository has always scoped its delete to ``user_id`` — so one of the two
paths off the same router let any authenticated caller revoke somebody else's
device registration by presenting its token. The victim simply stops receiving
notifications, and the attacker gets a success response.

The endpoint is now called on every logout (SEC-039), which is what turned a
dormant asymmetry into one worth closing first.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.notifications.repository import FCMTokenRepository
from src.domains.notifications.service import FCMNotificationService


class TestRepositoryScopesTheDelete:
    """The SQL itself must carry the ownership condition."""

    @pytest.mark.asyncio
    async def test_delete_filters_on_both_token_and_user(self):
        """Compile the statement and read its WHERE clause.

        Asserting on the compiled SQL rather than on a mock call: the guarantee
        is that the DELETE cannot match another user's row, and only the
        statement can show that. A test on the repository's arguments would pass
        just as well if the filter were dropped on the way to the query.
        """
        db = MagicMock()
        db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
        repository = FCMTokenRepository(db)
        user_id = uuid4()

        await repository.unregister_token("fcm-token-value", user_id)

        statement = db.execute.await_args.args[0]
        where = str(statement.compile(compile_kwargs={"literal_binds": False}))
        assert "user_fcm_tokens.token = " in where
        assert "user_fcm_tokens.user_id = " in where

    @pytest.mark.asyncio
    async def test_returns_false_when_nothing_matched(self):
        """Another user's token matches no row — and must not report success."""
        db = MagicMock()
        db.execute = AsyncMock(return_value=MagicMock(rowcount=0))
        repository = FCMTokenRepository(db)

        assert await repository.unregister_token("someone-elses-token", uuid4()) is False


class TestServicePropagatesTheOwner:
    """The service must not drop the caller identity on the way down."""

    @pytest.mark.asyncio
    async def test_user_id_reaches_the_repository(self):
        db = MagicMock()
        service = FCMNotificationService(db)
        service.repository = MagicMock()
        service.repository.unregister_token = AsyncMock(return_value=True)
        user_id = uuid4()

        result = await service.unregister_token("fcm-token-value", user_id)

        assert result is True
        service.repository.unregister_token.assert_awaited_once_with("fcm-token-value", user_id)

    @pytest.mark.asyncio
    async def test_the_token_value_is_never_logged(self, caplog):
        """A token is a delivery capability — it identifies a device, not a user.

        The success log used to carry `token_prefix=token[:20]`. Twenty
        characters of an FCM token at INFO level is neither a counter nor an id;
        the user id is both, and is what an operator actually needs.
        """
        db = MagicMock()
        service = FCMNotificationService(db)
        service.repository = MagicMock()
        service.repository.unregister_token = AsyncMock(return_value=True)
        secret = "SECRET-FCM-TOKEN-VALUE-0123456789"

        with caplog.at_level("INFO"):
            await service.unregister_token(secret, uuid4())

        assert secret[:20] not in caplog.text
