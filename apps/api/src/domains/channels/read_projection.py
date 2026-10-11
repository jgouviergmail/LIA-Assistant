"""The channel settings list projection shared by HTTP and native application reads."""

from src.domains.channels.models import UserChannelBinding
from src.domains.channels.schemas import ChannelBindingListResponse, ChannelBindingResponse


def channel_bindings_response(bindings: list[UserChannelBinding]) -> ChannelBindingListResponse:
    from src.infrastructure.channels.telegram.bot import get_bot_username

    return ChannelBindingListResponse(
        bindings=[ChannelBindingResponse.model_validate(binding) for binding in bindings],
        total=len(bindings),
        telegram_bot_username=get_bot_username(),
    )
