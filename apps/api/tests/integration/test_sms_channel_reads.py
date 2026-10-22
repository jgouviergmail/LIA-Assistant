"""Real source authority is shared by Radio and spoken SMS reads."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import delete

from src.core.exceptions import AuthorizationError
from src.domains.agents.telephony.sms_output import guard_sms_voice_output, read_sms_voice
from src.domains.radio.facts import FactPack
from src.domains.radio.formats import RadioFormat
from src.domains.radio.personal import PersonalSource, personal_facts
from src.domains.radio.sms_context import read_sms, sms_pack_current
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.models import SmsMessage
from tests.integration.test_application_memory_independent_transactions import (
    committed_actor as committed_actor,
)
from tests.integration.test_sms_ingestion import authority, message
from tests.integration.test_sms_relations import sms_actor_session as sms_actor_session

pytestmark = pytest.mark.integration


async def test_voice_and_radio_share_consent_and_refuse_withdrawn_or_erased_copies(
    sms_actor_session,
):
    db, user = sms_actor_session
    principal = await authority(db, user)
    await SmsIngestionService(db).ingest(principal, [message(body="Rendez-vous au jardin")])
    with pytest.raises(AuthorizationError):
        await read_sms_voice(user.id, {})
    user.sms_preferences = {"assistant_enabled": True}
    await db.commit()
    voice = await read_sms_voice(user.id, {})
    assert voice.success and "Rendez-vous" in str(voice.structured_data)
    assert "get_sms_tool" not in voice.message
    drafts = await read_sms(user.id, now=datetime.now(UTC), tz=UTC)
    facts = personal_facts({PersonalSource.SMS: drafts})
    pack = FactPack(format=RadioFormat.JOURNAL, facts=facts.day)
    assert len(pack.facts) == 1 and await sms_pack_current(pack)
    user.sms_preferences = {"assistant_enabled": False}
    await db.commit()
    assert not (await guard_sms_voice_output(voice, user.id)).success
    assert not await sms_pack_current(pack)
    user.sms_preferences = {"assistant_enabled": True}
    await db.commit()
    voice = await read_sms_voice(user.id, {})
    await db.execute(delete(SmsMessage).where(SmsMessage.user_id == user.id))
    await db.commit()
    assert not (await guard_sms_voice_output(voice, user.id)).success
    assert not await sms_pack_current(pack)
