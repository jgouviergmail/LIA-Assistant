from src.core.reasoning_intent import ReasoningIntent
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.providers.adapter import ProviderAdapter

def show(model, intent, label):
    kwargs = {"top_p": 0.9, "frequency_penalty": 0.2, "presence_penalty": 0.1}
    if intent is not None:
        kwargs["reasoning_effort"] = intent
    _, cfg, temp = ProviderAdapter._prepare_provider_config(
        "openai", model, temperature=0.3, streaming=False, **kwargs
    )
    prof = ModelCapabilitiesCache.get(model)
    print(f"  {label}")
    print(f"     catalogue : is_reasoning={getattr(prof,'is_reasoning_model',None)} "
          f"supports_temperature={getattr(prof,'supports_temperature',None)} "
          f"supports_top_p={getattr(prof,'supports_top_p',None)}")
    print(f"     ENVOYE    : top_p={cfg.get('top_p')} freq={cfg.get('frequency_penalty')} "
          f"temperature={temp}")

print("=== ce que l adaptateur envoie reellement (temperature demandee = 0.3, top_p = 0.9) ===")
for model in ("gpt-5.2-chat-latest", "gpt-5.6-luna", "gpt-4o"):
    for intent, label in ((None, "aucune intention"), (ReasoningIntent(level="none"), "intention none"),
                          (ReasoningIntent(level="low"), "intention low")):
        show(model, intent, f"{model} / {label}")
    print()
