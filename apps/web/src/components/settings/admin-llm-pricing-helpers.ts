/**
 * Pure helpers for the LLM admin Pricing form.
 *
 * Extracted from AdminLLMPricingSection.tsx so they can be unit-tested
 * without rendering the React component. The component imports + re-exports
 * these symbols at runtime — keep both files in lock-step.
 */

import type {
  LLMModelKindName,
  LLMProviderName,
  ReasoningBudgetRangePayload,
  ReasoningTemplate,
  ReasoningWidgetName,
  TimeSlotPricePayload,
} from '@/lib/actions/settings-actions';

/** Sentinel slug used in the "Copy reasoning shape from..." selector when
 *  the admin wants to bypass templates and edit the 4 reasoning shape
 *  fields by hand. Sent to the backend as ``reasoning_template = null``
 *  (Custom mode). Mirrors the Python service's ``reasoning_template is None``
 *  branch in ``_resolve_reasoning_block``. */
export const CUSTOM_TEMPLATE_VALUE = '__custom__';

/** Default-empty budget range for new Custom-mode entries. */
export const EMPTY_BUDGET_RANGE: ReasoningBudgetRangePayload = {
  min: 0,
  max: 0,
  off_sentinel: null,
  dynamic_sentinel: null,
};

/** Form data captured by the modal. The reasoning + sampling block is
 *  split into a Template selector (``reasoning_template``) plus a
 *  Custom-mode payload. The submit handler picks one branch based on
 *  ``reasoning_template === CUSTOM_TEMPLATE_VALUE``. */
export interface ModelPricingFormData {
  provider: LLMProviderName;
  model_name: string;
  max_input_tokens: number;
  max_output_tokens: number;
  supports_tools: boolean;
  supports_structured_output: boolean;
  supports_strict_mode: boolean;
  supports_streaming: boolean;
  supports_vision: boolean;
  // Reasoning + sampling — Template selector OR Custom mode.
  reasoning_template: string;
  // Custom-mode fields.
  kind: LLMModelKindName;
  is_reasoning_model: boolean;
  reasoning_widget: ReasoningWidgetName;
  reasoning_enum_values_csv: string;
  reasoning_budget_range: ReasoningBudgetRangePayload;
  reasoning_doc_i18n_key: string;
  supports_temperature: boolean;
  supports_top_p: boolean;
  supports_frequency_penalty: boolean;
  supports_presence_penalty: boolean;
  // Pricing — semantic of the unit prices is given by `pricing_unit`
  // ('per_1m_tokens' for chat/text models, 'per_audio_*' for STT/TTS).
  pricing_unit: 'per_1m_tokens' | 'per_audio_minute' | 'per_audio_hour';
  input_unit_price: string;
  cached_input_unit_price: string | null;
  output_unit_price: string;
  // Time-slot tariff (ADR-223): the toggle drives the editor's visibility;
  // rows are kept in state even while the toggle is off so an accidental
  // toggle does not destroy the admin's typed windows.
  time_slots_enabled: boolean;
  time_slots: TimeSlotFormRow[];
}

/** One editable window row of the time-slot tariff. All fields are input
 *  strings; `''` in cached means "no separate cache billing" (→ null on the
 *  wire), `''` elsewhere means "not filled in yet" (blocks submit). */
export interface TimeSlotFormRow {
  start_utc: string;
  end_utc: string;
  input_unit_price: string;
  cached_input_unit_price: string;
  output_unit_price: string;
}

/** A fresh editor row — hours empty so the admin types both bounds. */
export const EMPTY_TIME_SLOT_ROW: TimeSlotFormRow = {
  start_utc: '',
  end_utc: '',
  input_unit_price: '',
  cached_input_unit_price: '',
  output_unit_price: '',
};

/** Subset of fields persisted on a model row that participate in the
 *  reasoning shape comparison. Matches the backend's 4-field fingerprint
 *  in ``LLMModelService._fingerprint``. */
export interface ReasoningShape {
  is_reasoning_model: boolean;
  reasoning_widget: ReasoningWidgetName;
  reasoning_enum_values: string[] | null;
  reasoning_budget_range: ReasoningBudgetRangePayload | null;
}

/** Parse a comma-separated enum_values input. Empty / whitespace-only
 *  inputs return null so the backend can validate widget cohesion
 *  (widget=enum + null values ⇒ 422). */
export function parseEnumValuesCsv(csv: string): string[] | null {
  const items = csv
    .split(',')
    .map(s => s.trim())
    .filter(Boolean);
  return items.length ? items : null;
}

/** Render an enum_values list back to a CSV input value (with separating
 *  ", " for readability). Inverse of {@link parseEnumValuesCsv} modulo
 *  whitespace normalisation. */
export function formatEnumValuesCsv(values: string[] | null | undefined): string {
  return values ? values.join(', ') : '';
}

/** Compare a template's reasoning shape against an existing model. Used
 *  at edit time to pre-select the matching entry in the "Copy reasoning
 *  shape from..." selector. Compares only the 4 shape fields — kind,
 *  sampling caps and doc_i18n_key are independent. */
export function fingerprintMatches(tpl: ReasoningTemplate, m: ReasoningShape): boolean {
  return (
    tpl.is_reasoning_model === m.is_reasoning_model &&
    tpl.reasoning_widget === m.reasoning_widget &&
    JSON.stringify(tpl.reasoning_enum_values ?? null) ===
      JSON.stringify(m.reasoning_enum_values ?? null) &&
    JSON.stringify(tpl.reasoning_budget_range ?? null) ===
      JSON.stringify(m.reasoning_budget_range ?? null)
  );
}

/** Shape returned by {@link buildReasoningSamplingPayload}. Optional
 *  fields are present in Template mode OR Custom mode but never both;
 *  the backend's ``model_validator`` enforces the XOR. */
export interface ReasoningSamplingPayload {
  kind: LLMModelKindName;
  supports_temperature: boolean;
  supports_top_p: boolean;
  supports_frequency_penalty: boolean;
  supports_presence_penalty: boolean;
  reasoning_doc_i18n_key: string | null;
  reasoning_template?: string | null;
  is_reasoning_model?: boolean;
  reasoning_widget?: ReasoningWidgetName;
  reasoning_enum_values?: string[] | null;
  reasoning_budget_range?: ReasoningBudgetRangePayload | null;
}

/** Build the reasoning + sampling block of the create/update payload from
 *  the form state.
 *
 *  Always-explicit fields (saved per model regardless of template):
 *    - ``kind``, the four ``supports_*`` sampling flags,
 *      ``reasoning_doc_i18n_key``.
 *
 *  Reasoning shape is one of three branches:
 *    - Non-reasoning: force ``widget='none'`` + ``is_reasoning_model=false``.
 *    - Reasoning + Template mode: send ``reasoning_template`` (the backend
 *      copies the 4 shape fields).
 *    - Reasoning + Custom mode: send the 4 explicit shape fields. */
export function buildReasoningSamplingPayload(
  formData: ModelPricingFormData
): ReasoningSamplingPayload {
  const alwaysExplicit: ReasoningSamplingPayload = {
    kind: formData.kind,
    supports_temperature: formData.supports_temperature,
    supports_top_p: formData.supports_top_p,
    supports_frequency_penalty: formData.supports_frequency_penalty,
    supports_presence_penalty: formData.supports_presence_penalty,
    reasoning_doc_i18n_key: formData.reasoning_doc_i18n_key.trim() || null,
  };

  // Non-reasoning model — bypass templates and force widget='none'.
  if (!formData.is_reasoning_model) {
    return {
      ...alwaysExplicit,
      is_reasoning_model: false,
      reasoning_widget: 'none',
      reasoning_enum_values: null,
      reasoning_budget_range: null,
    };
  }

  // Reasoning model — Template mode (default) or Custom mode (advanced).
  if (formData.reasoning_template !== CUSTOM_TEMPLATE_VALUE) {
    return { ...alwaysExplicit, reasoning_template: formData.reasoning_template };
  }

  const widget = formData.reasoning_widget;
  return {
    ...alwaysExplicit,
    is_reasoning_model: true,
    reasoning_widget: widget,
    reasoning_enum_values:
      widget === 'enum' ? parseEnumValuesCsv(formData.reasoning_enum_values_csv) : null,
    reasoning_budget_range:
      widget === 'budget_int' || widget === 'toggle_budget'
        ? formData.reasoning_budget_range
        : null,
  };
}

// ============================================================================
// Time-slot tariffs (ADR-223) — client-side mirror of the backend rules
// (``pricing_time_slots.py``). The server stays authoritative; this mirror
// exists so the admin gets immediate feedback instead of a 422 round-trip.
// ============================================================================

/** Validation verdict for the slot editor; null = rows are submittable. */
export type TimeSlotRowsError = 'incomplete' | 'zero_length' | 'overlap';

const HHMM_RE = /^(?:[01]\d|2[0-3]):[0-5]\d$/;

function hhmmToMinutes(value: string): number {
  const [hours, minutes] = value.split(':');
  return parseInt(hours, 10) * 60 + parseInt(minutes, 10);
}

/** Project a window onto the 1440-minute day as non-wrapping [start,end)
 *  segments — a midnight-wrapping window becomes two. */
function daySegments(startMinute: number, endMinute: number): Array<[number, number]> {
  if (startMinute < endMinute) return [[startMinute, endMinute]];
  return [
    [startMinute, 1440],
    [0, endMinute],
  ];
}

function isBlankOrNegativePrice(value: string): boolean {
  return value.trim() === '' || Number.isNaN(parseFloat(value)) || parseFloat(value) < 0;
}

/** True when a row misses a valid hour or carries a blank/negative price
 *  where one is required. The cached price may be blank (no cache billing). */
function timeSlotRowIncomplete(row: TimeSlotFormRow): boolean {
  return (
    !HHMM_RE.test(row.start_utc) ||
    !HHMM_RE.test(row.end_utc) ||
    isBlankOrNegativePrice(row.input_unit_price) ||
    isBlankOrNegativePrice(row.output_unit_price) ||
    (row.cached_input_unit_price.trim() !== '' && parseFloat(row.cached_input_unit_price) < 0)
  );
}

/** True when any two windows share at least one minute of the day. */
function timeSlotRowsOverlap(rows: TimeSlotFormRow[]): boolean {
  const segmented = rows.map(row =>
    daySegments(hhmmToMinutes(row.start_utc), hhmmToMinutes(row.end_utc))
  );
  for (let index = 0; index < rows.length; index += 1) {
    for (let other = index + 1; other < rows.length; other += 1) {
      for (const [startA, endA] of segmented[index]) {
        for (const [startB, endB] of segmented[other]) {
          if (startA < endB && startB < endA) return true;
        }
      }
    }
  }
  return false;
}

/** Validate editor rows before submit. Mirrors the backend order: shape
 *  first (incomplete), then zero-length windows, then overlap on the
 *  1440-minute circle. */
export function validateTimeSlotRows(rows: TimeSlotFormRow[]): TimeSlotRowsError | null {
  if (rows.length === 0 || rows.some(timeSlotRowIncomplete)) return 'incomplete';
  if (rows.some(row => row.start_utc === row.end_utc)) return 'zero_length';
  return timeSlotRowsOverlap(rows) ? 'overlap' : null;
}

/** Build the `time_slots` wire field from the form state.
 *
 *  Token-billed + toggle on → the mapped rows (blank cached price → null).
 *  Otherwise: `undefined` at create time (flat pricing, field omitted) and
 *  `[]` at update time — the explicit clearing sentinel, because an omitted
 *  field INHERITS the current row's slots on the backend. */
export function buildTimeSlotsPayload(
  formData: ModelPricingFormData,
  mode: 'create' | 'update'
): TimeSlotPricePayload[] | undefined {
  const active = formData.pricing_unit === 'per_1m_tokens' && formData.time_slots_enabled;
  if (!active) return mode === 'create' ? undefined : [];
  return formData.time_slots.map(row => ({
    start_utc: row.start_utc,
    end_utc: row.end_utc,
    input_unit_price: row.input_unit_price,
    cached_input_unit_price: row.cached_input_unit_price.trim() === '' ? null : row.cached_input_unit_price,
    output_unit_price: row.output_unit_price,
  }));
}

/** Map the API's slot list (or null for flat pricing) to editable rows. */
export function slotRowsFromModel(
  slots: TimeSlotPricePayload[] | null | undefined
): TimeSlotFormRow[] {
  return (slots ?? []).map(slot => ({
    start_utc: slot.start_utc,
    end_utc: slot.end_utc,
    input_unit_price: slot.input_unit_price,
    cached_input_unit_price: slot.cached_input_unit_price ?? '',
    output_unit_price: slot.output_unit_price,
  }));
}

/** Format a `Date.getTimezoneOffset()` value (minutes WEST of UTC) as a
 *  "UTC±HH:MM" label, so the admin can situate the UTC windows relative to
 *  their own clock. CEST (-120) → "UTC+02:00". */
export function utcOffsetLabel(offsetMinutes: number): string {
  const sign = offsetMinutes <= 0 ? '+' : '-';
  const absolute = Math.abs(offsetMinutes);
  const hours = String(Math.floor(absolute / 60)).padStart(2, '0');
  const minutes = String(absolute % 60).padStart(2, '0');
  return `UTC${sign}${hours}:${minutes}`;
}
