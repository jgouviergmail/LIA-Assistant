import re
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.core.reasoning_intent import requested_level
from src.infrastructure.llm.reasoning.translate import kwargs_for

RESP = re.compile(r"^(gpt-4\.1|gpt-5|o[1-9])", re.IGNORECASE)
print("=== creneaux dont le DEFAUT part sur la voie Responses SANS effort rendu ===")
print("    (top_p et temperature sont alors envoyes)")
risky = []
for slot, c in sorted(LLM_DEFAULTS.items()):
    if c.provider != "openai" or not RESP.match(c.model):
        continue
    eff = kwargs_for("openai", c.model, c.reasoning_effort).get("reasoning_effort")
    if not eff:
        risky.append((slot, c.model, c.top_p, c.temperature, requested_level(c.reasoning_effort)))
for slot, model, tp, temp, lvl in risky:
    print(f"  {slot:26} {model:16} top_p={tp} temperature={temp} intention={lvl}")
print(f"\n  total : {len(risky)} creneaux")
