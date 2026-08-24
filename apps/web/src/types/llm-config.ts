/**
 * LLM Configuration Admin types.
 * Mirrors backend Pydantic schemas for type safety.
 *
 * reasoning_effort is ONE shape for every provider (ADR-245): an ordinal level,
 * an optional token budget and an orthogonal exclude-from-output flag. It
 * replaced a four-member discriminated union dispatched on the model's
 * reasoning_widget column — three authorities that had to agree, and did not.
 * What a given model accepts now travels with the model, in the resolved
 * profile ModelCapabilities publishes.
 */

// --- Provider Keys ---

export interface ProviderKeyStatus {
  provider: string;
  display_name: string;
  has_db_key: boolean;
  masked_key: string | null;
  updated_at: string | null;
}

export interface ProviderKeysResponse {
  providers: ProviderKeyStatus[];
}

export interface ProviderKeyUpdate {
  key: string;
}

// --- Reasoning Effort ---

/** The ordinal ladder, ascending. Mirrors backend `core.reasoning_intent.LEVELS`.
 * `provider_default` is the identity — it asks for nothing and produces no
 * kwarg on any provider — which is why it sits at the bottom and is never a
 * coercion target. */
export const REASONING_LEVELS = [
  'provider_default',
  'none',
  'minimal',
  'low',
  'medium',
  'high',
  'xhigh',
  'max',
] as const;

export type ReasoningLevel = (typeof REASONING_LEVELS)[number];

/** Numeric budget range a model accepts, as RESOLVED by the backend profile —
 * the same bounds its validator enforces. Mirrors backend ReasoningBudgetRange. */
export interface ReasoningBudgetRange {
  min: number;
  max: number;
}

/** The single stored shape of reasoning_effort. Mirrors backend
 * `ReasoningIntent`. `null` means no override: the model's own default applies. */
export interface ReasoningIntentValue {
  level: ReasoningLevel;
  budget_tokens: number | null;
  exclude_from_output: boolean;
}

/** What the form and the API carry: an intent, or nothing. */
export type ReasoningEffortValue = ReasoningIntentValue | null;

// --- LLM Agent Config ---

export interface LLMAgentConfig {
  provider: string;
  provider_config: string;
  model: string;
  temperature: number;
  top_p: number;
  frequency_penalty: number;
  presence_penalty: number;
  max_tokens: number;
  timeout_seconds: number | null;
  reasoning_effort: ReasoningEffortValue;
}

// --- LLM Type Config ---

/** Visual power tier for admin color-coding. */
export type PowerTier = 'critical' | 'high' | 'medium' | 'low';

/** Kind of model an LLM type expects. Drives the ?kinds= query param when
 * the frontend fetches /llm-config/metadata. */
export type LLMModelKind = 'chat' | 'image' | 'audio' | 'realtime' | 'tts' | 'embedding';

export interface LLMTypeInfo {
  llm_type: string;
  display_name: string;
  category: string;
  description_key: string;
  required_capabilities: string[];
  power_tier: PowerTier | null;
  required_kind: LLMModelKind;
}

export interface LLMTypeConfig {
  llm_type: string;
  info: LLMTypeInfo;
  effective: LLMAgentConfig;
  overrides: Record<string, unknown>;
  defaults: LLMAgentConfig;
  is_overridden: boolean;
}

export interface LLMTypeConfigUpdate {
  provider?: string | null;
  model?: string | null;
  temperature?: number | null;
  top_p?: number | null;
  frequency_penalty?: number | null;
  presence_penalty?: number | null;
  max_tokens?: number | null;
  timeout_seconds?: number | null;
  reasoning_effort?: ReasoningEffortValue;
  provider_config?: string | null;
}

export interface LLMConfigListResponse {
  configs: LLMTypeConfig[];
}

// --- Metadata ---

export interface ModelCapabilities {
  model_id: string;
  kind: LLMModelKind;
  max_output_tokens: number;
  supports_tools: boolean;
  supports_structured_output: boolean;
  supports_vision: boolean;
  is_reasoning_model: boolean;

  // The RESOLVED reasoning profile (ADR-245), never the catalogue's own
  // columns: the backend derives these from the same function its validator
  // and its runtime translator use, so what this UI offers is exactly what the
  // API accepts. Publishing the raw columns instead is how the dropdown came
  // to offer `minimal` on a model whose API refused it.
  /** Translator family; 'none' when the model does not reason. */
  reasoning_family: string;
  /** The accepted ladder, ascending. Empty = no reasoning control at all. */
  reasoning_levels: ReasoningLevel[];
  /** Whether reasoning can be turned off ('none' is offered). */
  reasoning_can_disable: boolean;
  /** Whether an explicit token budget is expressible. */
  reasoning_supports_budget: boolean;
  /** Whether exclude_from_output actually reaches this family's provider. */
  reasoning_supports_exclude: boolean;
  reasoning_budget_range: ReasoningBudgetRange | null;
  reasoning_doc_i18n_key: string | null;
  // Per-model sampling support — drives conditional rendering of
  // temperature / top_p / frequency_penalty / presence_penalty inputs.
  // Mirrors llm_models.supports_* columns. Philosophy A: the UI shows
  // only what the API accepts.
  supports_temperature: boolean;
  supports_top_p: boolean;
  supports_frequency_penalty: boolean;
  supports_presence_penalty: boolean;
  cost_input: number | null;
  cost_output: number | null;
}

export interface ProviderModelsMetadata {
  providers: Record<string, ModelCapabilities[]>;
}

// --- Voice picker (admin TTS) ---

/** One voice exposed to the admin TTS picker. Mirrors the backend
 * ``VoiceOptionPayload`` from src/domains/voice/admin_router.py. */
export interface VoiceOption {
  voice_id: string;
  label: string;
  gender: string | null;
  language: string | null;
}

/** Response shape for ``GET /admin/voice/voices?provider=X``. */
export interface VoicesResponse {
  provider: 'edge' | 'openai' | 'elevenlabs';
  voices: VoiceOption[];
  source: 'static' | 'live';
}

// --- Ollama dynamic discovery ---

export interface OllamaModelCapabilities extends ModelCapabilities {
  size: string | null;
  family: string | null;
}

export interface OllamaModelsResponse {
  models: OllamaModelCapabilities[];
  source: 'live' | 'fallback';
}

// --- UI helpers ---

export const LLM_CATEGORY_LABELS: Record<string, string> = {
  pipeline: 'Pipeline',
  domain_agents: 'Domain Agents',
  query_response: 'Query & Response',
  hitl: 'HITL',
  memory: 'Memory',
  background: 'Background',
  briefing: 'Briefing',
  specialized: 'Specialized',
};

export const LLM_CATEGORIES_ORDER = [
  'pipeline',
  'domain_agents',
  'query_response',
  'hitl',
  'memory',
  'background',
  'briefing',
  'specialized',
];
