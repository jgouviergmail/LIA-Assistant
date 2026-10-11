"""Original public contract for rewriting minutes with another owned template."""

from typing import Literal

from pydantic import BaseModel, Field

from src.core.constants import MEETINGS_TEMPLATE_REF_MAX
from src.core.meeting_templates import TEMPLATE_REF_PATTERN


class MeetingReformatRequest(BaseModel):
    """Write the minutes again with another template (ADR-259)."""

    template_ref: str = Field(
        max_length=MEETINGS_TEMPLATE_REF_MAX, pattern=TEMPLATE_REF_PATTERN, description="Template."
    )
    mode: Literal["replace", "new"] = Field(
        description="replace = these minutes; new = new minutes from the same transcript."
    )
