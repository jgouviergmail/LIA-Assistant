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
  TimeSlotPricePayload,
} from '@/lib/actions/settings-actions';

/** Form data captured by the modal. The reasoning identity is written
 *  directly — a toggle and the depths left ticked — with no template mode:
 *  the checkboxes render the model's OWN family ladder, so copying another
 *  model's stored ladder could only remove depths this one accepts. */
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
  // Reasoning + sampling, written directly.
  kind: LLMModelKindName;
  is_reasoning_model: boolean;
  reasoning_enum_values_csv: string;
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

/** Parse the stored ladder narrowing. Empty returns null, and that is the
 *  value the form writes when every depth is kept: "no narrowing" and
 *  "narrowed to everything" mean the same thing to `resolve_reasoning_profile`,
 *  and the empty one survives the family gaining a level.
 *
 *  It is no longer a free-text field — the widget cohesion rule this comment
 *  used to invoke went with the columns it guarded (ADR-245) — but the CSV
 *  stays the form's internal representation, so the parse/format pair is what
 *  the checkbox editor reads and writes. */
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

/** Shape returned by {@link buildReasoningSamplingPayload}. The ladder and
 *  its clearing intent are mutually exclusive — the backend's
 *  ``model_validator`` refuses a payload carrying both. */
export interface ReasoningSamplingPayload {
  kind: LLMModelKindName;
  supports_temperature: boolean;
  supports_top_p: boolean;
  supports_frequency_penalty: boolean;
  supports_presence_penalty: boolean;
  reasoning_doc_i18n_key: string | null;
  is_reasoning_model?: boolean;
  reasoning_enum_values?: string[] | null;
  clear_reasoning_enum_values?: boolean;
}

/** Build the reasoning + sampling block of the create/update payload from
 *  the form state.
 *
 *  Always-explicit fields (saved per model regardless of template):
 *    - ``kind``, the four ``supports_*`` sampling flags,
 *      ``reasoning_doc_i18n_key``.
 *
 *  The reasoning identity is one of three branches:
 *    - Non-reasoning: ``is_reasoning_model=false`` and no ladder.
 *    - Reasoning: send the identity explicitly — the ladder the operator
 *      left ticked, or the clearing intent when nothing is narrowed.
 *
 * The `reasoning_template` mode is gone: the form renders the model's OWN
 * family ladder as checkboxes, so copying another model's stored ladder could
 * only remove depths that this one accepts. */
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

  const ladder = formData.is_reasoning_model
    ? parseEnumValuesCsv(formData.reasoning_enum_values_csv)
    : null;

  // "No narrowing" cannot travel as a null: the update path builds its
  // change-set with exclude_none, so re-ticking every depth would be dropped
  // and the previous restriction would survive. The intent needs its own
  // shape — the same answer the emptied cached price already got.
  if (ladder === null) {
    return {
      ...alwaysExplicit,
      is_reasoning_model: formData.is_reasoning_model,
      clear_reasoning_enum_values: true,
    };
  }

  return { ...alwaysExplicit, is_reasoning_model: true, reasoning_enum_values: ladder };
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
    cached_input_unit_price:
      row.cached_input_unit_price.trim() === '' ? null : row.cached_input_unit_price,
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
