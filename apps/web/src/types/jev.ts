/** Native decision routing, mirrored from the administration API. */
export type JevUsage =
  | 'meeting_template'
  | 'filter_email'
  | 'filter_event'
  | 'filter_task'
  | 'filter_file'
  | 'radio_verification'
  | 'consultation_path'
  | 'consultation_bounded'
  | 'observe_memory'
  | 'observe_interests'
  | 'observe_journal'
  | 'observe_open_loops'
  | 'hitl_exclusion'
  | 'filter_reminder'
  | 'filter_ticket'
  | 'filter_mcp'
  | 'filter_document'
  | 'initiative_utility';
export type JevReadiness =
  | 'ready'
  | 'missing_key'
  | 'unavailable_model'
  | 'missing_price'
  | 'unavailable';
export interface JevUsageStatus {
  usage: JevUsage;
  label_key: string;
  llm_type: string;
  enabled: boolean;
  effective: boolean;
  readiness: JevReadiness;
}
export interface JevSettings {
  enabled: boolean;
  usages: JevUsageStatus[];
}
export interface JevToggleUpdate {
  usage: JevUsage | null;
  enabled: boolean;
}

/** Ephemeral, account-scoped diagnostics. Never persisted in browser storage. */
export interface JevChoicePreview {
  choice: string;
  choice_label: string;
  confidence: number;
  probabilities: { key: string; label: string; probability: number }[];
  omitted_candidates: number;
}

export interface JevCallTrace {
  id: string;
  run_id: string;
  caller: string;
  usage: string;
  started_at: string;
  requested_model: string;
  reported_model: string | null;
  duration_ms: number;
  context: { text: string; original_characters: number; omitted_characters: number };
  observed_result?: JevCallTrace['context'] | null;
  response: JevChoicePreview | null;
  responses?: Record<string, JevChoicePreview>;
  outcome: string;
  status_code: number | null;
  action: 'pending' | 'selected' | 'preview' | 'observed' | 'fallback' | 'aborted' | 'cancelled';
  applied_decisions?: Record<string, 'match' | 'non_match' | 'unknown'>;
  decision_labels?: Record<string, string>;
  action_target: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_eur: number | null;
}

export interface JevTracePage {
  calls: JevCallTrace[];
  limit: number;
  retention_seconds: number;
}
