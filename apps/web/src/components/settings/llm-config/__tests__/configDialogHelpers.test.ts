/**
 * configDialogHelpers — unit tests (audit F011).
 *
 * Complements the RTL characterization of AdminLLMConfigSection: these cover
 * the pure decision logic that jsdom cannot conveniently drive through Radix
 * widgets — provider/model switch semantics, the override diff builder, model
 * gating and sampling visibility.
 */

import { describe, it, expect } from 'vitest';

import {
  buildConfigUpdate,
  computeAvailableModels,
  findModelCapabilities,
  formAfterModelChange,
  formAfterProviderChange,
  formForSave,
  formFromConfig,
  isAnthropicThinkingActive,
  isFieldModified,
  modelMatchesRequirements,
  parseProviderConfig,
  resolveTtsProvider,
  samplingVisibility,
  stableStringify,
  structuredErrorDetail,
} from '../configDialogHelpers';
import type {
  LLMAgentConfig,
  LLMTypeConfig,
  ModelCapabilities,
  ReasoningIntentValue,
} from '@/types/llm-config';

/** One stored shape for every provider (ADR-245). */
const HIGH: ReasoningIntentValue = {
  level: 'high',
  budget_tokens: null,
  exclude_from_output: false,
};
const LOW: ReasoningIntentValue = { ...HIGH, level: 'low' };

function caps(overrides: Partial<ModelCapabilities> = {}): ModelCapabilities {
  return {
    model_id: 'm1',
    kind: 'chat',
    max_output_tokens: 4096,
    supports_tools: true,
    supports_structured_output: true,
    supports_vision: true,
    is_reasoning_model: false,
    reasoning_family: 'none',
    reasoning_levels: [],
    reasoning_can_disable: true,
    reasoning_supports_budget: false,
    reasoning_supports_exclude: false,
    reasoning_budget_range: null,
    reasoning_doc_i18n_key: null,
    supports_temperature: true,
    supports_top_p: true,
    supports_frequency_penalty: true,
    supports_presence_penalty: true,
    cost_input: null,
    cost_output: null,
    ...overrides,
  };
}

/** A second model that reasons, for the model-switch cases. */
const LADDER_CAPS = caps({
  model_id: 'm2',
  is_reasoning_model: true,
  reasoning_family: 'openai',
  reasoning_levels: ['none', 'low', 'medium', 'high'],
});

function agentCfg(overrides: Partial<LLMAgentConfig> = {}): LLMAgentConfig {
  return {
    provider: 'openai',
    provider_config: '',
    model: 'm1',
    temperature: 0.7,
    top_p: 1,
    frequency_penalty: 0,
    presence_penalty: 0,
    max_tokens: 1000,
    timeout_seconds: null,
    reasoning_effort: null,
    ...overrides,
  };
}

function typeConfig(
  effective: Partial<LLMAgentConfig> = {},
  defaults: Partial<LLMAgentConfig> = {},
  requiredKind: LLMTypeConfig['info']['required_kind'] = 'chat'
): LLMTypeConfig {
  return {
    llm_type: 'router',
    info: {
      llm_type: 'router',
      display_name: 'Router',
      category: 'pipeline',
      description_key: 'desc.router',
      required_capabilities: [],
      power_tier: null,
      required_kind: requiredKind,
    },
    effective: agentCfg(effective),
    overrides: {},
    defaults: agentCfg(defaults),
    is_overridden: false,
  };
}

describe('parseProviderConfig', () => {
  it('returns {} for empty, malformed or non-object payloads', () => {
    expect(parseProviderConfig(null)).toEqual({});
    expect(parseProviderConfig('')).toEqual({});
    expect(parseProviderConfig('not json')).toEqual({});
    expect(parseProviderConfig('[1,2]')).toEqual({});
  });

  it('parses a valid blob', () => {
    expect(parseProviderConfig('{"rate":"+10%"}')).toEqual({ rate: '+10%' });
  });
});

describe('stableStringify', () => {
  it('is key-order independent (two levels deep)', () => {
    const a = stableStringify({ voice_male: 'x', voice_settings: { style: 1, stability: 0.2 } });
    const b = stableStringify({
      voice_settings: { stability: 0.2, style: 1 },
      voice_male: 'x',
    });
    expect(a).toBe(b);
  });
});

describe('resolveTtsProvider', () => {
  it('returns null for non-TTS types and unsupported providers', () => {
    expect(resolveTtsProvider(false, 'edge')).toBeNull();
    expect(resolveTtsProvider(true, 'ollama')).toBeNull();
    expect(resolveTtsProvider(true, null)).toBeNull();
  });

  it('returns the provider for the three supported TTS providers', () => {
    expect(resolveTtsProvider(true, 'edge')).toBe('edge');
    expect(resolveTtsProvider(true, 'openai')).toBe('openai');
    expect(resolveTtsProvider(true, 'elevenlabs')).toBe('elevenlabs');
  });
});

describe('form lifecycle', () => {
  it('formFromConfig copies the EFFECTIVE config', () => {
    const cfg = typeConfig({ temperature: 1.5, model: 'm2' });
    expect(formFromConfig(cfg)).toMatchObject({
      temperature: 1.5,
      model: 'm2',
      provider: 'openai',
    });
  });

  it('provider switch wipes model and reasoning_effort, keeps the rest', () => {
    const next = formAfterProviderChange(
      { provider: 'openai', model: 'm1', reasoning_effort: HIGH, temperature: 1.2 },
      'anthropic'
    );
    expect(next).toEqual({
      provider: 'anthropic',
      model: '',
      reasoning_effort: null,
      temperature: 1.2,
    });
  });

  it('model switch keeps a level the new model also offers', () => {
    const next = formAfterModelChange(
      { provider: 'openai', model: 'm1', reasoning_effort: HIGH },
      'm2',
      LADDER_CAPS
    );
    expect(next.model).toBe('m2');
    expect(next.reasoning_effort).toEqual(HIGH);
  });

  it('model switch drops a level the new model does not offer', () => {
    const next = formAfterModelChange(
      { provider: 'openai', model: 'm1', reasoning_effort: { ...HIGH, level: 'xhigh' } },
      'm2',
      LADDER_CAPS
    );
    expect(next.reasoning_effort).toBeNull();
  });

  it('model switch drops reasoning_effort when the new model does not reason', () => {
    const next = formAfterModelChange(
      { provider: 'openai', model: 'm1', reasoning_effort: HIGH },
      'm2',
      caps({ model_id: 'm2' })
    );
    expect(next.reasoning_effort).toBeNull();
  });
});

describe('buildConfigUpdate', () => {
  it('returns an empty diff when the form matches the defaults', () => {
    const cfg = typeConfig();
    expect(buildConfigUpdate(cfg, formFromConfig(cfg), {})).toEqual({});
  });

  it('includes only scalar fields that differ from the defaults', () => {
    const cfg = typeConfig();
    const form = { ...formFromConfig(cfg), max_tokens: 2222, temperature: 1.3 };
    expect(buildConfigUpdate(cfg, form, {})).toEqual({ max_tokens: 2222, temperature: 1.3 });
  });

  it('compares reasoning_effort by value (a fresh but equal object is NOT a diff)', () => {
    const cfg = typeConfig({ reasoning_effort: HIGH }, { reasoning_effort: HIGH });
    const form = { ...formFromConfig(cfg), reasoning_effort: { ...HIGH } };
    expect(buildConfigUpdate(cfg, form, {})).toEqual({});
  });

  it('is not fooled by key order between what the API sent and what the form rebuilt', () => {
    const cfg = typeConfig({ reasoning_effort: HIGH }, { reasoning_effort: HIGH });
    const reordered: ReasoningIntentValue = {
      exclude_from_output: false,
      budget_tokens: null,
      level: 'high',
    };
    const form = { ...formFromConfig(cfg), reasoning_effort: reordered };
    expect(buildConfigUpdate(cfg, form, {})).toEqual({});
  });

  it('sends reasoning_effort when it differs from the default', () => {
    const cfg = typeConfig();
    const form = { ...formFromConfig(cfg), reasoning_effort: LOW };
    expect(buildConfigUpdate(cfg, form, {})).toEqual({
      reasoning_effort: LOW,
    });
  });

  it('sends provider_config for TTS types only, stable-serialised', () => {
    const tts = typeConfig({}, {}, 'tts');
    expect(buildConfigUpdate(tts, formFromConfig(tts), { rate: '+25%' })).toEqual({
      provider_config: '{"rate":"+25%"}',
    });
    // Same tuning as the default blob → no diff (key order irrelevant).
    const withDefault = typeConfig(
      { provider_config: '{"rate":"+10%"}' },
      { provider_config: '{"rate":"+10%"}' },
      'tts'
    );
    expect(buildConfigUpdate(withDefault, formFromConfig(withDefault), { rate: '+10%' })).toEqual(
      {}
    );
    // Non-TTS types never send provider_config.
    const chat = typeConfig();
    expect(buildConfigUpdate(chat, formFromConfig(chat), { rate: '+25%' })).toEqual({});
  });
});

describe('formForSave', () => {
  const toggleCaps = caps({
    model_id: 'qwen3.8-max',
    reasoning_family: 'qwen_toggle_budget',
    reasoning_levels: ['none', 'minimal', 'low', 'medium', 'high'],
    reasoning_supports_budget: true,
    reasoning_budget_range: { min: 0, max: 32768 },
  });

  it("nulls a reasoning_effort the SELECTED model refuses (the prod 422's exact path)", () => {
    // Prod 2026-08-14: the dialog's metadata lacked the freshly created model,
    // so ReasoningSection rendered nothing and the form silently carried the
    // previous model's enum shape into the PUT → 422 wrong_reasoning_effort_shape
    // on every save attempt. Save-time coercion is the chokepoint that survives
    // stale metadata, free-text models and any future form drift.
    const stale: ReasoningIntentValue = { ...HIGH, level: 'xhigh' };
    const form = { model: 'qwen3.8-max', reasoning_effort: stale };
    expect(formForSave(form, toggleCaps, true).reasoning_effort).toBeNull();
  });

  it('keeps a reasoning_effort the selected model accepts', () => {
    const form = { model: 'qwen3.8-max', reasoning_effort: { ...HIGH, budget_tokens: 8192 } };
    expect(formForSave(form, toggleCaps, true).reasoning_effort).toEqual({
      level: 'high',
      budget_tokens: 8192,
      exclude_from_output: false,
    });
  });

  it('does NOT wipe a value whose only fault is a budget the user can see', () => {
    // Regression: an out-of-range budget made save-time coercion null the WHOLE
    // override — silently discarding the level the admin had chosen, on a field
    // that is on screen with its bounds printed under it. The backend rejects
    // the same bound with an explicit message the dialog already surfaces, so
    // the honest answer is to let it speak.
    const typed: ReasoningIntentValue = { ...HIGH, budget_tokens: 999_999 }; // range is 0-32768
    const form = { model: 'qwen3.8-max', reasoning_effort: typed };
    expect(formForSave(form, toggleCaps, true).reasoning_effort).toEqual(typed);
  });

  it('still wipes a level the widget cannot even display', () => {
    const unreachable: ReasoningIntentValue = { ...HIGH, level: 'xhigh' };
    const form = { model: 'qwen3.8-max', reasoning_effort: unreachable };
    expect(formForSave(form, toggleCaps, true).reasoning_effort).toBeNull();
  });

  it('nulls the effort for a model absent from the loaded catalogue', () => {
    const form = { model: 'brand-new-model', reasoning_effort: LOW };
    expect(formForSave(form, undefined, true).reasoning_effort).toBeNull();
  });

  it('leaves the form untouched when the catalogue never loaded (cannot prove anything)', () => {
    const form = { model: 'm1', reasoning_effort: LOW };
    expect(formForSave(form, undefined, false)).toBe(form);
  });
});

describe('isFieldModified', () => {
  it('compares scalars with !== and reasoning_effort by value', () => {
    const cfg = typeConfig({}, { temperature: 0.7, reasoning_effort: HIGH });
    expect(isFieldModified(cfg, { temperature: 0.7 }, 'temperature')).toBe(false);
    expect(isFieldModified(cfg, { temperature: 1.2 }, 'temperature')).toBe(true);
    expect(isFieldModified(cfg, { reasoning_effort: { ...HIGH } }, 'reasoning_effort')).toBe(false);
    expect(isFieldModified(cfg, { reasoning_effort: LOW }, 'reasoning_effort')).toBe(true);
  });
});

describe('model gating', () => {
  it('rejects kind mismatches and missing required capabilities', () => {
    expect(modelMatchesRequirements(caps({ kind: 'tts' }), 'chat', [])).toBe(false);
    expect(modelMatchesRequirements(caps({ supports_vision: false }), 'chat', ['vision'])).toBe(
      false
    );
    expect(modelMatchesRequirements(caps({ supports_tools: false }), 'chat', ['tools'])).toBe(
      false
    );
    expect(
      modelMatchesRequirements(caps({ supports_structured_output: false }), 'chat', [
        'structured_output',
      ])
    ).toBe(false);
    expect(modelMatchesRequirements(caps(), 'chat', ['vision', 'tools'])).toBe(true);
  });

  it('computeAvailableModels: empty without a provider, prefers the live Ollama catalogue', () => {
    const metadata = { openai: [caps()], ollama: [caps({ model_id: 'static-ollama' })] };
    expect(computeAvailableModels(null, metadata, [], 'chat', [])).toEqual([]);
    expect(computeAvailableModels('openai', metadata, [], 'chat', [])).toEqual(['m1']);
    expect(
      computeAvailableModels('ollama', metadata, [caps({ model_id: 'live-1' })], 'chat', [])
    ).toEqual(['live-1']);
    // Empty live catalogue → fall back to static metadata.
    expect(computeAvailableModels('ollama', metadata, [], 'chat', [])).toEqual(['static-ollama']);
  });

  it('findModelCapabilities: metadata first, then the live Ollama catalogue', () => {
    const metadata = { openai: [caps({ model_id: 'm1', supports_vision: false })] };
    const live = [caps({ model_id: 'dyn-1' })];
    expect(findModelCapabilities(metadata, live, 'openai', 'm1')?.supports_vision).toBe(false);
    expect(findModelCapabilities(metadata, live, 'openai', 'dyn-1')?.model_id).toBe('dyn-1');
    expect(findModelCapabilities(metadata, live, 'openai', 'missing')).toBeUndefined();
  });
});

describe('sampling visibility', () => {
  it('isAnthropicThinkingActive reads the one intent, and only for Anthropic', () => {
    const off: ReasoningIntentValue = { ...HIGH, level: 'none' };
    const budgeted: ReasoningIntentValue = {
      ...HIGH,
      level: 'provider_default',
      budget_tokens: 1024,
    };
    expect(isAnthropicThinkingActive('openai', HIGH)).toBe(false);
    expect(isAnthropicThinkingActive('anthropic', null)).toBe(false);
    expect(isAnthropicThinkingActive('anthropic', undefined)).toBe(false);
    expect(isAnthropicThinkingActive('anthropic', off)).toBe(false);
    expect(isAnthropicThinkingActive('anthropic', HIGH)).toBe(true);
    // A budget asked without a depth still means "think", and still locks
    // temperature: the API constraint is about thinking, not about the word.
    expect(isAnthropicThinkingActive('anthropic', budgeted)).toBe(true);
  });

  it('defaults to permissive when the model is unknown, honours supports_* flags', () => {
    expect(samplingVisibility(undefined, false)).toEqual({
      showTemperature: true,
      showTopP: true,
      showFrequencyPenalty: true,
      showPresencePenalty: true,
    });
    expect(samplingVisibility(caps({ supports_frequency_penalty: false }), false)).toMatchObject({
      showFrequencyPenalty: false,
    });
  });

  it('locks temperature/top_p while Anthropic thinking is active', () => {
    expect(samplingVisibility(caps(), true)).toEqual({
      showTemperature: false,
      showTopP: false,
      showFrequencyPenalty: true,
      showPresencePenalty: true,
    });
  });
});

// --- structuredErrorDetail ---------------------------------------------------

describe('structuredErrorDetail', () => {
  it('extracts the Pydantic-style detail from an ApiError-shaped failure', () => {
    const detail = {
      type: 'thinking_budget_below_floor',
      msg: 'explicit backend message',
      ctx: { floor: 4000, effective_max_tokens: 600 },
    };
    expect(structuredErrorDetail({ data: { detail } })).toEqual(detail);
  });

  it('returns null for every non-structured failure shape', () => {
    expect(structuredErrorDetail(undefined)).toBeNull();
    expect(structuredErrorDetail(new Error('network down'))).toBeNull();
    expect(structuredErrorDetail({ data: 'Internal Server Error' })).toBeNull();
    // FastAPI's plain-string detail (non-structured 4xx)
    expect(structuredErrorDetail({ data: { detail: 'Not found' } })).toBeNull();
    // FastAPI's native RequestValidationError shape is a LIST — not ours
    expect(structuredErrorDetail({ data: { detail: [{ msg: 'field required' }] } })).toBeNull();
  });
});

// --- thinkingBudgetBelowFloor toast copy — real locales ----------------------
//
// The explicit message the admin sees on a rejected save is interpolated with
// {{floor}}/{{maxTokens}} from the backend ctx. Key parity alone does not
// guarantee the placeholders survive translation — pin them in all 6 locales.

describe('thinkingBudgetBelowFloor key resolves against real locales', () => {
  it.each(['en', 'fr', 'de', 'es', 'it', 'zh'])(
    '%s carries the key with both interpolation placeholders',
    async lng => {
      const bundle = (await import(`../../../../../locales/${lng}/translation.json`)).default as {
        settings: {
          admin: { llmConfig: { config: Record<string, string> } };
        };
      };
      const msg = bundle.settings.admin.llmConfig.config.thinkingBudgetBelowFloor;
      expect(typeof msg).toBe('string');
      expect(msg).toContain('{{floor}}');
      expect(msg).toContain('{{maxTokens}}');
    }
  );
});
