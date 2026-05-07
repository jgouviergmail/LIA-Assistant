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
}

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
