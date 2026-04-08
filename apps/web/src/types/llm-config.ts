/**
 * LLM Configuration Admin types.
 * Mirrors backend Pydantic schemas for type safety.
 *
 * reasoning_effort values must stay in sync with backend:
 * - schemas.py: Literal["none", "minimal", "low", "medium", "high", "xhigh"]
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

/** Must stay in sync with backend Literal in schemas.py */
export type ReasoningEffort = 'none' | 'minimal' | 'low' | 'medium' | 'high' | 'xhigh';

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
  reasoning_effort: ReasoningEffort | null;
}

// --- LLM Type Config ---

/** Visual power tier for admin color-coding. */
export type PowerTier = 'critical' | 'high' | 'medium' | 'low';

export interface LLMTypeInfo {
  llm_type: string;
  display_name: string;
  category: string;
  description_key: string;
  required_capabilities: string[];
  power_tier: PowerTier | null;
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
  reasoning_effort?: ReasoningEffort | null;
  provider_config?: string | null;
}

export interface LLMConfigListResponse {
  configs: LLMTypeConfig[];
}

// --- Metadata ---

export interface ModelCapabilities {
  model_id: string;
  max_output_tokens: number;
  supports_tools: boolean;
  supports_structured_output: boolean;
  supports_vision: boolean;
  is_reasoning_model: boolean;
  is_image_model?: boolean;
  cost_input: number | null;
  cost_output: number | null;
}

export interface ProviderModelsMetadata {
  providers: Record<string, ModelCapabilities[]>;
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
  specialized: 'Specialized',
};

export const LLM_CATEGORIES_ORDER = [
  'pipeline',
  'domain_agents',
  'query_response',
  'hitl',
  'memory',
  'background',
  'specialized',
];
