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
  buildReasoningSamplingPayload,
  buildTimeSlotsPayload,
  formatEnumValuesCsv,
  parseEnumValuesCsv,
  slotRowsFromModel,
  utcOffsetLabel,
  validateTimeSlotRows,
  type ModelPricingFormData,
  type TimeSlotFormRow,
} from '@/components/settings/admin-llm-pricing-helpers';

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
  kind: 'chat',
  is_reasoning_model: false,
  reasoning_enum_values_csv: '',
  reasoning_doc_i18n_key: '',
  supports_temperature: true,
  supports_top_p: true,
  supports_frequency_penalty: true,
  supports_presence_penalty: true,
  pricing_unit: 'per_1m_tokens',
  input_unit_price: '1.0',
  cached_input_unit_price: null,
  output_unit_price: '3.0',
  time_slots_enabled: false,
  time_slots: [],
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

describe('buildReasoningSamplingPayload — non-reasoning branch', () => {
  it('asks for clearing rather than sending an empty ladder', () => {
    const payload = buildReasoningSamplingPayload({
      ...baseFormData,
      is_reasoning_model: false,
      // A ladder typed before the toggle was turned off must not survive it.
      reasoning_enum_values_csv: 'low, high',
    });
    expect(payload.is_reasoning_model).toBe(false);
    expect(payload.clear_reasoning_enum_values).toBe(true);
    expect(payload.reasoning_enum_values).toBeUndefined();
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

  it('trims whitespace and converts an empty doc_i18n_key to null', () => {
    const payload = buildReasoningSamplingPayload({
      ...baseFormData,
      reasoning_doc_i18n_key: '   ',
    });
    expect(payload.reasoning_doc_i18n_key).toBeNull();
  });
});

describe('buildReasoningSamplingPayload — the ladder', () => {
  it('sends the depths left ticked', () => {
    const payload = buildReasoningSamplingPayload({
      ...baseFormData,
      is_reasoning_model: true,
      reasoning_enum_values_csv: 'low, high',
    });
    expect(payload.is_reasoning_model).toBe(true);
    expect(payload.reasoning_enum_values).toEqual(['low', 'high']);
    expect(payload.clear_reasoning_enum_values).toBeUndefined();
  });

  it('asks for CLEARING when every depth is kept, never a bare null', () => {
    // A null is dropped in transit: the update path builds its change-set
    // with exclude_none, so re-ticking everything would leave the previous
    // restriction in place — a ladder that cannot be widened back.
    const payload = buildReasoningSamplingPayload({
      ...baseFormData,
      is_reasoning_model: true,
      reasoning_enum_values_csv: '',
    });
    expect(payload.clear_reasoning_enum_values).toBe(true);
    expect(payload.reasoning_enum_values).toBeUndefined();
  });

  it('a non-reasoning model clears the ladder too', () => {
    const payload = buildReasoningSamplingPayload({
      ...baseFormData,
      is_reasoning_model: false,
      reasoning_enum_values_csv: 'low, high',
    });
    expect(payload.is_reasoning_model).toBe(false);
    expect(payload.clear_reasoning_enum_values).toBe(true);
  });

  it('always-explicit fields pass through', () => {
    const payload = buildReasoningSamplingPayload({
      ...baseFormData,
      is_reasoning_model: true,
      reasoning_enum_values_csv: 'high',
      kind: 'chat',
      supports_temperature: false,
      reasoning_doc_i18n_key: '  openai_effort  ',
    });
    expect(payload.kind).toBe('chat');
    expect(payload.supports_temperature).toBe(false);
    expect(payload.reasoning_doc_i18n_key).toBe('openai_effort');
  });
});

// ============================================================================
// Time-slot tariffs (ADR-223) — client-side mirror of the backend rules.
// Server stays authoritative; these helpers exist for immediate feedback.
// ============================================================================

const PEAK_ROW: TimeSlotFormRow = {
  start_utc: '01:00',
  end_utc: '04:00',
  input_unit_price: '0.44',
  cached_input_unit_price: '0.014',
  output_unit_price: '1.32',
};
const SECOND_ROW: TimeSlotFormRow = { ...PEAK_ROW, start_utc: '06:00', end_utc: '10:00' };

function slotsForm(over: Partial<ModelPricingFormData> = {}): ModelPricingFormData {
  return {
    ...baseFormData,
    pricing_unit: 'per_1m_tokens',
    time_slots_enabled: true,
    time_slots: [PEAK_ROW, SECOND_ROW],
    ...over,
  };
}

describe('validateTimeSlotRows', () => {
  it('accepts the DeepSeek-shaped two-window tariff', () => {
    expect(validateTimeSlotRows([PEAK_ROW, SECOND_ROW])).toBeNull();
  });

  it('accepts adjacent and midnight-wrapping windows', () => {
    expect(
      validateTimeSlotRows([
        { ...PEAK_ROW, start_utc: '22:00', end_utc: '02:00' },
        { ...PEAK_ROW, start_utc: '02:00', end_utc: '05:00' },
      ])
    ).toBeNull();
  });

  it('flags an empty slot list', () => {
    expect(validateTimeSlotRows([])).toBe('incomplete');
  });

  it('flags missing hours or prices as incomplete', () => {
    expect(validateTimeSlotRows([{ ...PEAK_ROW, start_utc: '' }])).toBe('incomplete');
    expect(validateTimeSlotRows([{ ...PEAK_ROW, input_unit_price: '' }])).toBe('incomplete');
    expect(validateTimeSlotRows([{ ...PEAK_ROW, output_unit_price: '' }])).toBe('incomplete');
  });

  it('treats a blank cached price as complete (caching unsupported)', () => {
    expect(validateTimeSlotRows([{ ...PEAK_ROW, cached_input_unit_price: '' }])).toBeNull();
  });

  it('flags negative prices', () => {
    expect(validateTimeSlotRows([{ ...PEAK_ROW, input_unit_price: '-1' }])).toBe('incomplete');
  });

  it('flags zero-length windows', () => {
    expect(validateTimeSlotRows([{ ...PEAK_ROW, end_utc: '01:00' }])).toBe('zero_length');
  });

  it('flags overlaps, including across midnight', () => {
    expect(
      validateTimeSlotRows([PEAK_ROW, { ...PEAK_ROW, start_utc: '03:00', end_utc: '05:00' }])
    ).toBe('overlap');
    expect(
      validateTimeSlotRows([
        { ...PEAK_ROW, start_utc: '22:00', end_utc: '02:00' },
        { ...PEAK_ROW, start_utc: '01:00', end_utc: '03:00' },
      ])
    ).toBe('overlap');
  });
});

describe('buildTimeSlotsPayload', () => {
  it('maps enabled rows to the wire payload with blank cached prices as null', () => {
    const payload = buildTimeSlotsPayload(
      slotsForm({ time_slots: [{ ...PEAK_ROW, cached_input_unit_price: '' }] }),
      'update'
    );
    expect(payload).toEqual([
      {
        start_utc: '01:00',
        end_utc: '04:00',
        input_unit_price: '0.44',
        cached_input_unit_price: null,
        output_unit_price: '1.32',
      },
    ]);
  });

  it('omits the field at create time when disabled (flat pricing)', () => {
    expect(
      buildTimeSlotsPayload(slotsForm({ time_slots_enabled: false }), 'create')
    ).toBeUndefined();
  });

  it('sends the [] clearing sentinel at update time when disabled', () => {
    expect(buildTimeSlotsPayload(slotsForm({ time_slots_enabled: false }), 'update')).toEqual([]);
  });

  it('never sends slots for an audio-billed unit', () => {
    expect(
      buildTimeSlotsPayload(slotsForm({ pricing_unit: 'per_audio_hour' }), 'create')
    ).toBeUndefined();
    expect(buildTimeSlotsPayload(slotsForm({ pricing_unit: 'per_audio_hour' }), 'update')).toEqual(
      []
    );
  });
});

describe('slotRowsFromModel', () => {
  it('round-trips the API response into editable rows', () => {
    const rows = slotRowsFromModel([
      {
        start_utc: '01:00',
        end_utc: '04:00',
        input_unit_price: '0.44',
        cached_input_unit_price: null,
        output_unit_price: '1.32',
      },
    ]);
    expect(rows).toEqual([{ ...PEAK_ROW, cached_input_unit_price: '' }]);
  });

  it('maps a flat-priced model to no rows', () => {
    expect(slotRowsFromModel(null)).toEqual([]);
    expect(slotRowsFromModel(undefined)).toEqual([]);
  });
});

describe('utcOffsetLabel', () => {
  it('formats positive, negative and zero offsets', () => {
    // getTimezoneOffset returns minutes WEST of UTC (CEST = -120).
    expect(utcOffsetLabel(-120)).toBe('UTC+02:00');
    expect(utcOffsetLabel(300)).toBe('UTC-05:00');
    expect(utcOffsetLabel(0)).toBe('UTC+00:00');
    expect(utcOffsetLabel(-330)).toBe('UTC+05:30');
  });
});
