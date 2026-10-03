"""One bounded host directive shared by Pipeline and ReAct."""

import json

from src.core.card_composition import card_composition_ctx
from src.domains.agents.prompts.prompt_loader import load_prompt


def build_card_composition_block() -> str:
    selected = card_composition_ctx.get()
    if selected is None:
        return ""
    target = json.dumps(
        {
            "kind": selected.kind,
            "target_id": selected.target_id,
            "action": selected.action,
            "provider": selected.provider,
        },
        ensure_ascii=True,
    )
    return load_prompt("card_composition_context", version="v1").replace(
        "{selected_target}", target
    )
