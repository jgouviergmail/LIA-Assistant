"""LangChain's domain loop receives bounded SMS evidence; the response keeps one data block."""

import json

from src.domains.agents.sms.projection import SmsToolPage
from src.domains.agents.sms.proof import page_proof
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.utils.content_wrapper import wrap_external_content


class SmsModelToolOutput(UnifiedToolOutput):
    def __str__(self) -> str:
        page = SmsToolPage.model_validate(
            self.structured_data.get("sms_archive", self.structured_data)
        )
        content = json.dumps(
            {
                "sms_snapshot": page_proof(page),
                "data": (
                    self.structured_data
                    if "sms_archive" in self.structured_data
                    else page.model_dump(mode="json")
                ),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return wrap_external_content(content, source_url="personal_sms_archive", source_type="sms")
