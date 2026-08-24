/**
 * Pure unit tests for the reasoning coherence helpers the admin dialog uses to
 * keep `form.reasoning_effort` valid for the selected model. Frontend twin of
 * ``apps/api/tests/unit/domains/llm_config/test_reasoning_validation.py``.
 *
 * What this file stopped testing (ADR-245): a cross-product of four stored
 * SHAPES against four widget types. There is one shape now. What can still be
 * wrong is a level the model does not offer, a budget a level-based family
 * cannot express, or one outside the published range — and the regression that
 * motivated the original file is still here, generalised: a value that fits the
 * previous model must not travel to a model that refuses it (prod 2026-08-14,
 * 422 on every save attempt).
 */
import { describe, expect, it } from 'vitest';

import type { ModelCapabilities, ReasoningEffortValue } from '@/types/llm-config';
import {
  EMPTY_INTENT,
  coerceReasoningEffortForModel,
  formatReasoningValue,
  modelReasons,
  reasoningEffortMatchesModel,
  reasoningIsActive,
  withBudget,
  withExclude,
  withLevel,
} from '../reasoningHelpers';

/** Minimal caps stub: the helpers read only the resolved reasoning profile. */
function caps(partial: Partial<ModelCapabilities>): ModelCapabilities {
  return {
    reasoning_family: 'none',
    reasoning_levels: [],
    reasoning_can_disable: true,
    reasoning_supports_budget: false,
    reasoning_supports_exclude: false,
    reasoning_budget_range: null,
    ...partial,
  } as ModelCapabilities;
}

const LADDER = caps({
  reasoning_family: 'openai',
  reasoning_levels: ['none', 'low', 'medium', 'high', 'xhigh'],
});

const BUDGETED = caps({
  reasoning_family: 'anthropic_budget',
  reasoning_levels: ['none', 'low', 'medium', 'high'],
  reasoning_supports_budget: true,
  reasoning_budget_range: { min: 1024, max: 128000 },
});

describe('withLevel / withBudget / withExclude', () => {
  it('never mutate the intent they are given', () => {
    const before = { ...EMPTY_INTENT };
    withLevel(EMPTY_INTENT, 'high');
    withBudget(EMPTY_INTENT, 8192);
    withExclude(EMPTY_INTENT, true);
    expect(EMPTY_INTENT).toEqual(before);
  });

  it('change one field and keep the others', () => {
    const intent = withExclude(withBudget(withLevel(EMPTY_INTENT, 'high'), 8192), true);
    expect(intent).toEqual({ level: 'high', budget_tokens: 8192, exclude_from_output: true });
  });
});

describe('modelReasons', () => {
  it('is false for a model with an empty ladder, and for an unknown one', () => {
    expect(modelReasons(caps({}))).toBe(false);
    expect(modelReasons(undefined)).toBe(false);
    expect(modelReasons(LADDER)).toBe(true);
  });
});

describe('reasoningEffortMatchesModel', () => {
  it('null is valid for every model, reasoning or not', () => {
    expect(reasoningEffortMatchesModel(null, caps({}))).toBe(true);
    expect(reasoningEffortMatchesModel(undefined, LADDER)).toBe(true);
    expect(reasoningEffortMatchesModel(null, undefined)).toBe(true);
  });

  it('refuses any intent on a model that does not reason', () => {
    expect(reasoningEffortMatchesModel(withLevel(EMPTY_INTENT, 'low'), caps({}))).toBe(false);
  });

  it('accepts a level on the ladder and refuses one that is off it', () => {
    expect(reasoningEffortMatchesModel(withLevel(EMPTY_INTENT, 'high'), LADDER)).toBe(true);
    expect(reasoningEffortMatchesModel(withLevel(EMPTY_INTENT, 'minimal'), LADDER)).toBe(false);
  });

  it('always accepts provider_default on a reasoning model', () => {
    expect(reasoningEffortMatchesModel(EMPTY_INTENT, LADDER)).toBe(true);
  });

  it('refuses a budget the family cannot express', () => {
    expect(reasoningEffortMatchesModel(withBudget(EMPTY_INTENT, 8192), LADDER)).toBe(false);
    expect(reasoningEffortMatchesModel(withBudget(EMPTY_INTENT, 8192), BUDGETED)).toBe(true);
  });

  it('refuses a budget outside the published range', () => {
    expect(reasoningEffortMatchesModel(withBudget(EMPTY_INTENT, 1023), BUDGETED)).toBe(false);
    expect(reasoningEffortMatchesModel(withBudget(EMPTY_INTENT, 128001), BUDGETED)).toBe(false);
    expect(reasoningEffortMatchesModel(withBudget(EMPTY_INTENT, 1024), BUDGETED)).toBe(true);
  });

  it('refuses exclude_from_output where it would never reach the provider', () => {
    expect(reasoningEffortMatchesModel(withExclude(EMPTY_INTENT, true), LADDER)).toBe(false);
    const gemini = caps({
      reasoning_family: 'gemini_level',
      reasoning_levels: ['low', 'medium', 'high'],
      reasoning_supports_exclude: true,
    });
    expect(reasoningEffortMatchesModel(withExclude(EMPTY_INTENT, true), gemini)).toBe(true);
  });

  it('proves nothing for an unknown model, so keeps nothing', () => {
    expect(reasoningEffortMatchesModel(withLevel(EMPTY_INTENT, 'low'), undefined)).toBe(false);
  });
});

describe('coerceReasoningEffortForModel', () => {
  it('keeps a value the new model accepts', () => {
    const v: ReasoningEffortValue = withBudget(withLevel(EMPTY_INTENT, 'high'), 4096);
    expect(coerceReasoningEffortForModel(v, BUDGETED)).toEqual(v);
  });

  it('drops a level the new model does not offer (the production regression)', () => {
    expect(coerceReasoningEffortForModel(withLevel(EMPTY_INTENT, 'xhigh'), BUDGETED)).toBeNull();
  });

  it('drops a budget the new family cannot express', () => {
    expect(coerceReasoningEffortForModel(withBudget(EMPTY_INTENT, 4096), LADDER)).toBeNull();
  });

  it('drops to null when the new model does not reason at all', () => {
    expect(coerceReasoningEffortForModel(withLevel(EMPTY_INTENT, 'low'), caps({}))).toBeNull();
  });

  it('drops to null when the new model is unknown', () => {
    expect(coerceReasoningEffortForModel(withLevel(EMPTY_INTENT, 'low'), undefined)).toBeNull();
  });
});

describe('reasoningIsActive', () => {
  it('is false for absent, none, and a bare provider_default', () => {
    expect(reasoningIsActive(null)).toBe(false);
    expect(reasoningIsActive(undefined)).toBe(false);
    expect(reasoningIsActive(withLevel(EMPTY_INTENT, 'none'))).toBe(false);
    expect(reasoningIsActive(EMPTY_INTENT)).toBe(false);
  });

  it('is true for any depth, and for a budget asked without a depth', () => {
    expect(reasoningIsActive(withLevel(EMPTY_INTENT, 'minimal'))).toBe(true);
    expect(reasoningIsActive(withLevel(EMPTY_INTENT, 'max'))).toBe(true);
    expect(reasoningIsActive(withBudget(EMPTY_INTENT, 8192))).toBe(true);
  });

  it('is false for an explicit zero budget with no depth', () => {
    expect(reasoningIsActive(withBudget(EMPTY_INTENT, 0))).toBe(false);
  });
});

describe('formatReasoningValue', () => {
  it('renders the tile badge without inventing a value', () => {
    expect(formatReasoningValue(null)).toBe('-');
    expect(formatReasoningValue(EMPTY_INTENT)).toBe('auto');
    expect(formatReasoningValue(withLevel(EMPTY_INTENT, 'high'))).toBe('high');
    expect(formatReasoningValue(withBudget(EMPTY_INTENT, 8192))).toBe('8192t');
    expect(formatReasoningValue(withBudget(withLevel(EMPTY_INTENT, 'low'), 2048))).toBe('low/2048t');
  });
});
