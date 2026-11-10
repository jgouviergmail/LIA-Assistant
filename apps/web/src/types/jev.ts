/** Native decision routing, mirrored from the administration API. */
export type JevUsage =
  | 'meeting_template'
  | 'radio_verification'
  | 'consultation_path'
  | 'consultation_bounded'
  | 'observe_memory'
  | 'observe_interests'
  | 'observe_journal'
  | 'observe_open_loops'
  | 'hitl_exclusion'
  | 'memory_reference_presence'
  | 'hitl_rejection'
  | 'parameter_kind'
  | 'email_classification'
  | 'event_classification';
export type JevReadiness =
  | 'ready'
  | 'missing_key'
  | 'unavailable_model'
  | 'missing_price'
  | 'unavailable';
/** What a gate's score is (ADR-374): a confidence, a bounded concentration, a Noul margin. */
export type JevGateKind = 'choice_confidence' | 'choice_concentration' | 'margin';
/** Each answer alone, or every answer of one call. */
export type JevGateScope = 'each' | 'all';
/** One threshold of a usage, its published bounds and the value the next call uses. */
export interface JevGateStatus {
  key: string;
  kind: JevGateKind;
  scope: JevGateScope;
  default: number;
  minimum: number;
  maximum: number;
  value: number;
}
export interface JevUsageStatus {
  usage: JevUsage;
  label_key: string;
  llm_type: string;
  enabled: boolean;
  effective: boolean;
  readiness: JevReadiness;
  /** None for an observer, which decides nothing. */
  gates: JevGateStatus[];
  /** Every threshold still equals the value its record qualified. */
  qualified: boolean;
}
export interface JevSettings {
  enabled: boolean;
  usages: JevUsageStatus[];
}
export interface JevToggleUpdate {
  usage: JevUsage | null;
  enabled: boolean;
}
/** Some gates of one usage; a gate left out keeps its value. */
export interface JevThresholdUpdate {
  usage: JevUsage;
  values: Record<string, number>;
}

/** One gate's judgements over the window, per bucket 0..100 (ADR-374). */
export interface JevGateStatistics {
  key: string;
  kind: JevGateKind;
  /** The threshold the next operation decides with. */
  threshold: number;
  /** A confidence concludes from bucket threshold × 100 up, a margin up to it. */
  buckets: number[];
}
/** An observer's verdicts beside what its extractor proposed, for one bucket. */
export interface JevAgreementRow {
  verdict: string;
  bucket: number;
  proposed: boolean;
  count: number;
}
/** One usage over the window: cost, outcomes, judgements. */
export interface JevUsageStatistics {
  usage: JevUsage;
  /** Billed calls. */
  calls: number;
  cost_eur: number;
  latency_p50_ms: number | null;
  /** Operations per outcome code. */
  outcomes: Record<string, number>;
  gates: JevGateStatistics[];
  /** An observer's agreement; null for a usage that decides. */
  agreement: JevAgreementRow[] | null;
}
export interface JevStatisticsResponse {
  /** Whole UTC days, today included. */
  days: number;
  since: string;
  usages: JevUsageStatistics[];
}

/** Ephemeral, account-scoped diagnostics. Never persisted in browser storage. */
export interface JevChoicePreview {
  choice: string;
  choice_label: string;
  confidence: number;
  probabilities: { key: string; label: string; probability: number }[];
  omitted_candidates: number;
}

/** Closed native validation codes; historical traces omit this field. */
export type JevInvalidResponseReason =
  | 'envelope_schema'
  | 'answer_set'
  | 'answer_schema'
  | 'option_set'
  | 'unknown_choice'
  | 'probability_sum'
  | 'winning_choice'
  | 'ambiguous_choice';

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
  invalid_response_reason?: JevInvalidResponseReason | null;
  status_code: number | null;
  action: 'pending' | 'selected' | 'preview' | 'observed' | 'fallback' | 'aborted' | 'cancelled';
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
