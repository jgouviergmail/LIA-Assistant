"""An output projection cannot become a shortcut around participant privacy."""

from uuid import uuid4

import pytest

from src.domains.world.message_content import (
    MessageAddress,
    MessageReceipt,
    MessageVariant,
    StoredMessage,
    project_message,
)

pytestmark = pytest.mark.unit


def sample() -> StoredMessage:
    return StoredMessage(
        id=str(uuid4()),
        epoch=str(uuid4()),
        sender=MessageAddress(account=str(uuid4()), public_id=str(uuid4()), alias="A"),
        recipient=MessageAddress(account=str(uuid4()), public_id=str(uuid4()), alias="B"),
        original="Bonjour",
        source_language="fr",
        created_at=100.0,
        expires_at=1900.0,
    )


def test_even_the_projection_refuses_a_non_participant() -> None:
    with pytest.raises(ValueError, match="world_message_unavailable"):
        project_message(sample(), str(uuid4()), "en", 101.0)


def test_outgoing_text_stays_readable_while_its_translation_is_pending_or_uncertain() -> None:
    message = sample()
    message.variants["en"] = MessageVariant(
        job_id=message.id, payer=message.sender.account, status="pending", deadline=120.0
    )
    own = project_message(message, message.sender.account, "fr", 101.0)
    assert own.text == "Bonjour" and own.status == "pending"
    uncertain = project_message(message, message.sender.account, "fr", 121.0)
    assert uncertain.status == "uncertain" and uncertain.receipt is None


def test_completed_translation_and_receipt_do_not_cross_their_separate_audiences() -> None:
    message = sample()
    message.variants["en"] = MessageVariant(
        job_id=message.id,
        payer=message.sender.account,
        status="translated",
        deadline=120.0,
        text="Hello",
        receipt=MessageReceipt(run_id="inert", tokens_in=40, tokens_out=4, cost_eur=0.001),
    )
    incoming = project_message(message, message.recipient.account, "en", 102.0)
    assert incoming.text == "Hello" and incoming.status == "translated" and incoming.receipt is None
    changed = project_message(message, message.recipient.account, "de", 102.0)
    assert changed.text is None and changed.status == "unavailable"
    sender = project_message(message, message.sender.account, "fr", 102.0)
    assert sender.receipt is not None


def test_receipt_follows_the_latest_paid_variant_when_an_older_language_is_replaced() -> None:
    message = sample()
    for language, deadline in (("en", 110.0), ("de", 120.0), ("en", 130.0)):
        message.variants[language] = MessageVariant(
            job_id=str(uuid4()),
            payer=message.recipient.account,
            status="translated",
            deadline=deadline,
            text="Hello",
            receipt=MessageReceipt(run_id=str(deadline), tokens_in=30, tokens_out=4),
        )
    receipt = project_message(message, message.recipient.account, "en", 140.0).receipt
    assert receipt is not None and receipt.run_id == "130.0"
    assert project_message(message, message.sender.account, "fr", 140.0).receipt is None
