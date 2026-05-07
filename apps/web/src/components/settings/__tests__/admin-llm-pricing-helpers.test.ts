/**
 * Pure unit tests for the LLM admin Pricing form helpers.
 *
 * These verify the Template/Custom XOR construction logic, the CSV
 * round-trip, and the fingerprint comparison used at edit time. They
 * mirror the backend's
 * ``apps/api/tests/unit/domains/llm/test_schemas_reasoning.py`` and
 * ``test_service_helpers.py`` for cross-stack consistency.
 */

import { describe, it, expect } from 'vitest';

import {
  CUSTOM_TEMPLATE_VALUE,
  EMPTY_BUDGET_RANGE,
  buildReasoningSamplingPayload,
  fingerprintMatches,
  formatEnumValuesCsv,
  parseEnumValuesCsv,
  type ModelPricingFormData,
} from '@/components/settings/admin-llm-pricing-helpers';
import type { ReasoningTemplate } from '@/lib/actions/settings-actions';

const baseFormData: ModelPricingFormData = {
  provider: 'openai',
  model_name: 'test-model',
  max_input_tokens: 1000,
  max_output_tokens: 200,
  supports_tools: true,
  supports_structured_output: true,
  supports_strict_mode: false,
  supports_streaming: true,
  supports_vision: false,
  reasoning_template: CUSTOM_TEMPLATE_VALUE,
  kind: 'chat',
  is_reasoning_model: false,
  reasoning_widget: 'none',
  reasoning_enum_values_csv: '',
  reasoning_budget_range: EMPTY_BUDGET_RANGE,
  reasoning_doc_i18n_key: '',
  supports_temperature: true,
  supports_top_p: true,
  supports_frequency_penalty: true,
  supports_presence_penalty: true,
  input_price_per_1m_tokens: '1.0',
  cached_input_price_per_1m_tokens: null,
  output_price_per_1m_tokens: '3.0',
};

describe('parseEnumValuesCsv', () => {
  it('splits a comma-separated list and trims whitespace', () => {
    expect(parseEnumValuesCsv('low, medium, high')).toEqual(['low', 'medium', 'high']);
  });

  it('returns null for empty input', () => {
    expect(parseEnumValuesCsv('')).toBeNull();
  });

  it('returns null for whitespace-only input', () => {
    expect(parseEnumValuesCsv('   ')).toBeNull();
    expect(parseEnumValuesCsv(', , ,')).toBeNull();
  });

  it('drops empty fragments (trailing commas, doubles)', () => {
    expect(parseEnumValuesCsv('low,,medium,')).toEqual(['low', 'medium']);
  });

  it('preserves order', () => {
    expect(parseEnumValuesCsv('high,low,medium')).toEqual(['high', 'low', 'medium']);
  });
});

describe('formatEnumValuesCsv', () => {
  it('joins with ", " for readability', () => {
    expect(formatEnumValuesCsv(['low', 'medium', 'high'])).toBe('low, medium, high');
  });

  it('returns empty string for null', () => {
    expect(formatEnumValuesCsv(null)).toBe('');
  });

  it('returns empty string for undefined', () => {
    expect(formatEnumValuesCsv(undefined)).toBe('');
  });

  it('round-trips with parseEnumValuesCsv (order preserved)', () => {
    const original = ['minimal', 'low', 'medium', 'high'];
    expect(parseEnumValuesCsv(formatEnumValuesCsv(original))).toEqual(original);
  });
});

describe('fingerprintMatches', () => {
  const enumTemplate: ReasoningTemplate = {
    template_model_name: 'gpt-5',
    representative_provider: 'openai',
    description: 'enum [minimal/low/medium/high]',
    matching_count: 5,
    is_reasoning_model: true,
    reasoning_widget: 'enum',
    reasoning_enum_values: ['minimal', 'low', 'medium', 'high'],
    reasoning_budget_range: null,
  };

  it('matches identical reasoning shape', () => {
    expect(
      fingerprintMatches(enumTemplate, {
        is_reasoning_model: true,
        reasoning_widget: 'enum',
        reasoning_enum_values: ['minimal', 'low', 'medium', 'high'],
        reasoning_budget_range: null,
      })
    ).toBe(true);
  });

  it('rejects different is_reasoning_model', () => {
    expect(
      fingerprintMatches(enumTemplate, {
        is_reasoning_model: false,
        reasoning_widget: 'enum',
        reasoning_enum_values: ['minimal', 'low', 'medium', 'high'],
        reasoning_budget_range: null,
      })
    ).toBe(false);
  });

  it('rejects different widget', () => {
    expect(
      fingerprintMatches(enumTemplate, {
        is_reasoning_model: true,
        reasoning_widget: 'budget_int',
        reasoning_enum_values: ['minimal', 'low', 'medium', 'high'],
        reasoning_budget_range: null,
      })
    ).toBe(false);
  });

  it('rejects different enum_values', () => {
    expect(
      fingerprintMatches(enumTemplate, {
        is_reasoning_model: true,
        reasoning_widget: 'enum',
        reasoning_enum_values: ['low', 'high'],
        reasoning_budget_range: null,
      })
    ).toBe(false);
  });

  it('rejects different enum_values order (lists are positional)', () => {
    expect(
      fingerprintMatches(enumTemplate, {
        is_reasoning_model: true,
        reasoning_widget: 'enum',
        reasoning_enum_values: ['high', 'medium', 'low', 'minimal'],
        reasoning_budget_range: null,
      })
    ).toBe(false);
  });

  it('matches identical budget_range', () => {
    const budgetTemplate: ReasoningTemplate = {
      template_model_name: 'gemini-2.5-pro',
      representative_provider: 'gemini',
      description: 'budget 128..32768',
      matching_count: 1,
      is_reasoning_model: true,
      reasoning_widget: 'budget_int',
      reasoning_enum_values: null,
      reasoning_budget_range: { min: 128, max: 32768 },
    };
    expect(
      fingerprintMatches(budgetTemplate, {
        is_reasoning_model: true,
        reasoning_widget: 'budget_int',
        reasoning_enum_values: null,
        reasoning_budget_range: { min: 128, max: 32768 },
      })
    ).toBe(true);
  });

  it('rejects different budget_range', () => {
    const budgetTemplate: ReasoningTemplate = {
      template_model_name: 'gemini-2.5-pro',
      representative_provider: 'gemini',
      description: 'budget 128..32768',
      matching_count: 1,
      is_reasoning_model: true,
      reasoning_widget: 'budget_int',
      reasoning_enum_values: null,
      reasoning_budget_range: { min: 128, max: 32768 },
    };
    expect(
      fingerprintMatches(budgetTemplate, {
        is_reasoning_model: true,
        reasoning_widget: 'budget_int',
        reasoning_enum_values: null,
        reasoning_budget_range: { min: 0, max: 1024 },
      })
    ).toBe(false);
  });

  it('treats null and undefined enum_values as equal (both ⇒ no list)', () => {
    const noEnumTemplate: ReasoningTemplate = {
      template_model_name: 'no-reasoning',
      representative_provider: 'openai',
      description: 'no reasoning',
      matching_count: 55,
      is_reasoning_model: false,
      reasoning_widget: 'none',
      reasoning_enum_values: null,
      reasoning_budget_range: null,
    };
    expect(
      fingerprintMatches(noEnumTemplate, {
        is_reasoning_model: false,
        reasoning_widget: 'none',
        reasoning_enum_values: null,
        reasoning_budget_range: null,
      })
    ).toBe(true);
  });
});

describe('buildReasoningSamplingPayload — non-reasoning branch', () => {
  it('forces widget=none and clears template when is_reasoning_model=false', () => {
    const payload = buildReasoningSamplingPayload({
      ...baseFormData,
      is_reasoning_model: false,
      // Even if a template was previously selected, the non-reasoning branch
      // takes priority and bypasses it.
      reasoning_template: 'gpt-5',
    });
    expect(payload.is_reasoning_model).toBe(false);
    expect(payload.reasoning_widget).toBe('none');
    expect(payload.reasoning_enum_values).toBeNull();
    expect(payload.reasoning_budget_range).toBeNull();
    expect(payload.reasoning_template).toBeUndefined();
  });

  it('always-explicit fields pass through (kind + sampling caps + doc_i18n_key)', () => {
    const payload = buildReasoningSamplingPayload({
      ...baseFormData,
      is_reasoning_model: false,
      kind: 'image',
      supports_temperature: false,
      supports_top_p: false,
      supports_frequency_penalty: false,
      supports_presence_penalty: false,
      reasoning_doc_i18n_key: 'custom_key',
    });
    expect(payload.kind).toBe('image');
    expect(payload.supports_temperature).toBe(false);
    expect(payload.supports_top_p).toBe(false);
    expect(payload.supports_frequency_penalty).toBe(false);
    expect(payload.supports_presence_penalty).toBe(false);
    expect(payload.reasoning_doc_i18n_key).toBe('custom_key');
  });

  it('trims whitespace and converts empty doc_i18n_key to null', () => {
    const payload = buildReasoningSamplingPayload({
      ...baseFormData,
      reasoning_doc_i18n_key: '   ',
    });
    expect(payload.reasoning_doc_i18n_key).toBeNull();
  });
});

describe('buildReasoningSamplingPayload — Template mode', () => {
  it('passes the template name and omits explicit reasoning shape fields', () => {
    const payload = buildReasoningSamplingPayload({
      ...baseFormData,
      is_reasoning_model: true,
      reasoning_template: 'gpt-5',
      // These should NOT leak into the payload (XOR enforced server-side).
      reasoning_widget: 'enum',
      reasoning_enum_values_csv: 'this-should-be-ignored',
    });
    expect(payload.reasoning_template).toBe('gpt-5');
    expect(payload.is_reasoning_model).toBeUndefined();
    expect(payload.reasoning_widget).toBeUndefined();
    expect(payload.reasoning_enum_values).toBeUndefined();
    expect(payload.reasoning_budget_range).toBeUndefined();
  });

  it('preserves the always-explicit fields alongside the template', () => {
    const payload = buildReasoningSamplingPayload({
      ...baseFormData,
      is_reasoning_model: true,
      reasoning_template: 'gpt-5',
      kind: 'chat',
      supports_temperature: false,
      supports_top_p: false,
      supports_frequency_penalty: false,
      supports_presence_penalty: false,
    });
    expect(payload.reasoning_template).toBe('gpt-5');
    expect(payload.kind).toBe('chat');
    expect(payload.supports_temperature).toBe(false);
    expect(payload.supports_top_p).toBe(false);
  });
});

describe('buildReasoningSamplingPayload — Custom mode', () => {
  it('widget=enum sends parsed enum_values and null budget_range', () => {
    const payload = buildReasoningSamplingPayload({
      ...baseFormData,
      is_reasoning_model: true,
      reasoning_template: CUSTOM_TEMPLATE_VALUE,
      reasoning_widget: 'enum',
      reasoning_enum_values_csv: 'low, medium, high',
    });
    expect(payload.reasoning_template).toBeUndefined();
    expect(payload.is_reasoning_model).toBe(true);
    expect(payload.reasoning_widget).toBe('enum');
    expect(payload.reasoning_enum_values).toEqual(['low', 'medium', 'high']);
    expect(payload.reasoning_budget_range).toBeNull();
  });

  it('widget=budget_int sends budget_range and null enum_values', () => {
    const payload = buildReasoningSamplingPayload({
      ...baseFormData,
      is_reasoning_model: true,
      reasoning_template: CUSTOM_TEMPLATE_VALUE,
      reasoning_widget: 'budget_int',
      reasoning_budget_range: { min: 0, max: 32768, off_sentinel: 0, dynamic_sentinel: -1 },
    });
    expect(payload.reasoning_widget).toBe('budget_int');
    expect(payload.reasoning_enum_values).toBeNull();
    expect(payload.reasoning_budget_range).toEqual({
      min: 0,
      max: 32768,
      off_sentinel: 0,
      dynamic_sentinel: -1,
    });
  });

  it('widget=toggle_budget sends budget_range and null enum_values', () => {
    const payload = buildReasoningSamplingPayload({
      ...baseFormData,
      is_reasoning_model: true,
      reasoning_template: CUSTOM_TEMPLATE_VALUE,
      reasoning_widget: 'toggle_budget',
      reasoning_budget_range: { min: 0, max: 38912, off_sentinel: null, dynamic_sentinel: null },
    });
    expect(payload.reasoning_widget).toBe('toggle_budget');
    expect(payload.reasoning_enum_values).toBeNull();
    expect(payload.reasoning_budget_range).toEqual({
      min: 0,
      max: 38912,
      off_sentinel: null,
      dynamic_sentinel: null,
    });
  });

  it('widget=none zeros out both enum_values and budget_range', () => {
    const payload = buildReasoningSamplingPayload({
      ...baseFormData,
      is_reasoning_model: true,
      reasoning_template: CUSTOM_TEMPLATE_VALUE,
      reasoning_widget: 'none',
      reasoning_enum_values_csv: 'should-be-discarded',
    });
    expect(payload.reasoning_widget).toBe('none');
    expect(payload.reasoning_enum_values).toBeNull();
    expect(payload.reasoning_budget_range).toBeNull();
  });

  it('always-explicit fields pass through in Custom mode too', () => {
    const payload = buildReasoningSamplingPayload({
      ...baseFormData,
      is_reasoning_model: true,
      reasoning_template: CUSTOM_TEMPLATE_VALUE,
      reasoning_widget: 'enum',
      reasoning_enum_values_csv: 'low,high',
      kind: 'chat',
      supports_temperature: true,
      supports_top_p: false,
      reasoning_doc_i18n_key: 'family_x',
    });
    expect(payload.kind).toBe('chat');
    expect(payload.supports_temperature).toBe(true);
    expect(payload.supports_top_p).toBe(false);
    expect(payload.reasoning_doc_i18n_key).toBe('family_x');
  });
});
