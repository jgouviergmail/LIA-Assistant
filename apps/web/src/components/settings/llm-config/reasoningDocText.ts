/**
 * English-only documentation strings for the reasoning_widget tooltip.
 *
 * Intentionally NOT routed through i18n: the Configuration LLM admin UI is
 * technical and stays English-only (consistent with non-translated LLM type
 * names like "router", "planner", "response"). Backend exposes the lookup
 * key via ModelCapabilities.reasoning_doc_i18n_key (the name carries the
 * i18n_key suffix for historical reasons, but no translation tables exist).
 */
export const REASONING_DOC_TEXT: Record<string, string> = {
  openai_o_series: 'OpenAI o-series: low / medium / high. Cannot be disabled.',
  openai_gpt5: 'GPT-5 / mini / nano: minimal / low / medium / high (default medium).',
  openai_gpt5_pro: 'GPT-5 Pro: reasoning is forced to high (no other value accepted).',
  openai_gpt5_codex: 'GPT-5 codex: low / medium / high.',
  openai_gpt5_1: 'GPT-5.1: none / low / medium / high (default none).',
  openai_gpt5_1_codex: 'GPT-5.1 codex / codex-mini: low / medium / high.',
  openai_gpt5_1_codex_max: 'GPT-5.1 codex-max: low / medium / high / xhigh.',
  openai_gpt5_2: 'GPT-5.2: none / low / medium / high / xhigh. Note: minimal is NOT supported.',
  openai_gpt5_2_codex: 'GPT-5.2 codex: low / medium / high / xhigh.',
  openai_gpt5_2_pro: 'GPT-5.2 Pro: medium / high / xhigh.',
  openai_gpt5_2_chat_latest: 'GPT-5.2 chat-latest: reasoning forced to medium (no admin control).',
  openai_gpt5_3_codex: 'GPT-5.3 codex: low / medium / high / xhigh.',
  openai_gpt5_4: 'GPT-5.4: none / low / medium / high / xhigh.',
  openai_gpt5_4_mini: 'GPT-5.4 mini: none / low / medium / high / xhigh.',
  gemini_2_5: 'Gemini 2.5 Flash: thinking budget in tokens. 0 = off, -1 = auto, 1–24576 = custom.',
  gemini_2_5_lite:
    'Gemini 2.5 Flash Lite: thinking budget in tokens. 0 = off, -1 = auto, 512–24576.',
  gemini_2_5_pro: 'Gemini 2.5 Pro: thinking budget in tokens, 128–32768. CANNOT be disabled.',
  gemini_3_x_flash: 'Gemini 3.x Flash: minimal / low / medium / high.',
  gemini_3_x_pro: 'Gemini 3.x Pro: low / medium / high (no minimal). CANNOT be disabled.',
  anthropic_haiku_4_5:
    'Claude Haiku 4.5: extended thinking via a manual token budget. Disabled by ' +
    'default; toggle on + budget 1024–16384. Temperature is locked while thinking is on.',
  anthropic_4_5:
    'Claude Opus 4.5: extended thinking via a manual token budget. Disabled by ' +
    'default; toggle on + budget 1024–16384. Temperature is locked while thinking is on.',
  anthropic_4_6:
    'Claude Opus 4.6: adaptive thinking. off / low / medium / high / max (off = no ' +
    'thinking). Temperature is locked while thinking is on.',
  anthropic_sonnet_4_6:
    'Claude Sonnet 4.6: adaptive thinking. off / low / medium / high / max (off = no ' +
    'thinking). Temperature is locked while thinking is on.',
  deepseek_v4:
    'DeepSeek V4: off / high / max. (low / medium are silently mapped to high by the API.)',
  qwen3_max:
    'Qwen3-max: hybrid thinking, disabled by default. Toggle on + budget in tokens (0–32768).',
  qwen3_5:
    'Qwen3.5 plus / flash: hybrid thinking, enabled by default. Toggle + budget in tokens (0–32768).',
  perplexity_deep: 'Perplexity Sonar Deep Research: low / medium / high.',
};
