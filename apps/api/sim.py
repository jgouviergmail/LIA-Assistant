import re
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.infrastructure.llm.reasoning.translate import kwargs_for
from src.infrastructure.llm.providers.responses_adapter import create_responses_llm

RESP = re.compile(r"^(gpt-4\.1|gpt-5|o[1-9])", re.IGNORECASE)
print("=== APRES correction : ce que chaque creneau openai envoie reellement ===")
seen = {}
for slot, c in sorted(LLM_DEFAULTS.items()):
    if c.provider != "openai" or not RESP.match(c.model):
        continue
    eff = kwargs_for("openai", c.model, c.reasoning_effort).get("reasoning_effort")
    llm = create_responses_llm(model=c.model, api_key="k", temperature=c.temperature,
                               top_p=c.top_p, max_tokens=c.max_tokens, reasoning_effort=eff)
    key = (c.model, eff, llm.top_p, llm.temperature)
    seen.setdefault(key, []).append(slot)
for (model, eff, tp, temp), slots in sorted(seen.items(), key=lambda x: x[0][0]):
    print(f"  {model:16} effort={str(eff):6} -> top_p={str(tp):5} temperature={str(temp):5} "
          f"({len(slots)} creneaux)")
