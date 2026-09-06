from src.core.reasoning_intent import ReasoningIntent
from src.infrastructure.llm.reasoning.translate import kwargs_for

print("=== ce que le traducteur rend pour openai (decide la branche Responses) ===")
for label, stored in [
    ("aucune intention (None)", None),
    ("intent provider_default", ReasoningIntent(level="provider_default")),
    ("intent none", ReasoningIntent(level="none")),
    ("intent low", ReasoningIntent(level="low")),
    ("intent high", ReasoningIntent(level="high")),
]:
    for model in ("gpt-5.6-luna", "gpt-5.1", "gpt-4.1-mini"):
        out = kwargs_for("openai", model, stored)
        eff = out.get("reasoning_effort")
        branch = "RAISONNEMENT (ni top_p ni temperature)" if eff else "STANDARD (top_p + temperature ENVOYES)"
        print(f"  {model:14} {label:26} -> reasoning_effort={eff!r:12} {branch}")
    print()
