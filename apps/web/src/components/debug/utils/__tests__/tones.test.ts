/**
 * Unit tests for the debug-panel tone foundation.
 *
 * The tone module is the single authority on colour semantics inside the
 * debug panel: semantic tones resolve to design-system tokens (theme-aware
 * by construction), node identities resolve to a bi-theme family palette,
 * and score tiers come from one documented table instead of four inline
 * divergent copies.
 */
import { describe, expect, it } from 'vitest';

import {
  type DebugTone,
  TONE_BAR,
  TONE_TEXT,
  badgeVariantFor,
  confidenceTone,
  fallbackLevelTone,
  nodeChipClasses,
  nodeFamily,
  scoreTier,
  strategyTone,
  executionStatusTone,
  tierTone,
  zoneTone,
} from '../tones';

const ALL_TONES: DebugTone[] = ['success', 'info', 'warning', 'destructive', 'alert', 'neutral'];

describe('tone token tables', () => {
  it('resolves every tone to a design-system token class, never a raw palette colour', () => {
    for (const tone of ALL_TONES) {
      const text = TONE_TEXT[tone];
      const bar = TONE_BAR[tone];
      expect(text).toBeTruthy();
      expect(bar).toBeTruthy();
      // Raw Tailwind palette colours (green-400, red-900/20…) are what broke
      // the panel across themes — tokens only.
      expect(text).not.toMatch(/(green|red|yellow|orange|blue|purple|gray)-\d/);
      expect(bar).not.toMatch(/(green|red|yellow|orange|blue|purple|gray)-\d/);
    }
    expect(TONE_TEXT.success).toBe('text-success');
    expect(TONE_TEXT.neutral).toBe('text-muted-foreground');
    expect(TONE_BAR.info).toBe('bg-primary');
  });

  it('maps tones onto Badge variants so chips inherit the contrast guard', () => {
    expect(badgeVariantFor('success')).toBe('success');
    expect(badgeVariantFor('destructive')).toBe('destructive');
    expect(badgeVariantFor('warning')).toBe('warning');
    expect(badgeVariantFor('info')).toBe('info');
    expect(badgeVariantFor('alert')).toBe('alert');
    expect(badgeVariantFor('neutral')).toBe('secondary');
  });
});

describe('semantic tone mappers', () => {
  it('grades confidence levels', () => {
    expect(confidenceTone('high')).toBe('success');
    expect(confidenceTone('medium')).toBe('warning');
    expect(confidenceTone('low')).toBe('destructive');
  });

  it('grades token-budget zones with density carrying the top level (ADR-205 doctrine)', () => {
    expect(zoneTone('safe')).toBe('success');
    expect(zoneTone('warning')).toBe('warning');
    expect(zoneTone('critical')).toBe('destructive');
    expect(zoneTone('emergency')).toBe('alert');
  });

  it('grades planner strategies by how degraded the path is', () => {
    expect(strategyTone('template_bypass')).toBe('success');
    expect(strategyTone('filtered_catalogue')).toBe('info');
    expect(strategyTone('generative')).toBe('info');
    expect(strategyTone('panic_mode')).toBe('destructive');
  });

  it('grades catalogue fallback levels on the same severity scale as zones', () => {
    expect(fallbackLevelTone('full_catalogue')).toBe('success');
    expect(fallbackLevelTone('filtered_catalogue')).toBe('warning');
    expect(fallbackLevelTone('reduced_descriptions')).toBe('warning');
    expect(fallbackLevelTone('primary_domain_only')).toBe('destructive');
    expect(fallbackLevelTone('simple_search')).toBe('alert');
  });

  it('routes execution step statuses through the app-wide lifecycle vocabulary', () => {
    expect(executionStatusTone('completed')).toBe('success');
    expect(executionStatusTone('running')).toBe('info');
    expect(executionStatusTone('error')).toBe('destructive');
    expect(executionStatusTone('pending')).toBe('info');
    // Unknown statuses stay neutral — never an invented alarm.
    expect(executionStatusTone('someday')).toBe('neutral');
  });
});

describe('score tiers', () => {
  it('classifies scores against the documented per-space thresholds', () => {
    // similarity space (memory injection): 0.8 / 0.6
    expect(scoreTier(0.8, 'similarity')).toBe('high');
    expect(scoreTier(0.79, 'similarity')).toBe('medium');
    expect(scoreTier(0.6, 'similarity')).toBe('medium');
    expect(scoreTier(0.59, 'similarity')).toBe('low');
    // relevance space (RAG / journals): 0.75 / 0.68 — see SCORE_SPACES
    expect(scoreTier(0.75, 'relevance')).toBe('high');
    expect(scoreTier(0.74, 'relevance')).toBe('medium');
    expect(scoreTier(0.68, 'relevance')).toBe('medium');
    expect(scoreTier(0.67, 'relevance')).toBe('low');
    // confidence space (interest extraction): 0.8 / 0.5
    expect(scoreTier(0.8, 'confidence')).toBe('high');
    expect(scoreTier(0.5, 'confidence')).toBe('medium');
    expect(scoreTier(0.4, 'confidence')).toBe('low');
  });

  it('maps tiers to tones for bars and legends', () => {
    expect(tierTone('high')).toBe('success');
    expect(tierTone('medium')).toBe('warning');
    expect(tierTone('low')).toBe('destructive');
  });
});

describe('node identity families', () => {
  it('assigns every known pipeline node to its family', () => {
    expect(nodeFamily('compaction')).toBe('analysis');
    expect(nodeFamily('router')).toBe('analysis');
    // Real node names observed at runtime (2026-08-05): the analyzer LLM and
    // the pre-planner memory resolution run inside the router phase.
    expect(nodeFamily('query_analyzer')).toBe('analysis');
    expect(nodeFamily('memory_reference_extraction')).toBe('analysis');
    expect(nodeFamily('planner')).toBe('planning');
    expect(nodeFamily('semantic_validator')).toBe('planning');
    expect(nodeFamily('clarification')).toBe('planning');
    expect(nodeFamily('hitl_dispatch')).toBe('hitl');
    expect(nodeFamily('approval_gate')).toBe('hitl');
    expect(nodeFamily('for_each_confirm')).toBe('hitl');
    expect(nodeFamily('task_orchestrator')).toBe('execution');
    expect(nodeFamily('parallel_executor')).toBe('execution');
    expect(nodeFamily('response')).toBe('response');
    expect(nodeFamily('fallback_response')).toBe('response');
    expect(nodeFamily('image_generation')).toBe('media');
    expect(nodeFamily('tts')).toBe('media');
  });

  it('assigns rule-based families: react_*, embedding_*, *_agent, *_extraction', () => {
    expect(nodeFamily('react_setup')).toBe('react');
    expect(nodeFamily('react_call_model')).toBe('react');
    expect(nodeFamily('react_execute_tools')).toBe('react');
    expect(nodeFamily('react_finalize')).toBe('react');
    expect(nodeFamily('embedding_embed_query')).toBe('embedding');
    expect(nodeFamily('embedding_embed_documents')).toBe('embedding');
    expect(nodeFamily('contact_agent')).toBe('execution');
    expect(nodeFamily('perplexity_agent')).toBe('execution');
    expect(nodeFamily('memory_extraction')).toBe('background');
    expect(nodeFamily('interest_extraction')).toBe('background');
    expect(nodeFamily('journal_extraction')).toBe('background');
    expect(nodeFamily('open_loop_extraction')).toBe('background');
    expect(nodeFamily('mystery_node')).toBe('unknown');
  });

  it('renders identity chips readable in BOTH themes (dark: split or theme token)', () => {
    const families = [
      'compaction',
      'planner',
      'hitl_dispatch',
      'task_orchestrator',
      'react_call_model',
      'image_generation',
      'embedding_embed_query',
      'memory_extraction',
    ];
    for (const node of families) {
      const classes = nodeChipClasses(node);
      // A raw text colour without a dark: counterpart is the exact defect the
      // old NODE_COLORS had (text-*-400 = dark-only).
      if (/text-[a-z]+-\d/.test(classes)) {
        expect(classes).toMatch(/dark:text-/);
      }
    }
    // Response uses the theme token — readable in both themes by construction.
    expect(nodeChipClasses('response')).toContain('text-primary');
    // Unknown nodes stay neutral.
    expect(nodeChipClasses('whatever')).toContain('text-muted-foreground');
  });

  it('gives distinct identities to distinct families', () => {
    const chips = new Set(
      ['router', 'planner', 'hitl_dispatch', 'task_orchestrator', 'react_setup', 'response', 'image_generation', 'embedding_embed_query', 'memory_extraction'].map(
        nodeChipClasses
      )
    );
    expect(chips.size).toBe(9);
  });
});
