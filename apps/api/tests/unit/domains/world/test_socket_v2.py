"""Socket generations are independent of owner preferences and correspondence."""

from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from src.domains.world.socket_models import CommandReceipt, EmoteCommand, SocketVersionedModel
from src.domains.world.wire_models import VersionedModel

pytestmark = pytest.mark.unit


def test_socket_upgrade_does_not_upgrade_preferences_or_messages() -> None:
    assert VersionedModel().version == 1
    assert SocketVersionedModel().version == 2


@pytest.mark.parametrize("version", [True, False, 1, 2.0, "2", None])
def test_socket_version_requires_the_exact_integer_generation(version: object) -> None:
    with pytest.raises(ValidationError):
        SocketVersionedModel.model_validate({"version": version})


def test_emote_command_is_finite_and_cannot_supply_identity_or_business_data() -> None:
    command = {
        "type": "emote",
        "version": 2,
        "epoch": str(uuid4()),
        "seq": 7,
        "emote": "wave",
    }
    assert EmoteCommand.model_validate(command).emote == "wave"
    for extra in ({"account_id": str(uuid4())}, {"message": "private"}, {"tool": "send_email"}):
        with pytest.raises(ValidationError):
            EmoteCommand.model_validate({**command, **extra})
    for invalid in ("invented", "<script>", "", 1):
        with pytest.raises(ValidationError):
            EmoteCommand.model_validate({**command, "emote": invalid})
    for seq in (True, 0, 2**31, 1.0, "1"):
        with pytest.raises(ValidationError):
            EmoteCommand.model_validate({**command, "seq": seq})


def test_pose_receipts_cannot_be_forged_by_an_unrelated_accepted_emote() -> None:
    adapter = TypeAdapter(CommandReceipt)
    pose = adapter.validate_python({"seq": 7, "kind": "pose", "result": "accepted"})
    emote = adapter.validate_python({"seq": 8, "kind": "emote", "result": "accepted"})
    assert pose.kind == "pose" and pose.seq == 7
    assert emote.kind == "emote" and emote.seq == 8
    with pytest.raises(ValidationError):
        adapter.validate_python({"seq": 8, "kind": "emote", "result": "occupied"})
    with pytest.raises(ValidationError):
        adapter.validate_python({"seq": True, "kind": "pose", "result": "accepted"})
