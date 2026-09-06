import asyncio
from src.infrastructure.llm.providers.adapter import ProviderAdapter

async def main():
    from src.domains.llm_config.service import LLMConfigService
    from src.infrastructure.database.session import get_db_context
    from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache

    async with get_db_context() as db:
        await ModelCapabilitiesCache.load_from_db(db)

    slots = ["router", "context_resolver", "hitl_classifier", "semantic_pivot",
             "voice_comment", "personality_translation", "briefing", "initiative"]
    from src.core.config import settings
    from src.infrastructure.llm.factory import get_llm_config_for_agent

    print(f"{'creneau':26} {'modele':16} {'top_p cfg':10} {'ENVOYE':10} {'catalogue'}")
    for slot in slots:
        cfg = get_llm_config_for_agent(settings, slot)
        prof = ModelCapabilitiesCache.get(cfg.model)
        kwargs = {"top_p": cfg.top_p, "frequency_penalty": cfg.frequency_penalty,
                  "presence_penalty": cfg.presence_penalty,
                  "reasoning_effort": cfg.reasoning_effort}
        _, out, _ = ProviderAdapter._prepare_provider_config(
            cfg.provider, cfg.model, temperature=cfg.temperature, streaming=False, **kwargs)
        sent = out.get("top_p")
        flag = "  <-- ENVOYE alors que REFUSE" if (sent is not None and prof and not prof.supports_top_p) else ""
        print(f"{slot:26} {cfg.model:16} {str(cfg.top_p):10} {str(sent):10} "
              f"supports_top_p={getattr(prof,'supports_top_p',None)}{flag}")

asyncio.run(main())
