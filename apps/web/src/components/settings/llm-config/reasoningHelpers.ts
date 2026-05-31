/**
 * Shape compatibility helpers for `reasoning_effort` vs a model's reasoning widget.
 *
 * Frontend twin of the backend `domains.llm_config.reasoning_validation`
 * (`validate_reasoning_effort` / `reasoning_effort_matches_widget`). The shape
 * of a `reasoning_effort` value is dispatched on the model's `reasoning_widget`:
 *   - 'none'          → must be null
 *   - 'enum'          → { effort: <one of reasoning_enum_values> }
 *   - 'budget_int'    → { budget: <int> }
 *   - 'toggle_budget' → { enabled: <bool>, budget?: <int|null> }
 *
 * Used by the admin LLM config dialog to keep `form.reasoning_effort` coherent
 * with the currently selected model: when the model (or provider) changes, a
 * value whose shape no longer fits the new model must not be carried over — it
 * would be persisted as-is and crash the typed reasoning builder at runtime.
 */
import type {
  ModelCapabilities,
  ReasoningEffortValue,
  ReasoningWidgetType,
} from '@/types/llm-config';

/** Discriminate the *shape* of a reasoning_effort value into the widget type it
 * belongs to. `null` (no override) maps to 'none'. */
export function reasoningEffortShape(value: ReasoningEffortValue | undefined): ReasoningWidgetType {
  if (value == null) return 'none';
  if ('effort' in value) return 'enum';
  if ('enabled' in value) return 'toggle_budget';
  if ('budget' in value) return 'budget_int';
  return 'none';
}

/** True when `value` is a valid reasoning_effort for `caps`: correct shape for
 * the model's `reasoning_widget` and, for the 'enum' widget, an allowed value.
 * `null` is valid only for the 'none' widget. When `caps` is undefined (e.g. a
 * dynamically discovered model not in the static catalogue) the model is treated
 * as non-reasoning ('none'), so only `null` is considered valid. */
export function reasoningEffortMatchesModel(
  value: ReasoningEffortValue | undefined,
  caps: ModelCapabilities | undefined
): boolean {
  const widget: ReasoningWidgetType = caps?.reasoning_widget ?? 'none';
  if (widget === 'none') return value == null;
  if (value == null) return false;
  if (reasoningEffortShape(value) !== widget) return false;
  if (widget === 'enum') {
    const allowed = caps?.reasoning_enum_values ?? [];
    return 'effort' in value && allowed.includes(value.effort);
  }
  // 'budget_int' / 'toggle_budget': shape matched; numeric range is validated
  // by the widget UI and (authoritatively) by the backend.
  return true;
}

/** Return `current` if it is valid for `caps`, otherwise `null` (= no override,
 * the model's intrinsic default applies). Call this whenever the selected model
 * or provider changes so a stale reasoning_effort can never travel across the
 * switch. */
export function coerceReasoningEffortForModel(
  current: ReasoningEffortValue | undefined,
  caps: ModelCapabilities | undefined
): ReasoningEffortValue {
  return reasoningEffortMatchesModel(current, caps) ? (current ?? null) : null;
}
