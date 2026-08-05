/**
 * v2 contract for the injection, extraction and pipeline sections.
 *
 * Same grammar as group 1 (English labels, themed icons, token tones) plus
 * the two analysis upgrades: node identity chips (bi-theme families) and
 * the LLM waterfall (run-anchored start offsets).
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Accordion } from '@/components/ui/accordion';
import { MemoryInjectionSection } from '../MemoryInjectionSection';
import { RAGInjectionSection } from '../RAGInjectionSection';
import { MemoryDetectionSection } from '../MemoryDetectionSection';
import { OpenLoopExtractionSection } from '../OpenLoopExtractionSection';
import { RequestLifecycleSection } from '../RequestLifecycleSection';
import { LLMPipelineSection } from '../LLMPipelineSection';
import { LLMCallsSection } from '../LLMCallsSection';
import { GoogleApiCallsSection } from '../GoogleApiCallsSection';
import type {
  LLMPipelineMetrics,
  MemoryDetectionMetrics,
  MemoryInjectionMetrics,
  OpenLoopExtractionMetrics,
  RAGInjectionMetrics,
  RequestLifecycleMetrics,
} from '@/types/chat';

function open(values: string[], ui: React.ReactNode) {
  return render(
    <Accordion type="multiple" defaultValue={values}>
      {ui}
    </Accordion>
  );
}

describe('MemoryInjectionSection v2', () => {
  const DATA: MemoryInjectionMetrics = {
    memory_count: 1,
    emotional_state: 'neutral',
    settings: { min_score: 0.6, max_results: 5 },
    memories: [
      {
        content: 'Loves jazz',
        category: 'preference',
        score: 0.82,
        emotional_weight: 4,
      },
    ],
  };

  it('renders English labels with the shared score bar', () => {
    open(['memory-injection'], <MemoryInjectionSection data={DATA} />);
    expect(screen.getByText('Memory Injection')).toBeInTheDocument();
    expect(screen.getByText(/Injected memories/)).toBeInTheDocument();
    // Shared ScoreBar replaces the inline bar copy.
    expect(screen.getByTestId('score-bar-fill')).toBeInTheDocument();
    expect(screen.getByText('POS')).toBeInTheDocument();
  });
});

describe('RAGInjectionSection v2', () => {
  const DATA: RAGInjectionMetrics = {
    spaces_searched: 1,
    chunks_found: 2,
    chunks_injected: 1,
    chunks: [{ space: 'Legal', file: 'contract.pdf', score: 0.74 }],
  };

  it('renders chunk rows with the shared score bar and legend', () => {
    open(['rag-injection'], <RAGInjectionSection data={DATA} />);
    expect(screen.getByText('RAG Knowledge Spaces')).toBeInTheDocument();
    expect(screen.getByText('contract.pdf')).toBeInTheDocument();
    expect(screen.getByTestId('score-bar-fill')).toBeInTheDocument();
    expect(screen.getByText('≥0.70')).toBeInTheDocument();
  });
});

describe('MemoryDetectionSection v2', () => {
  const DATA: MemoryDetectionMetrics = {
    enabled: true,
    extracted_memories: [
      {
        action: 'create',
        content: 'User plays tennis on Sundays',
        category: 'pattern',
        emotional_weight: 2,
        importance: 0.7,
        stored: true,
      },
    ],
    existing_similar: [],
    llm_metadata: {
      model: 'gpt-4.1-mini',
      input_tokens: 900,
      output_tokens: 60,
      cached_tokens: 0,
      total_tokens: 960,
    },
  };

  it('shows the action chip and the LLM spend line', () => {
    open(['memory-detection'], <MemoryDetectionSection data={DATA} />);
    expect(screen.getByText('Memory Extraction')).toBeInTheDocument();
    expect(screen.getByText('CREATE')).toBeInTheDocument();
    expect(screen.getByText('gpt-4.1-mini')).toBeInTheDocument();
  });
});

describe('OpenLoopExtractionSection v2', () => {
  const DATA: OpenLoopExtractionMetrics = {
    items_parsed: 1,
    opened: 1,
    closed: 0,
    skipped: 0,
    items: [
      {
        action: 'open',
        subject: 'envoyer le devis',
        direction: 'user_owes',
        counterparty: null,
        due_hint_iso: null,
      },
    ],
    llm_metadata: {
      model: 'gpt-4.1-mini',
      input_tokens: 1200,
      output_tokens: 80,
      cached_tokens: 300,
    },
  };

  it('now shows the extraction LLM spend like the sibling families', () => {
    open(['open-loop-extraction'], <OpenLoopExtractionSection data={DATA} />);
    expect(screen.getByText('Open Loop Extraction')).toBeInTheDocument();
    expect(screen.getByText('gpt-4.1-mini')).toBeInTheDocument();
  });
});

describe('RequestLifecycleSection v2', () => {
  const DATA: RequestLifecycleMetrics = {
    nodes: [
      {
        name: 'router',
        status: 'completed',
        tokens_in: 100,
        tokens_out: 20,
        tokens_cache: 0,
        cost_eur: 0.001,
        calls_count: 1,
        duration_ms: 800,
      },
      {
        name: 'react_call_model',
        status: 'completed',
        tokens_in: 500,
        tokens_out: 100,
        tokens_cache: 0,
        cost_eur: 0.004,
        calls_count: 2,
        duration_ms: 2400,
      },
    ],
    total_nodes: 2,
    total_duration_ms: 3200,
  };

  it('renders node identity chips (bi-theme families) in given order', () => {
    open(['request_lifecycle'], <RequestLifecycleSection data={DATA} />);
    expect(screen.getByText('Execution Times')).toBeInTheDocument();
    const react = screen.getByText('react_call_model');
    expect(react.className).toContain('fuchsia');
    expect(react.className).toContain('dark:text-fuchsia-300');
  });
});

describe('LLMPipelineSection v2', () => {
  const DATA: LLMPipelineMetrics = {
    calls: [
      {
        node_name: 'router',
        model_name: 'gpt-4.1-mini',
        tokens_in: 100,
        tokens_out: 20,
        tokens_cache: 0,
        cost_eur: 0.001,
        duration_ms: 800,
        call_type: 'chat',
        sequence: 1,
        started_offset_ms: 0,
      },
      {
        node_name: 'response',
        model_name: 'gpt-4.1',
        tokens_in: 900,
        tokens_out: 300,
        tokens_cache: 400,
        cost_eur: 0.01,
        duration_ms: 3200,
        call_type: 'chat',
        sequence: 2,
        started_offset_ms: 1000,
      },
    ],
    total_calls: 2,
    total_chat_calls: 2,
    total_embedding_calls: 0,
    total_duration_ms: 4000,
    total_tokens_in: 1000,
    total_tokens_out: 320,
    total_tokens_cache: 400,
    total_cost_eur: 0.011,
  };

  it('renders the chronological waterfall from the run-anchored offsets', () => {
    open(['llm_pipeline'], <LLMPipelineSection data={DATA} />);
    expect(screen.getByText('LLM Pipeline')).toBeInTheDocument();
    const bars = screen.getAllByTestId('waterfall-bar');
    expect(bars).toHaveLength(2);
    // Second call starts at 1000/4200ms of the wall (offset+duration max).
    expect(bars[1].style.left).not.toBe('0%');
    expect(bars[0].style.left).toBe('0%');
  });

  it('labels totals in English', () => {
    open(['llm_pipeline'], <LLMPipelineSection data={DATA} />);
    expect(screen.getAllByText(/2 calls/).length).toBeGreaterThan(0);
  });
});

describe('IntelligentMechanismsSection v2', () => {
  it('renders the LLM analysis block in English', async () => {
    const { IntelligentMechanismsSection } = await import('../IntelligentMechanismsSection');
    open(
      ['mechanisms'],
      <IntelligentMechanismsSection
        data={{
          llm_query_analysis: {
            applied: true,
            intent: 'search',
            mapped_intent: 'contact_search',
            confidence: 0.9,
            primary_domain: 'contact',
            secondary_domains: [],
            english_query: 'find marie',
            reasoning: 'clear lookup',
          },
        }}
      />
    );
    expect(screen.getByText('Intelligent Mechanisms')).toBeInTheDocument();
    expect(screen.getByText('Domains:')).toBeInTheDocument();
    expect(screen.getByText(/1 active/)).toBeInTheDocument();
  });
});

describe('SkillsSection v2', () => {
  it('tones the activation mode through the design system', async () => {
    const { SkillsSection } = await import('../SkillsSection');
    open(
      ['skills'],
      <SkillsSection
        data={{
          activated: true,
          skill_name: 'meteo-expert',
          activation_mode: 'bypass',
          is_deterministic: true,
        }}
      />
    );
    expect(screen.getByText('Skills')).toBeInTheDocument();
    const chips = screen.getAllByText('bypass');
    expect(chips.some(el => el.className.includes('text-success'))).toBe(true);
  });
});

describe('KnowledgeEnrichmentSection v2', () => {
  it('renders the executed case with token-toned chips', async () => {
    const { KnowledgeEnrichmentSection } = await import('../KnowledgeEnrichmentSection');
    open(
      ['knowledge-enrichment'],
      <KnowledgeEnrichmentSection
        data={{
          enabled: true,
          executed: true,
          encyclopedia_keywords: ['jazz'],
          is_news_query: false,
          endpoint: 'web',
          keyword_used: 'jazz',
          results_count: 3,
          from_cache: true,
        }}
      />
    );
    expect(screen.getByText('Knowledge Enrichment')).toBeInTheDocument();
    const cache = screen.getByText('CACHE');
    expect(cache.className).toContain('text-success');
  });
});

describe('JournalInjectionSection v2', () => {
  it('renders entries with the shared score bar and legend', async () => {
    const { JournalInjectionSection } = await import('../JournalInjectionSection');
    open(
      ['journal-injection'],
      <JournalInjectionSection
        plannerData={undefined}
        data={{
          entries_found: 1,
          entries_injected: 1,
          total_chars_injected: 320,
          max_chars_budget: 2000,
          max_results_setting: 5,
          entries: [
            {
              theme: 'learnings',
              title: 'Learned about jazz',
              score: 0.74,
              mood: 'curious',
              source: 'conversation',
              date: '2026-08-01',
              char_count: 320,
              injected: true,
            },
          ],
        }}
      />
    );
    expect(screen.getByText('Personal Journals')).toBeInTheDocument();
    expect(screen.getByTestId('score-bar-fill')).toBeInTheDocument();
    expect(screen.getByText('≥0.70')).toBeInTheDocument();
  });
});

describe('JournalExtractionSection v2', () => {
  it('tones the action counters through the design system', async () => {
    const { JournalExtractionSection } = await import('../JournalExtractionSection');
    open(
      ['journal-extraction'],
      <JournalExtractionSection
        data={{
          actions_parsed: 1,
          actions_applied: 1,
          entries: [
            {
              action: 'create',
              entry_id: 'e-1',
              theme: 'learnings',
              title: 'Jazz notes',
              mood: 'curious',
            },
          ],
        }}
      />
    );
    expect(screen.getByText('Journal Extraction')).toBeInTheDocument();
    const created = screen.getByText('+1');
    expect(created.className).toContain('text-success');
  });
});

describe('InterestProfileSection v2', () => {
  it('renders extracted interests with the shared confidence bar', async () => {
    const { InterestProfileSection } = await import('../InterestProfileSection');
    open(
      ['interest-profile'],
      <InterestProfileSection
        data={{
          enabled: true,
          analyzed: true,
          extracted_interests: [
            { topic: 'jazz', category: 'music', confidence: 0.85, action: 'create' },
          ],
          existing_interests: [],
          matching_decisions: [],
          llm_metadata: null,
        }}
      />
    );
    expect(screen.getByText('Interest Extraction')).toBeInTheDocument();
    expect(screen.getByText('CREATE')).toBeInTheDocument();
    expect(screen.getByTestId('score-bar-fill')).toBeInTheDocument();
  });
});

describe('LLMCallsSection v2', () => {
  it('renders the English summary with node identity chips', () => {
    open(
      ['llm'],
      <LLMCallsSection
        calls={[
          {
            node_name: 'planner',
            model_name: 'gpt-4.1-mini',
            tokens_in: 500,
            tokens_out: 100,
            tokens_cache: 100,
            cost_eur: 0.002,
          },
        ]}
        summary={{
          total_calls: 1,
          total_tokens_in: 500,
          total_tokens_out: 100,
          total_tokens_cache: 100,
          total_cost_eur: 0.002,
        }}
      />
    );
    expect(screen.getByText('LLM Calls')).toBeInTheDocument();
    expect(screen.getByText('Summary')).toBeInTheDocument();
    expect(screen.getByText('Cache efficiency:')).toBeInTheDocument();
    const chip = screen.getByText('planner');
    expect(chip.className).toContain('blue');
  });
});

describe('GoogleApiCallsSection v2', () => {
  it('renders the English summary and per-call details', () => {
    open(
      ['google-api'],
      <GoogleApiCallsSection
        calls={[
          { api_name: 'places', endpoint: '/places:searchText', cost_usd: 0.005, cost_eur: 0.0046, cached: false },
        ]}
        summary={{
          total_calls: 1,
          billable_calls: 1,
          cached_calls: 0,
          total_cost_usd: 0.005,
          total_cost_eur: 0.0046,
        }}
      />
    );
    expect(screen.getByText('Google API')).toBeInTheDocument();
    expect(screen.getByText('Summary')).toBeInTheDocument();
    expect(screen.getByText('Billable:')).toBeInTheDocument();
  });
});
