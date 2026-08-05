/**
 * Pure derivations driving the v2 orchestrator:
 *
 * - `sectionPresence`: which sections have data on this request (empty ones
 *   fold behind a per-group "idle" disclosure instead of stacking N/A rows).
 * - `collectAnomalies`: which sections carry a problem — the "identify the
 *   issue in 5 seconds" layer (header counter + per-section dot).
 */
import { describe, expect, it } from 'vitest';

import { collectAnomalies } from '../anomalies';
import { sectionPresence } from '../presence';
import { baseDebugMetrics } from '../../__tests__/fixtures';
import type { DebugMetrics } from '@/types/chat';

const BASE: DebugMetrics = baseDebugMetrics();

describe('sectionPresence', () => {
  it('marks the always-on analysis sections present and optional ones absent', () => {
    const presence = sectionPresence(BASE);
    expect(presence.intent).toBe(true);
    expect(presence.query).toBe(true);
    expect(presence.planner).toBe(false);
    expect(presence.tools).toBe(false);
    expect(presence['rag-injection']).toBe(false);
    expect(presence.llm_pipeline).toBe(false);
  });

  it('marks optional sections present when their data carries substance', () => {
    const presence = sectionPresence({
      ...BASE,
      planner_intelligence: {
        strategy: 'generative',
        tokens: { used: 1, saved: 1, full_catalogue_estimate: 2, reduction_percentage: 50 },
        plan: {},
        flags: { used_template: false, used_panic_mode: false, used_generative: true },
        success: true,
      },
      for_each_analysis: {
        detected: true,
        collection_key: 'contacts',
        cardinality_magnitude: 3,
        cardinality_mode: 'each',
        constraint_hints: {},
      },
      llm_calls: [
        {
          node_name: 'router',
          model_name: 'm',
          tokens_in: 1,
          tokens_out: 1,
          tokens_cache: 0,
          cost_eur: 0,
        },
      ],
    });
    expect(presence.planner).toBe(true);
    expect(presence.for_each_analysis).toBe(true);
    expect(presence.llm_pipeline).toBe(true);
  });
});

describe('collectAnomalies', () => {
  it('returns nothing on a healthy request', () => {
    expect(collectAnomalies(BASE)).toEqual([]);
  });

  it('collects the failure signals across sections', () => {
    const anomalies = collectAnomalies({
      ...BASE,
      planner_intelligence: {
        strategy: 'panic_mode',
        tokens: { used: 1, saved: 0, full_catalogue_estimate: 1, reduction_percentage: 0 },
        plan: {},
        flags: { used_template: false, used_panic_mode: true, used_generative: false },
        success: false,
        error: 'boom',
      },
      execution_timeline: {
        steps: [
          {
            step_id: 's1',
            tool_name: 't',
            domain: 'contact',
            status: 'error',
            success: false,
            duration_ms: 10,
          },
        ],
        total_steps: 1,
        completed_steps: 1,
      },
      semantic_validation: {
        is_valid: false,
        confidence: 0.4,
        criticality: 'HIGH',
        requires_clarification: false,
        clarification_questions: [],
        validation_duration_seconds: 1,
        used_fallback: false,
        fallback_reason: null,
        issues: [],
      },
      token_budget: {
        current_tokens: 15000,
        thresholds: { safe: 4000, warning: 8000, critical: 12000, max: 16000 },
        zone: 'emergency',
        strategy: 'simple_search',
        fallback_active: true,
      },
      memory_detection: {
        enabled: true,
        extracted_memories: [],
        existing_similar: [],
        llm_metadata: null,
        error: 'llm failed',
      },
    });

    const sections = anomalies.map(a => a.section);
    expect(sections).toContain('planner');
    expect(sections).toContain('execution');
    expect(sections).toContain('semantic_validation');
    expect(sections).toContain('token_budget');
    expect(sections).toContain('memory-detection');
  });

  it('flags a section whose payload does not match its schema (detector, not gatekeeper)', () => {
    const anomalies = collectAnomalies({
      ...BASE,
      // interrupted must be a boolean — a drifted payload must SURFACE, not
      // silently disappear or crash the section.
      hitl: { interrupted: 'yes' } as unknown as DebugMetrics['hitl'],
    });
    const hit = anomalies.find(a => a.section === 'hitl');
    expect(hit).toBeTruthy();
    expect(hit!.label).toMatch(/payload/i);
  });

  it('flags a ReAct loop that hit its ceiling', () => {
    const anomalies = collectAnomalies({
      ...BASE,
      execution_mode: 'react',
      react_execution: {
        iterations: 10,
        max_iterations: 10,
        elapsed_seconds: 60,
        tool_names: [],
        executed_tool_calls: 9,
      },
    });
    expect(anomalies.map(a => a.section)).toContain('react_execution');
  });
});
