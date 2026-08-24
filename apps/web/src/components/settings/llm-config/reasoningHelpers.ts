/**
 * Coherence helpers for `reasoning_effort` against a model's resolved profile.
 *
 * Frontend twin of the backend `domains.llm_config.reasoning_validation`.
 * There is one stored shape now (ADR-245), so nothing here validates a SHAPE:
 * what can still be wrong is a level the model does not offer, a token budget
 * a level-based family cannot express, or one outside the range the backend
 * enforces.
 *
 * Used by the admin dialog to keep `form.reasoning_effort` coherent with the
 * selected model: when the model or provider changes, a value the new model
 * does not accept must not travel with it — the backend would 422 the save,
 * and before this chokepoint existed it did (prod 2026-08-14).
 */
import type {
  ModelCapabilities,
  ReasoningEffortValue,
  ReasoningIntentValue,
  ReasoningLevel,
} from '@/types/llm-config';

/** The identity intent: asks for nothing, produces no kwarg on any provider. */
export const EMPTY_INTENT: ReasoningIntentValue = {
  level: 'provider_default',
  budget_tokens: null,
  exclude_from_output: false,
};

/** Immutable field setters — the form state is replaced, never mutated. */
export function withLevel(
  intent: ReasoningIntentValue,
  level: ReasoningLevel
): ReasoningIntentValue {
  return { ...intent, level };
}

export function withBudget(
  intent: ReasoningIntentValue,
  budget_tokens: number | null
): ReasoningIntentValue {
  return { ...intent, budget_tokens };
}

export function withExclude(
  intent: ReasoningIntentValue,
  exclude_from_output: boolean
): ReasoningIntentValue {
  return { ...intent, exclude_from_output };
}

/** True when the model reasons at all, i.e. offers at least one level. */
export function modelReasons(caps: ModelCapabilities | undefined): boolean {
  return (caps?.reasoning_levels?.length ?? 0) > 0;
}

/**
 * True when `value` is one this model accepts.
 *
 * `null` (no override) is always valid, for every model — including one that
 * cannot reason. When `caps` is undefined the model is unknown to the
 * catalogue (a free-text entry, a dynamic Ollama tag): nothing can be proven,
 * so only `null` is kept. That is the same proof-over-optimism rule the
 * backend applies when it cannot derive a family.
 */
export function reasoningEffortMatchesModel(
  value: ReasoningEffortValue | undefined,
  caps: ModelCapabilities | undefined
): boolean {
  if (value == null) return true;
  if (!modelReasons(caps)) return false;
  return (
    levelIsOffered(value, caps) && budgetFits(value, caps) && excludeIsExpressible(value, caps)
  );
}

/** The level is on the published ladder — `provider_default` always is. */
function levelIsOffered(value: ReasoningIntentValue, caps: ModelCapabilities | undefined): boolean {
  if (value.level === 'provider_default') return true;
  return (caps?.reasoning_levels ?? []).includes(value.level);
}

/** The budget is expressible by the family, and inside the published range. */
function budgetFits(value: ReasoningIntentValue, caps: ModelCapabilities | undefined): boolean {
  const budget = value.budget_tokens;
  if (budget == null) return true;
  if (!caps?.reasoning_supports_budget) return false;
  const range = caps.reasoning_budget_range;
  return range == null || (budget >= range.min && budget <= range.max);
}

/** The flag actually reaches this family's provider. */
function excludeIsExpressible(
  value: ReasoningIntentValue,
  caps: ModelCapabilities | undefined
): boolean {
  return !value.exclude_from_output || (caps?.reasoning_supports_exclude ?? false);
}

/**
 * Return `current` when this model accepts it, otherwise `null` (= no
 * override, the model's own default applies).
 *
 * Call it when the selected model or provider CHANGES: a value the new model
 * refuses must not travel with the switch.
 */
export function coerceReasoningEffortForModel(
  current: ReasoningEffortValue | undefined,
  caps: ModelCapabilities | undefined
): ReasoningEffortValue {
  return reasoningEffortMatchesModel(current, caps) ? (current ?? null) : null;
}

/**
 * True when the widget would actually SHOW `value` for this model.
 *
 * Deliberately weaker than {@link reasoningEffortMatchesModel}, and the
 * difference is the point. Both answer a question about the same value, but
 * not the same question:
 *
 * - *does this model accept it?* — asked when the model changes, because the
 *   admin never chose the new pairing and cannot be expected to repair it;
 * - *can the admin see it and fix it here?* — asked at save time. A budget
 *   outside the published range is on screen, with its bounds printed under
 *   it, and the backend rejects it with those same bounds in an actionable
 *   message the dialog already surfaces. Nulling it instead threw away the
 *   LEVEL the admin had chosen too, silently, on a save they asked for.
 *
 * What stays unfixable in place is what the widget does not render: an unknown
 * model, a model that does not reason, a level absent from the dropdown, and a
 * flag whose switch is not shown.
 */
export function reasoningEffortIsVisible(
  value: ReasoningEffortValue | undefined,
  caps: ModelCapabilities | undefined
): boolean {
  if (value == null) return true;
  if (!modelReasons(caps)) return false;
  return levelIsOffered(value, caps) && excludeIsExpressible(value, caps);
}

/** True when the intent asks for any reasoning at all — i.e. it is neither
 * absent nor the two ways of saying "do not think". Drives the tile badge and
 * the Anthropic sampling lock. */
export function reasoningIsActive(value: ReasoningEffortValue | undefined): boolean {
  if (value == null) return false;
  if (value.level === 'none') return false;
  if (value.level === 'provider_default') return (value.budget_tokens ?? 0) > 0;
  return true;
}

/** Compact, human-readable rendering for the configuration tile. */
export function formatReasoningValue(value: ReasoningEffortValue | undefined): string {
  if (value == null) return '-';
  const budget = value.budget_tokens;
  if (value.level === 'provider_default') return budget != null ? `${budget}t` : 'auto';
  return budget != null ? `${value.level}/${budget}t` : value.level;
}
