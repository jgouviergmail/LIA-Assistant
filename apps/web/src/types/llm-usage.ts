/**
 * What one LLM call consumed — tokens and euros, for a single call.
 *
 * It lived in `types/briefing` while the Today dashboard was the only surface
 * showing it. The relationship debrief shows the same thing beside the same
 * kind of artefact, and a generic shape imported from ONE of its users is the
 * pattern the genericity guard refuses: the debrief would describe a cost in
 * the briefing's vocabulary.
 *
 * A DISPLAY summary, never an accounting record — the backend's
 * `token_usage_logs` is the record, and it is what anything summing costs must
 * read.
 */
export interface LLMUsage {
  tokens_in: number;
  tokens_out: number;
  tokens_cache: number;
  /** Computed cost in EUR via the active pricing cache. */
  cost_eur: number;
  model_name: string | null;
}
