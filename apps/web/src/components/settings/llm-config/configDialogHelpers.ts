/**
 * Pure logic of the admin LLM-config dialog (audit F011).
 *
 * Extracted from AdminLLMConfigSection's LLMConfigDialog (formerly CC 86) so
 * the decision logic — override-diff building, model filtering, sampling-param
 * visibility, provider/model change semantics and the TTS provider_config
 * plumbing — is unit-testable without driving Radix widgets in jsdom.
 * Behavior is pinned by __tests__/configDialogHelpers.test.ts plus the RTL
 * characterization suite in ../__tests__/AdminLLMConfigSection.test.tsx.
 */

import type {
  LLMModelKind,
  LLMTypeConfig,
  LLMTypeConfigUpdate,
  ModelCapabilities,
  ReasoningEffortValue,
} from '@/types/llm-config';
import { coerceReasoningEffortForModel } from './reasoningHelpers';

// --- TTS provider_config -----------------------------------------------------

/** Parsed shape of the ``provider_config`` JSONB blob stored on
 * ``llm_config_overrides.provider_config`` for the ``voice_tts`` LLM type.
 * Mirrors the structure documented in ``apps/api/src/domains/voice/factory.py``.
 * Each key is optional — only the ones relevant to the active provider are
 * populated when the admin saves. */
export interface TTSProviderConfig {
  voice_male?: string;
  voice_female?: string;
  // Edge-specific
  rate?: string;
  pitch?: string;
  volume?: string;
  // OpenAI-specific
  speed?: number;
  response_format?: string;
  // ElevenLabs-specific
  output_format?: string;
  voice_settings?: {
    stability?: number;
    similarity_boost?: number;
    style?: number;
    use_speaker_boost?: boolean;
  };
}

export const DEFAULT_ELEVENLABS_VOICE_SETTINGS = {
  stability: 0.5,
  similarity_boost: 0.75,
  style: 0.0,
  use_speaker_boost: true,
};

export const OPENAI_RESPONSE_FORMATS = ['mp3', 'opus', 'aac', 'flac', 'wav', 'pcm'] as const;
export const ELEVENLABS_OUTPUT_FORMATS = [
  'mp3_44100_128',
  'mp3_44100_64',
  'mp3_44100_32',
  'mp3_22050_32',
  'pcm_16000',
  'pcm_22050',
  'pcm_24000',
  'pcm_44100',
  'ulaw_8000',
] as const;

export function parseProviderConfig(raw: string | null | undefined): TTSProviderConfig {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as TTSProviderConfig;
    }
  } catch {
    // Malformed override — start from blank rather than crash the form.
  }
  return {};
}

/** Stable JSON stringification (sorted keys, two-level deep) so the diff
 * against the default is order-independent. The backend stores JSONB so key
 * order does not matter semantically, but the LLMTypeConfigUpdate diff
 * compares strings — sort keys to avoid spurious "modified" badges. */
export function stableStringify(obj: TTSProviderConfig): string {
  const sortKeys = (v: unknown): unknown => {
    if (Array.isArray(v)) return v.map(sortKeys);
    if (v && typeof v === 'object') {
      return Object.keys(v as Record<string, unknown>)
        .sort()
        .reduce<Record<string, unknown>>((acc, k) => {
          acc[k] = sortKeys((v as Record<string, unknown>)[k]);
          return acc;
        }, {});
    }
    return v;
  };
  return JSON.stringify(sortKeys(obj));
}

/** The three TTS providers the voice pickers / tuning blocks know about. */
export type TtsProvider = 'edge' | 'openai' | 'elevenlabs';

/** Provider whose TTS tuning block should render, or null (non-TTS type or
 * unsupported provider). */
export function resolveTtsProvider(
  isTts: boolean,
  provider: string | null | undefined
): TtsProvider | null {
  if (!isTts) return null;
  return provider === 'edge' || provider === 'openai' || provider === 'elevenlabs'
    ? provider
    : null;
}

// --- Form lifecycle ------------------------------------------------------------

/** Initial dialog form: a copy of the type's EFFECTIVE config. */
export function formFromConfig(config: LLMTypeConfig): LLMTypeConfigUpdate {
  return {
    provider: config.effective.provider,
    model: config.effective.model,
    temperature: config.effective.temperature,
    top_p: config.effective.top_p,
    frequency_penalty: config.effective.frequency_penalty,
    presence_penalty: config.effective.presence_penalty,
    max_tokens: config.effective.max_tokens,
    timeout_seconds: config.effective.timeout_seconds,
    reasoning_effort: config.effective.reasoning_effort,
    effort: config.effective.effort,
  };
}

/** Provider switch wipes model + reasoning_effort: both are provider/model
 * scoped — a stale value would be persisted as-is and crash the typed
 * reasoning builder once a model is re-picked. (The TTS provider_config wipe
 * stays with the caller, which owns that piece of state.) */
export function formAfterProviderChange(
  form: LLMTypeConfigUpdate,
  provider: string
): LLMTypeConfigUpdate {
  return { ...form, provider, model: '', reasoning_effort: null };
}

/** Model switch keeps reasoning_effort only if its shape still fits the new
 * model's reasoning widget, and keeps the global 'effort' only when the new
 * model declares a matching effort_values entry — otherwise both drop to null
 * (= use the model's default). Prevents a stale override (e.g. an enum effort
 * from a previous model) crashing the typed reasoning builder at runtime. */
export function formAfterModelChange(
  form: LLMTypeConfigUpdate,
  modelId: string,
  newCaps: ModelCapabilities | undefined
): LLMTypeConfigUpdate {
  const newEffortValues = newCaps?.effort_values ?? null;
  const keepEffort =
    form.effort != null && newEffortValues != null && newEffortValues.includes(form.effort);
  return {
    ...form,
    model: modelId,
    reasoning_effort: coerceReasoningEffortForModel(form.reasoning_effort, newCaps),
    effort: keepEffort ? form.effort : null,
  };
}

// --- Override diff ---------------------------------------------------------------

/** Scalar fields compared with plain !== when building the override diff. */
const SCALAR_OVERRIDE_FIELDS = [
  'provider',
  'model',
  'temperature',
  'top_p',
  'frequency_penalty',
  'presence_penalty',
  'max_tokens',
  'timeout_seconds',
] as const;

/** Build the PATCH payload: only fields differing from the type's DEFAULTS are
 * sent (override semantics). reasoning_effort is a discriminated union —
 * JSON-equal. provider_config is only compared for TTS types, via
 * stableStringify so a key-order permutation is not a false positive. */
export function buildConfigUpdate(
  config: LLMTypeConfig,
  form: LLMTypeConfigUpdate,
  providerConfig: TTSProviderConfig
): LLMTypeConfigUpdate {
  const update: LLMTypeConfigUpdate = {};
  const d = config.defaults;

  for (const field of SCALAR_OVERRIDE_FIELDS) {
    if (form[field] !== d[field]) {
      Object.assign(update, { [field]: form[field] });
    }
  }
  if (
    JSON.stringify(form.reasoning_effort ?? null) !== JSON.stringify(d.reasoning_effort ?? null)
  ) {
    update.reasoning_effort = form.reasoning_effort;
  }
  if ((form.effort ?? null) !== (d.effort ?? null)) update.effort = form.effort ?? null;

  if (config.info.required_kind === 'tts') {
    const currentSerialised = stableStringify(providerConfig);
    const defaultSerialised = stableStringify(parseProviderConfig(d.provider_config));
    if (currentSerialised !== defaultSerialised) {
      update.provider_config = currentSerialised;
    }
  }
  return update;
}

/** True when the form value for `field` differs from the type's default —
 * drives the per-field "overridden" badge. */
export function isFieldModified(
  config: LLMTypeConfig,
  form: LLMTypeConfigUpdate,
  field: keyof LLMTypeConfigUpdate
): boolean {
  const defaultVal = config.defaults[field as keyof typeof config.defaults];
  // reasoning_effort is a discriminated union object — JSON-equal it.
  if (field === 'reasoning_effort') {
    return JSON.stringify(form[field] ?? null) !== JSON.stringify(defaultVal ?? null);
  }
  return form[field] !== defaultVal;
}

// --- Model catalogue ---------------------------------------------------------------

/** Backend-authoritative model gate: exact required_kind match + every
 * required capability supported. Covers chat / image / audio / realtime /
 * tts / embedding (voice_transcription targets kind='audio'). */
export function modelMatchesRequirements(
  m: ModelCapabilities,
  requiredKind: LLMModelKind,
  requiredCaps: string[]
): boolean {
  if (m.kind !== requiredKind) return false;
  if (requiredCaps.includes('vision') && !m.supports_vision) return false;
  if (requiredCaps.includes('tools') && !m.supports_tools) return false;
  if (requiredCaps.includes('structured_output') && !m.supports_structured_output) return false;
  return true;
}

/** Model ids selectable for the current provider: live Ollama catalogue when
 * available, static metadata otherwise, gated by kind + capabilities. */
export function computeAvailableModels(
  provider: string | null | undefined,
  metadataProviders: Record<string, ModelCapabilities[]>,
  ollamaModels: ModelCapabilities[],
  requiredKind: LLMModelKind,
  requiredCaps: string[]
): string[] {
  if (!provider) return [];
  const source =
    provider === 'ollama' && ollamaModels.length > 0
      ? ollamaModels
      : (metadataProviders[provider] ?? []);
  return source
    .filter(m => modelMatchesRequirements(m, requiredKind, requiredCaps))
    .map(m => m.model_id);
}

/** Capabilities of `modelId` — static metadata first, then the live Ollama
 * catalogue (a dynamic model is not in metadata). */
export function findModelCapabilities(
  metadataProviders: Record<string, ModelCapabilities[]>,
  ollamaModels: ModelCapabilities[],
  provider: string | null | undefined,
  modelId: string
): ModelCapabilities | undefined {
  return (
    (metadataProviders[provider ?? ''] ?? []).find(m => m.model_id === modelId) ??
    ollamaModels.find(m => m.model_id === modelId)
  );
}

// --- Sampling params -----------------------------------------------------------------

/** Anthropic extended thinking is incompatible with custom temperature/top_p
 * (API constraint — "temperature may only be set to 1 when thinking is
 * enabled"). 'off' enum value / disabled toggle = reasoning off. */
export function isAnthropicThinkingActive(
  provider: string | null | undefined,
  reasoningEffort: ReasoningEffortValue | undefined
): boolean {
  if (provider !== 'anthropic' || !reasoningEffort) return false;
  if ('effort' in reasoningEffort) return reasoningEffort.effort !== 'off';
  if ('enabled' in reasoningEffort) return reasoningEffort.enabled === true;
  return false;
}

export interface SamplingVisibility {
  showTemperature: boolean;
  showTopP: boolean;
  showFrequencyPenalty: boolean;
  showPresencePenalty: boolean;
}

/** Sampling-param visibility: each input is shown if and only if the selected
 * model accepts that specific parameter (Philosophy A: raw truth from
 * llm_models.supports_* columns). Falls back to permissive (all true) when the
 * model is not in metadata — e.g. dynamic Ollama. Temperature/top_p are
 * additionally hidden while Anthropic thinking is active. */
export function samplingVisibility(
  caps: ModelCapabilities | undefined,
  anthropicThinkingActive: boolean
): SamplingVisibility {
  return {
    showTemperature: (caps?.supports_temperature ?? true) && !anthropicThinkingActive,
    showTopP: (caps?.supports_top_p ?? true) && !anthropicThinkingActive,
    showFrequencyPenalty: caps?.supports_frequency_penalty ?? true,
    showPresencePenalty: caps?.supports_presence_penalty ?? true,
  };
}
