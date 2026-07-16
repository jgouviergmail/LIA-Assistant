/**
 * Unit tests for the debug-metrics validators.
 *
 * Covers both the Zod-backed structural validators (full metrics, domain/tool
 * scores) and the hand-rolled semantic checks (intent, routing, token budget,
 * planner intelligence, numeric sanitization, score range). The logger is
 * mocked so warn/error paths stay silent. Minimal fixtures are cast to the
 * public metric shapes — the validators only read the fields asserted here.
 */
import { describe, expect, it, vi } from 'vitest';

import {
  sanitizeNumericValue,
  validateDebugMetrics,
  validateDomainScores,
  validateIntentDetection,
  validatePlannerIntelligence,
  validateRoutingDecision,
  validateScoreRange,
  validateTokenBudget,
  validateToolScores,
} from '../validators';
import type { DebugMetrics } from '@/types/chat';

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

const cast = <T>(o: unknown): T => o as T;

const validMetrics = {
  intent_detection: { detected_intent: 'greet', confidence: 0.9, user_goal: 'g', thresholds: {} },
  domain_selection: {
    selected_domains: ['contact'],
    primary_domain: 'contact',
    top_score: 0.9,
    thresholds: {},
  },
  routing_decision: { route_to: 'chat', confidence: 0.9, bypass_llm: false, thresholds: {} },
  context_resolution: {
    turn_type: 'new',
    is_reference: false,
    source_turn_id: null,
    source_domain: null,
    resolved_references: null,
    thresholds: {},
  },
  query_info: {
    original_query: 'q',
    english_query: 'q',
    english_enriched_query: null,
    user_language: 'en',
    implicit_intents: [],
    anticipated_needs: [],
    fallback_strategies: [],
  },
};

describe('validateDebugMetrics', () => {
  it('accepts a fully-formed metrics payload', () => {
    const result = validateDebugMetrics(validMetrics);
    expect(result.success).toBe(true);
    expect(result.data).toBeDefined();
  });

  it('rejects a malformed payload with per-path errors', () => {
    const result = validateDebugMetrics({ intent_detection: {} });
    expect(result.success).toBe(false);
    expect(result.errors && result.errors.length).toBeGreaterThan(0);
  });
});

describe('validateDomainScores', () => {
  it('returns calibrated scores when present', () => {
    const result = validateDomainScores(
      cast<DebugMetrics['domain_selection']>({
        selected_domains: ['contact'],
        primary_domain: 'contact',
        top_score: 0.9,
        all_scores: { contact: 0.9 },
        thresholds: {},
      })
    );
    expect(result.success).toBe(true);
    expect(result.type).toBe('calibrated');
    expect(result.data).toEqual({ contact: 0.9 });
  });

  it('fails softly when no scores are present', () => {
    const result = validateDomainScores(
      cast<DebugMetrics['domain_selection']>({
        selected_domains: [],
        primary_domain: 'general',
        top_score: 0,
        thresholds: {},
      })
    );
    expect(result.success).toBe(false);
    expect(result.errors).toEqual(['No domain scores available.']);
  });

  it('reports an invalid structure', () => {
    const result = validateDomainScores(cast<DebugMetrics['domain_selection']>({ foo: 'bar' }));
    expect(result.success).toBe(false);
    expect(result.errors).toEqual(['Invalid domain_selection structure']);
  });
});

describe('validateToolScores', () => {
  it('flags a completely absent section', () => {
    const result = validateToolScores(cast<DebugMetrics['tool_selection']>(undefined));
    expect(result.errors).toEqual(['SECTION_ABSENT']);
  });

  it('returns calibrated scores when present', () => {
    const result = validateToolScores(
      cast<DebugMetrics['tool_selection']>({
        selected_tools: [{ tool_name: 'x', score: 0.8, confidence: 'high' }],
        top_score: 0.8,
        has_uncertainty: false,
        all_scores: { x: 0.8 },
        thresholds: {},
      })
    );
    expect(result.success).toBe(true);
    expect(result.data).toEqual({ x: 0.8 });
  });

  it('fails when the section is present but scoreless', () => {
    const result = validateToolScores(
      cast<DebugMetrics['tool_selection']>({
        selected_tools: [],
        top_score: 0,
        has_uncertainty: false,
        thresholds: {},
      })
    );
    expect(result.success).toBe(false);
    expect(result.errors).toEqual(['No tool scores available.']);
  });

  it('reports an invalid structure', () => {
    const result = validateToolScores(cast<DebugMetrics['tool_selection']>({ selected_tools: 3 }));
    expect(result.success).toBe(false);
    expect(result.errors).toEqual(['Invalid tool_selection structure']);
  });
});

describe('validateIntentDetection', () => {
  it('accepts a valid section', () => {
    expect(
      validateIntentDetection(
        cast<DebugMetrics['intent_detection']>({ confidence: 0.5 })
      ).success
    ).toBe(true);
  });

  it('rejects a missing section', () => {
    const r = validateIntentDetection(cast<DebugMetrics['intent_detection']>(undefined));
    expect(r.errors).toEqual(['Intent detection metrics missing']);
  });

  it('rejects an out-of-range confidence', () => {
    const r = validateIntentDetection(cast<DebugMetrics['intent_detection']>({ confidence: 1.5 }));
    expect(r.errors).toEqual(['Confidence must be between 0 and 1']);
  });
});

describe('validateRoutingDecision', () => {
  it('accepts a valid route', () => {
    expect(
      validateRoutingDecision(
        cast<DebugMetrics['routing_decision']>({ route_to: 'planner', confidence: 0.7 })
      ).success
    ).toBe(true);
  });

  it('rejects a missing section', () => {
    expect(
      validateRoutingDecision(cast<DebugMetrics['routing_decision']>(undefined)).errors
    ).toEqual(['Routing decision metrics missing']);
  });

  it('rejects an unknown route target', () => {
    expect(
      validateRoutingDecision(
        cast<DebugMetrics['routing_decision']>({ route_to: 'nowhere', confidence: 0.7 })
      ).errors
    ).toEqual(['Invalid route_to value: nowhere']);
  });

  it('rejects an out-of-range confidence', () => {
    expect(
      validateRoutingDecision(
        cast<DebugMetrics['routing_decision']>({ route_to: 'chat', confidence: -0.1 })
      ).errors
    ).toEqual(['Confidence must be between 0 and 1']);
  });
});

describe('validateTokenBudget', () => {
  const budget = (over: Record<string, unknown>) =>
    cast<DebugMetrics['token_budget']>({
      current_tokens: 100,
      thresholds: { safe: 10, warning: 20, critical: 30, max: 40 },
      ...over,
    });

  it('accepts a monotonic budget', () => {
    expect(validateTokenBudget(budget({})).success).toBe(true);
  });

  it('flags an absent section', () => {
    expect(validateTokenBudget(cast<DebugMetrics['token_budget']>(undefined)).errors).toEqual([
      'SECTION_ABSENT',
    ]);
  });

  it('rejects non-monotonic thresholds', () => {
    expect(
      validateTokenBudget(budget({ thresholds: { safe: 30, warning: 20, critical: 10, max: 40 } }))
        .errors
    ).toEqual(['Invalid token budget thresholds (not monotonic)']);
  });

  it('rejects negative current tokens', () => {
    expect(validateTokenBudget(budget({ current_tokens: -5 })).errors).toEqual([
      'Current tokens cannot be negative',
    ]);
  });
});

describe('validatePlannerIntelligence', () => {
  const planner = (tokens: Record<string, number>) =>
    cast<DebugMetrics['planner_intelligence']>({ tokens });

  it('accepts consistent token stats', () => {
    expect(
      validatePlannerIntelligence(
        planner({ used: 10, saved: 5, full_catalogue_estimate: 20, reduction_percentage: 25 })
      ).success
    ).toBe(true);
  });

  it('flags an absent section', () => {
    expect(
      validatePlannerIntelligence(cast<DebugMetrics['planner_intelligence']>(undefined)).errors
    ).toEqual(['SECTION_ABSENT']);
  });

  it('rejects negative token counts', () => {
    expect(
      validatePlannerIntelligence(
        planner({ used: -1, saved: 5, full_catalogue_estimate: 20, reduction_percentage: 25 })
      ).errors
    ).toEqual(['Token counts cannot be negative']);
  });

  it('rejects an out-of-range reduction percentage', () => {
    expect(
      validatePlannerIntelligence(
        planner({ used: 10, saved: 5, full_catalogue_estimate: 20, reduction_percentage: 150 })
      ).errors
    ).toEqual(['Reduction percentage must be between 0 and 100']);
  });
});

describe('sanitizeNumericValue', () => {
  it('returns the value when valid', () => {
    expect(sanitizeNumericValue(42)).toBe(42);
  });

  it('returns the default for non-numbers and non-finite values', () => {
    expect(sanitizeNumericValue('x')).toBeNull();
    expect(sanitizeNumericValue(NaN)).toBeNull();
    expect(sanitizeNumericValue(Infinity, { defaultValue: 7 })).toBe(7);
  });

  it('honors allowNegative and min/max bounds', () => {
    expect(sanitizeNumericValue(-3, { allowNegative: false })).toBeNull();
    expect(sanitizeNumericValue(5, { min: 0, max: 3 })).toBeNull();
    expect(sanitizeNumericValue(2, { min: 0, max: 3 })).toBe(2);
  });
});

describe('validateScoreRange', () => {
  it('accepts a score within [0, 1]', () => {
    expect(validateScoreRange(0.5)).toBe(true);
    expect(validateScoreRange(0)).toBe(true);
    expect(validateScoreRange(1)).toBe(true);
  });

  it('rejects non-finite and out-of-range scores', () => {
    expect(validateScoreRange(NaN)).toBe(false);
    expect(validateScoreRange(-0.1)).toBe(false);
    expect(validateScoreRange(1.1, 'tool_score')).toBe(false);
  });
});
