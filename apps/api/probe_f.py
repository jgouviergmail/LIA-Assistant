from src.domains.llm_config.constants import LLM_DEFAULTS

slots = ["router", "context_resolver", "hitl_classifier", "semantic_pivot",
         "voice_comment", "personality_translation", "briefing", "initiative"]
print(f"{'creneau':26} {'modele (defaut)':22} {'top_p':7} {'freq':6} {'pres':6}")
for s in slots:
    c = LLM_DEFAULTS.get(s)
    if c is None:
        print(f"{s:26} ABSENT des defauts"); continue
    print(f"{s:26} {c.model:22} {c.top_p:<7} {c.frequency_penalty:<6} {c.presence_penalty:<6}")
print()
non_neutral = [(s, c.top_p, c.frequency_penalty, c.presence_penalty)
               for s, c in LLM_DEFAULTS.items()
               if c.provider == "openai" and (c.top_p != 1.0 or c.frequency_penalty or c.presence_penalty)]
print("creneaux openai a echantillonnage NON NEUTRE :", non_neutral or "aucun")
