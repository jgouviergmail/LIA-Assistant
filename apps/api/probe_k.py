import re
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.infrastructure.llm.reasoning.translate import kwargs_for

RESP = re.compile(r"^(gpt-4\.1|gpt-5|o[1-9])", re.IGNORECASE)
REASON = re.compile(r"^(gpt-5|o[1-9])", re.IGNORECASE)
risky = []
for slot, c in sorted(LLM_DEFAULTS.items()):
    if c.provider != "openai" or not RESP.match(c.model):
        continue
    if not REASON.match(c.model):
        continue   # gpt-4.1* n est PAS un modele de raisonnement : top_p est legitime
    eff = kwargs_for("openai", c.model, c.reasoning_effort).get("reasoning_effort")
    if not eff:
        risky.append((slot, c.model, c.top_p, c.temperature))
print("=== creneaux SUR UN MODELE DE RAISONNEMENT gpt-5/o-series, SANS effort rendu ===")
for r in risky:
    print(f"  {r[0]:26} {r[1]:16} top_p={r[2]} temperature={r[3]}")
print(f"  total : {len(risky)}")
