/**
 * English-only caveats about a model's reasoning, for the admin tooltip.
 *
 * Intentionally NOT routed through i18n: the Configuration LLM admin UI is
 * technical and stays English-only (consistent with non-translated LLM type
 * names like "router", "planner", "response"). The backend exposes the lookup
 * key via ModelCapabilities.reasoning_doc_i18n_key (the name carries the
 * i18n_key suffix for historical reasons, but no translation tables exist).
 *
 * These strings deliberately do NOT enumerate the accepted levels any more
 * (ADR-245). The ladder is published per model and rendered in the dropdown
 * right above this text; restating it here made the map a second authority on
 * what a model accepts, and it drifted — entries still said "off" and "-1 =
 * auto" for models whose control had become a level. What is left is what the
 * dropdown cannot show: API quirks, and the constraints a value implies
 * elsewhere in the form. Enforced by __tests__/reasoningDocText.test.ts.
 */
export const REASONING_DOC_TEXT: Record<string, string> = {
  openai_o_series: 'Reasoning cannot be disabled on the o-series.',
  openai_gpt5: 'Defaults to medium when left unset.',
  openai_gpt5_pro: 'Reasoning is forced: the API accepts no other value.',
  openai_gpt5_1: 'Defaults to none when left unset.',
  openai_gpt5_2: 'The API rejects "minimal" on this model, unlike GPT-5.',
  openai_gpt5_2_chat_latest: 'Reasoning is fixed by the API; there is nothing to control here.',
  gemini_2_5: 'Expressed as a token budget rather than a depth.',
  gemini_2_5_lite: 'Expressed as a token budget rather than a depth.',
  gemini_2_5_pro: 'Expressed as a token budget, and reasoning cannot be disabled.',
  gemini_3_x_pro: 'Reasoning cannot be disabled on this model.',
  anthropic_haiku_4_5:
    'Extended thinking is billed inside max_tokens, and locks temperature/top_p while on.',
  anthropic_4_5:
    'Extended thinking is billed inside max_tokens, and locks temperature/top_p while on.',
  anthropic_4_6: 'Adaptive thinking. Locks temperature/top_p while on.',
  anthropic_sonnet_4_6: 'Adaptive thinking. Locks temperature/top_p while on.',
  deepseek_v4: 'The API maps the lighter depths onto its own two, so they behave alike.',
  qwen3_max: 'Hybrid thinking, off by default. An explicit token budget is accepted.',
  qwen3_5: 'Hybrid thinking, on by default. An explicit token budget is accepted.',
  perplexity_deep: 'Reasoning is always on for deep research.',
};
