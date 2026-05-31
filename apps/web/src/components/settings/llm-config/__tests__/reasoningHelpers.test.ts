/**
 * Pure unit tests for the reasoning_effort shape-compatibility helpers used by
 * the admin LLM config dialog to keep `form.reasoning_effort` coherent with the
 * selected model. Mirrors the backend
 * ``apps/api/tests/unit/domains/llm_config/test_reasoning_validation.py``
 * (``reasoning_effort_matches_widget``).
 *
 * Regression: the DeepSeek-style ``{ effort: 'off' }`` must be dropped when the
 * selected model uses a Qwen ``toggle_budget`` widget — otherwise it travels
 * through the save and crashes the typed reasoning builder at runtime.
 */
import { describe, expect, it } from 'vitest';

import type { ModelCapabilities, ReasoningEffortValue } from '@/types/llm-config';
import {
  coerceReasoningEffortForModel,
  reasoningEffortMatchesModel,
  reasoningEffortShape,
} from '../reasoningHelpers';

/** Minimal caps stub — the helpers only read `reasoning_widget` / `reasoning_enum_values`. */
function caps(partial: Partial<ModelCapabilities>): ModelCapabilities {
  return { reasoning_widget: 'none', reasoning_enum_values: null, ...partial } as ModelCapabilities;
}

describe('reasoningEffortShape', () => {
  it('discriminates the union by its keys', () => {
    expect(reasoningEffortShape(null)).toBe('none');
    expect(reasoningEffortShape(undefined)).toBe('none');
    expect(reasoningEffortShape({ effort: 'low' })).toBe('enum');
    expect(reasoningEffortShape({ enabled: false })).toBe('toggle_budget');
    expect(reasoningEffortShape({ enabled: true, budget: 8192 })).toBe('toggle_budget');
    expect(reasoningEffortShape({ budget: 8192 })).toBe('budget_int');
  });
});

describe('reasoningEffortMatchesModel', () => {
  it("a 'none' widget accepts only null", () => {
    const c = caps({ reasoning_widget: 'none' });
    expect(reasoningEffortMatchesModel(null, c)).toBe(true);
    expect(reasoningEffortMatchesModel(undefined, c)).toBe(true);
    expect(reasoningEffortMatchesModel({ effort: 'low' }, c)).toBe(false);
    expect(reasoningEffortMatchesModel({ enabled: false }, c)).toBe(false);
  });

  it("an 'enum' widget needs an enum shape with an allowed value", () => {
    const c = caps({ reasoning_widget: 'enum', reasoning_enum_values: ['low', 'medium', 'high'] });
    expect(reasoningEffortMatchesModel({ effort: 'high' }, c)).toBe(true);
    expect(reasoningEffortMatchesModel({ effort: 'off' }, c)).toBe(false); // not allowed
    expect(reasoningEffortMatchesModel({ enabled: false }, c)).toBe(false); // wrong shape
    expect(reasoningEffortMatchesModel(null, c)).toBe(false); // null invalid for a reasoning widget
  });

  it("a 'toggle_budget' widget rejects the enum shape (the production bug)", () => {
    const c = caps({
      reasoning_widget: 'toggle_budget',
      reasoning_budget_range: { min: 0, max: 32768 },
    });
    expect(reasoningEffortMatchesModel({ enabled: false }, c)).toBe(true);
    expect(reasoningEffortMatchesModel({ enabled: true, budget: 8192 }, c)).toBe(true);
    expect(reasoningEffortMatchesModel({ effort: 'off' }, c)).toBe(false);
  });

  it("a 'budget_int' widget needs the bare-budget shape", () => {
    const c = caps({
      reasoning_widget: 'budget_int',
      reasoning_budget_range: { min: 1, max: 24576 },
    });
    expect(reasoningEffortMatchesModel({ budget: 8192 }, c)).toBe(true);
    expect(reasoningEffortMatchesModel({ enabled: true, budget: 8192 }, c)).toBe(false); // toggle shape
    expect(reasoningEffortMatchesModel({ effort: 'low' }, c)).toBe(false);
  });

  it('undefined caps → the model is treated as non-reasoning', () => {
    expect(reasoningEffortMatchesModel(null, undefined)).toBe(true);
    expect(reasoningEffortMatchesModel({ effort: 'low' }, undefined)).toBe(false);
  });
});

describe('coerceReasoningEffortForModel', () => {
  it('keeps a value that is compatible with the new model', () => {
    const c = caps({
      reasoning_widget: 'toggle_budget',
      reasoning_budget_range: { min: 0, max: 32768 },
    });
    const v: ReasoningEffortValue = { enabled: true, budget: 4096 };
    expect(coerceReasoningEffortForModel(v, c)).toEqual(v);
  });

  it('drops an incompatible value to null (DeepSeek enum → Qwen toggle)', () => {
    const c = caps({
      reasoning_widget: 'toggle_budget',
      reasoning_budget_range: { min: 0, max: 32768 },
    });
    expect(coerceReasoningEffortForModel({ effort: 'off' }, c)).toBeNull();
  });

  it('drops to null when the new model has no reasoning widget', () => {
    expect(
      coerceReasoningEffortForModel({ effort: 'low' }, caps({ reasoning_widget: 'none' }))
    ).toBeNull();
  });

  it('drops to null when the new model is unknown (no caps)', () => {
    expect(coerceReasoningEffortForModel({ effort: 'low' }, undefined)).toBeNull();
  });
});
