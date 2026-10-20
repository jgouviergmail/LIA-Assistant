"""Faithful bounded SMS evidence; short replies are facts, never disposable metadata."""

import json
from collections.abc import Mapping, Sequence

from pydantic import ValidationError

from src.domains.agents.sms.projection import SmsToolItem
from src.domains.agents.utils.content_wrapper import wrap_external_content


def sms_items_prompt(items: Sequence[Mapping[str, object]]) -> str:
    selected = []
    for index, item in enumerate(items, 1):
        try:
            message = SmsToolItem.model_validate(
                {key: value for key, value in item.items() if key != "index"}
            )
        except ValidationError:
            return "SMS reference is unavailable; read the source again."
        selected.append(
            {"index": index, **message.model_dump(mode="json", exclude={"owner_id", "revision"})}
        )
    content = json.dumps({"sms_messages": selected}, ensure_ascii=False, separators=(",", ":"))
    return (
        wrap_external_content(content, source_url="personal_sms_archive", source_type="sms")
        if selected
        else ""
    )
