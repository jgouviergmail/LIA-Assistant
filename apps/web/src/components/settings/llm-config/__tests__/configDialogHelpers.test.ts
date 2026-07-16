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
  formFromConfig,
  isAnthropicThinkingActive,
  isFieldModified,
  modelMatchesRequirements,
  parseProviderConfig,
  resolveTtsProvider,
  samplingVisibility,
  stableStringify,
} from '../configDialogHelpers';
import type { LLMAgentConfig, LLMTypeConfig, ModelCapabilities } from '@/types/llm-config';

function caps(overrides: Partial<ModelCapabilities> = {}): ModelCapabilities {
  return {
    model_id: 'm1',
    kind: 'chat',
    max_output_tokens: 4096,
    supports_tools: true,
    supports_structured_output: true,
    supports_vision: true,
    is_reasoning_model: false,
    reasoning_widget: 'none',
    reasoning_enum_values: null,
    reasoning_budget_range: null,
    reasoning_doc_i18n_key: null,
    effort_values: null,
    supports_temperature: true,
    supports_top_p: true,
    supports_frequency_penalty: true,
    supports_presence_penalty: true,
    cost_input: null,
    cost_output: null,
    ...overrides,
  };
}

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
    effort: null,
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
      { provider: 'openai', model: 'm1', reasoning_effort: { effort: 'high' }, temperature: 1.2 },
      'anthropic'
    );
    expect(next).toEqual({
      provider: 'anthropic',
      model: '',
      reasoning_effort: null,
      temperature: 1.2,
    });
  });

  it('model switch keeps a matching reasoning_effort and drops a stale effort', () => {
    const enumCaps = caps({
      model_id: 'm2',
      reasoning_widget: 'enum',
      reasoning_enum_values: ['low', 'high'],
      effort_values: null,
    });
    const next = formAfterModelChange(
      { provider: 'openai', model: 'm1', reasoning_effort: { effort: 'high' }, effort: 'high' },
      'm2',
      enumCaps
    );
    expect(next.model).toBe('m2');
    expect(next.reasoning_effort).toEqual({ effort: 'high' }); // shape still fits
    expect(next.effort).toBeNull(); // m2 declares no effort_values
  });

  it('model switch keeps the global effort when the new model declares it', () => {
    const effortCaps = caps({ model_id: 'm3', effort_values: ['high', 'medium'] });
    const next = formAfterModelChange(
      { provider: 'anthropic', model: 'm1', effort: 'high' },
      'm3',
      effortCaps
    );
    expect(next.effort).toBe('high');
  });

  it('model switch drops reasoning_effort when the widget no longer fits', () => {
    const next = formAfterModelChange(
      { provider: 'openai', model: 'm1', reasoning_effort: { effort: 'high' } },
      'm2',
      caps({ model_id: 'm2', reasoning_widget: 'none' })
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

  it('JSON-compares reasoning_effort (a fresh but equal object is NOT a diff)', () => {
    const cfg = typeConfig(
      { reasoning_effort: { effort: 'high' } },
      { reasoning_effort: { effort: 'high' } }
    );
    const form = { ...formFromConfig(cfg), reasoning_effort: { effort: 'high' } };
    expect(buildConfigUpdate(cfg, form, {})).toEqual({});
  });

  it('sends reasoning_effort and effort when they differ', () => {
    const cfg = typeConfig();
    const form = { ...formFromConfig(cfg), reasoning_effort: { effort: 'low' }, effort: 'high' };
    expect(buildConfigUpdate(cfg, form, {})).toEqual({
      reasoning_effort: { effort: 'low' },
      effort: 'high',
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

describe('isFieldModified', () => {
  it('compares scalars with !== and reasoning_effort by JSON equality', () => {
    const cfg = typeConfig({}, { temperature: 0.7, reasoning_effort: { effort: 'high' } });
    expect(isFieldModified(cfg, { temperature: 0.7 }, 'temperature')).toBe(false);
    expect(isFieldModified(cfg, { temperature: 1.2 }, 'temperature')).toBe(true);
    expect(isFieldModified(cfg, { reasoning_effort: { effort: 'high' } }, 'reasoning_effort')).toBe(
      false
    );
    expect(isFieldModified(cfg, { reasoning_effort: { effort: 'low' } }, 'reasoning_effort')).toBe(
      true
    );
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
  it('isAnthropicThinkingActive covers the three reasoning shapes', () => {
    expect(isAnthropicThinkingActive('openai', { effort: 'high' })).toBe(false);
    expect(isAnthropicThinkingActive('anthropic', null)).toBe(false);
    expect(isAnthropicThinkingActive('anthropic', { effort: 'off' })).toBe(false);
    expect(isAnthropicThinkingActive('anthropic', { effort: 'high' })).toBe(true);
    expect(isAnthropicThinkingActive('anthropic', { enabled: true })).toBe(true);
    expect(isAnthropicThinkingActive('anthropic', { enabled: false })).toBe(false);
    expect(isAnthropicThinkingActive('anthropic', { budget: 1024 })).toBe(false);
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
