/**
 * Unit tests for the debug-metrics validators (v3.4 surface).
 *
 * Kept API: the two score validators the sections consume, and
 * `validateSectionSchemas` — Zod as a DETECTOR feeding the anomaly channel
 * (fail-soft: mismatches surface, sections never disappear).
 */
import { describe, expect, it } from 'vitest';

import {
  validateDomainScores,
  validateSectionSchemas,
  validateToolScores,
} from '../validators';
import { baseDebugMetrics } from '../../__tests__/fixtures';
import type { DebugMetrics } from '@/types/chat';

const DOMAIN: DebugMetrics['domain_selection'] = {
  ...baseDebugMetrics().domain_selection,
  selected_domains: ['contact'],
  primary_domain: 'contact',
  top_score: 0.88,
  all_scores: { contact: 0.88, email: 0.2 },
};

const BASE: DebugMetrics = baseDebugMetrics({ domain_selection: DOMAIN });

describe('validateDomainScores', () => {
  it('returns the calibrated score map when scores exist', () => {
    const result = validateDomainScores(DOMAIN);
    expect(result.success).toBe(true);
    expect(result.data).toEqual({ contact: 0.88, email: 0.2 });
    expect(result.type).toBe('calibrated');
  });

  it('fails softly when no scores are available', () => {
    const result = validateDomainScores({ ...DOMAIN, all_scores: {} });
    expect(result.success).toBe(false);
    expect(result.errors?.[0]).toMatch(/No domain scores/);
  });

  it('rejects a structurally invalid section', () => {
    const result = validateDomainScores({
      ...DOMAIN,
      top_score: 42,
    } as DebugMetrics['domain_selection']);
    expect(result.success).toBe(false);
  });
});

describe('validateToolScores', () => {
  it('flags an absent section with the SECTION_ABSENT sentinel', () => {
    const result = validateToolScores(undefined);
    expect(result.success).toBe(false);
    expect(result.errors?.[0]).toBe('SECTION_ABSENT');
  });

  it('returns the score map for a valid section', () => {
    const result = validateToolScores({
      selected_tools: [{ tool_name: 't', score: 0.5, confidence: 'high' }],
      top_score: 0.5,
      has_uncertainty: false,
      all_scores: { t: 0.5 },
      thresholds: {},
    });
    expect(result.success).toBe(true);
    expect(result.data).toEqual({ t: 0.5 });
  });
});

describe('validateSectionSchemas', () => {
  it('returns nothing for a conforming payload', () => {
    expect(validateSectionSchemas(BASE)).toEqual([]);
  });

  it('skips absent sections — absence is presence business, not validation', () => {
    expect(validateSectionSchemas({ ...BASE, hitl: undefined })).toEqual([]);
  });

  it('reports a drifted section on its accordion value with a readable label', () => {
    const mismatches = validateSectionSchemas({
      ...BASE,
      hitl: { interrupted: 'yes' } as unknown as DebugMetrics['hitl'],
      intent_detection: {
        ...BASE.intent_detection,
        confidence: 12,
      },
    });
    const sections = mismatches.map(m => m.section);
    expect(sections).toContain('hitl');
    expect(sections).toContain('intent');
    for (const mismatch of mismatches) {
      expect(mismatch.label).toMatch(/Payload mismatch/);
    }
  });
});
