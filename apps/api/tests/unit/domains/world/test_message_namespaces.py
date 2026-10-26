"""Correspondence must retain the full authoritative instance and scene identity."""

import pytest
from redis.asyncio import Redis

from src.domains.world.mailbox import WorldMailbox
from src.domains.world.messaging import WorldMessaging
from src.domains.world.public_mailbox import PublicMailbox
from src.domains.world.store import WorldStore


@pytest.mark.parametrize(
    ("namespace", "scene"),
    [
        ("another-instance", "lia-campus:7"),
        ("same-instance", "another-scene:7"),
        ("same-instance", "lia-campus:8"),
    ],
)
async def test_mailboxes_and_paid_queues_are_isolated_by_instance_and_scene(
    namespace: str, scene: str
) -> None:
    redis = Redis()
    try:
        first = WorldStore(redis, namespace="same-instance", scene="lia-campus:7", ttl=1800)
        second = WorldStore(redis, namespace=namespace, scene=scene, ttl=1800)
        first_service, second_service = WorldMessaging(first), WorldMessaging(second)
        assert WorldMailbox(first).body_key("same-message") != WorldMailbox(second).body_key(
            "same-message"
        )
        assert PublicMailbox(first).inbox_key("same-owner") != PublicMailbox(second).inbox_key(
            "same-owner"
        )
        assert first_service.attempts.namespace != second_service.attempts.namespace
        assert first_service.public.attempts.namespace != second_service.public.attempts.namespace
        assert len(first_service.attempts.namespace) <= 40
        replica = WorldMessaging(
            WorldStore(redis, namespace="same-instance", scene="lia-campus:7", ttl=1800)
        )
        assert replica.attempts.namespace == first_service.attempts.namespace
        assert replica.mailbox.prefix == first_service.mailbox.prefix
    finally:
        await redis.aclose()
