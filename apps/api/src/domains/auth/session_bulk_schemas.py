"""The exact displayed fleet, with no raw authentication material."""

import re

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

from src.core.constants import APPLICATION_SESSION_INDEX_MAX_ENTRIES, SESSION_DISPLAY_ID_LENGTH
from src.domains.auth.session_queries import ListedDeviceSession

_DISPLAY_ID = re.compile(rf"^[0-9a-f]{{{SESSION_DISPLAY_ID_LENGTH}}}$")


class OtherDeviceSessionsSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    current_display_id: StrictStr = Field(pattern=rf"^[0-9a-f]{{{SESSION_DISPLAY_ID_LENGTH}}}$")
    sessions: tuple[ListedDeviceSession, ...] = Field(
        max_length=APPLICATION_SESSION_INDEX_MAX_ENTRIES
    )

    @model_validator(mode="after")
    def require_other_unique_sessions(self) -> OtherDeviceSessionsSelection:
        ids = {item.id for item in self.sessions}
        if len(ids) != len(self.sessions) or self.current_display_id in ids:
            raise ValueError("Other sessions must be unique and exclude the current session")
        if any(item.current is not False for item in self.sessions):
            raise ValueError("The originating session must be known and excluded")
        if any(_DISPLAY_ID.fullmatch(item.id) is None for item in self.sessions):
            raise ValueError("Only opaque displayed session identities may be selected")
        if any(
            item.created_at.tzinfo is None or item.created_at.utcoffset() is None
            for item in self.sessions
        ):
            raise ValueError("Session identities require an aware creation timestamp")
        return self
