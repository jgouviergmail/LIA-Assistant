/**
 * v2 contract for the analysis + planning + execution sections.
 *
 * One presentation grammar: English-only labels, themed title icon on every
 * section, token-based tones (no raw dark-only palette), neutral empty
 * states. Data logic is unchanged — these tests pin the v2 surface.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Accordion } from '@/components/ui/accordion';
import { IntentSection } from '../IntentSection';
import { DomainSection } from '../DomainSection';
import { RoutingSection } from '../RoutingSection';
import { QuerySection } from '../QuerySection';
import { ContextSection } from '../ContextSection';
import { ForEachAnalysisSection } from '../ForEachAnalysisSection';
import { PlannerSection } from '../PlannerSection';
import { ToolSection } from '../ToolSection';
import { TokenBudgetSection } from '../TokenBudgetSection';
import { ExecutionSection } from '../ExecutionSection';
import { ExecutionWavesSection } from '../ExecutionWavesSection';
import type { DebugMetrics } from '@/types/chat';

function open(values: string[], ui: React.ReactNode) {
  return render(
    <Accordion type="multiple" defaultValue={values}>
      {ui}
    </Accordion>
  );
}

const INTENT: DebugMetrics['intent_detection'] = {
  detected_intent: 'contact_search',
  confidence: 0.92,
  user_goal: 'find_information',
  goal_reasoning: 'User asks for a contact',
  thresholds: {
    high_threshold: { value: 0.7, actual: 0.92, passed: true },
    fallback_threshold: { value: 0.5, actual: 0.92, passed: true },
  },
};

const DOMAIN: DebugMetrics['domain_selection'] = {
  selected_domains: ['contact'],
  primary_domain: 'contact',
  top_score: 0.88,
  all_scores: { contact: 0.88 },
  thresholds: {
    primary_min: { value: 0.15, actual: 0.88, passed: true },
    max_domains: { value: 3, info: 'Maximum domains to select' },
  },
};

const ROUTING: DebugMetrics['routing_decision'] = {
  route_to: 'planner',
  confidence: 0.9,
  bypass_llm: false,
  reasoning_trace: ['llm_analysis', 'actionable'],
  thresholds: {
    chat_semantic_threshold: { value: 0.4, actual: 0.88, passed: true },
    high_semantic_threshold: { value: 0.7, actual: 0.88, passed: true },
    min_confidence: { value: 0.5, actual: 0.9, passed: true },
    chat_override_threshold: { value: 0.75, info: 'override' },
  },
};

const QUERY: DebugMetrics['query_info'] = {
  original_query: 'trouve marie',
  english_query: 'find marie',
  english_enriched_query: 'find contact marie',
  user_language: 'fr',
  implicit_intents: [],
  anticipated_needs: [],
  fallback_strategies: [],
};

const CONTEXT: DebugMetrics['context_resolution'] = {
  turn_type: 'initial',
  is_reference: false,
  source_turn_id: null,
  source_domain: null,
  resolved_references: null,
  thresholds: {
    confidence_threshold: { value: 0.6, info: 'min confidence' },
    active_window_turns: { value: 6, info: 'window' },
  },
};

function titleIcon(): Element | null {
  return document.querySelector('h3 svg.lucide, button svg.lucide');
}

describe('IntentSection v2', () => {
  it('renders English labels with a themed title icon', () => {
    open(['intent'], <IntentSection data={INTENT} />);
    expect(screen.getByText('Intent Detection')).toBeInTheDocument();
    expect(screen.getByText('Detected action:')).toBeInTheDocument();
    expect(screen.getByText('User goal:')).toBeInTheDocument();
    expect(screen.getByText('Decision thresholds')).toBeInTheDocument();
    expect(titleIcon()?.getAttribute('class')).toContain('text-primary');
  });
});

describe('DomainSection v2', () => {
  it('renders English labels and the selection outcome', () => {
    open(['domain'], <DomainSection data={DOMAIN} />);
    expect(screen.getByText('Domain Selection')).toBeInTheDocument();
    expect(screen.getByText('Active domains:')).toBeInTheDocument();
    expect(screen.getByText('Primary domain:')).toBeInTheDocument();
  });
});

describe('RoutingSection v2', () => {
  it('names the destination in English', () => {
    open(['routing'], <RoutingSection data={ROUTING} />);
    expect(screen.getByText('Routing Decision')).toBeInTheDocument();
    expect(screen.getByText('Planner (tools)')).toBeInTheDocument();
    expect(screen.getByText('LLM bypassed:')).toBeInTheDocument();
  });
});

describe('QuerySection v2', () => {
  it('shows the transformation pipeline in English', () => {
    open(['query'], <QuerySection data={QUERY} />);
    expect(screen.getByText('Query')).toBeInTheDocument();
    expect(screen.getByText('Original query')).toBeInTheDocument();
    expect(screen.getByText('↓ translation')).toBeInTheDocument();
    expect(screen.getByText('↓ enrichment')).toBeInTheDocument();
  });
});

describe('ContextSection v2', () => {
  it('describes the conversational state in English', () => {
    open(['context'], <ContextSection data={CONTEXT} />);
    expect(screen.getByText('Context Resolution')).toBeInTheDocument();
    expect(screen.getByText('Turn type:')).toBeInTheDocument();
    expect(screen.getByText('Contextual reference:')).toBeInTheDocument();
  });
});

describe('ForEachAnalysisSection v2', () => {
  it('renders a neutral empty state when no bulk operation was detected', () => {
    open(
      ['for_each_analysis'],
      <ForEachAnalysisSection
        data={{
          detected: false,
          collection_key: null,
          cardinality_magnitude: null,
          cardinality_mode: 'single',
          constraint_hints: {},
        }}
      />
    );
    const badge = screen.getByText('N/A');
    expect(badge.closest('[class*="destructive"]')).toBeNull();
  });
});

describe('PlannerSection v2', () => {
  it('keeps English labels and uses token colours for the outcome', () => {
    open(
      ['planner'],
      <PlannerSection
        data={{
          strategy: 'filtered_catalogue',
          tokens: { used: 900, saved: 4100, full_catalogue_estimate: 5000, reduction_percentage: 82 },
          plan: { steps_count: 2, tools_used: ['get_contacts_tool'], estimated_cost_usd: 0.001 },
          flags: { used_template: false, used_panic_mode: false, used_generative: false },
          success: true,
          error: null,
        }}
      />
    );
    expect(screen.getByText('Planner')).toBeInTheDocument();
    expect(screen.getByText('Token economics')).toBeInTheDocument();
    const success = screen.getByText('Yes');
    expect(success.className).toContain('text-success');
  });
});

describe('ToolSection v2', () => {
  it('explains the chat route with a neutral message in English', () => {
    open(['tools'], <ToolSection data={undefined} />);
    expect(
      screen.getByText('Routed to chat (simple conversation) — no tool selection ran.')
    ).toBeInTheDocument();
    const badge = screen.getByText('N/A');
    expect(badge.closest('[class*="destructive"]')).toBeNull();
  });
});

describe('TokenBudgetSection v2', () => {
  it('renders English zone labels with token colours', () => {
    open(
      ['token_budget'],
      <TokenBudgetSection
        data={{
          current_tokens: 1000,
          thresholds: { safe: 4000, warning: 8000, critical: 12000, max: 16000 },
          zone: 'safe',
          strategy: 'full_catalogue',
          fallback_active: false,
          total_consumed: 1500,
          tokens_input: 1000,
          tokens_output: 500,
          tokens_cache: 200,
        }}
      />
    );
    expect(screen.getByText('Token Budget')).toBeInTheDocument();
    expect(screen.getByText('Context size')).toBeInTheDocument();
    expect(screen.getByText('Total consumed (actual)')).toBeInTheDocument();
    // Zone threshold labels are English and token-toned.
    expect(screen.getByText('Safe:')).toBeInTheDocument();
    expect(screen.getByText('Critical:')).toBeInTheDocument();
  });
});

describe('ExecutionSection v2', () => {
  it('renders theme-safe progress and English step details', () => {
    open(
      ['execution'],
      <ExecutionSection
        data={{
          steps: [
            {
              step_id: 's1',
              tool_name: 'get_contacts_tool',
              domain: 'contact',
              status: 'completed',
              success: true,
              duration_ms: 320,
            },
          ],
          total_steps: 1,
          completed_steps: 1,
        }}
      />
    );
    expect(screen.getByText('Execution Timeline')).toBeInTheDocument();
    expect(screen.getByText(/Domain: contact/)).toBeInTheDocument();
    // The old bar was bg-gray-200 (light-only): the track must be tokenized.
    expect(document.querySelector('[class*="bg-gray-200"]')).toBeNull();
    expect(document.querySelector('[class*="border-gray-300"]')).toBeNull();
  });
});

describe('ExecutionWavesSection v2', () => {
  it('shows planned parallelism metrics in English', () => {
    open(
      ['execution_waves'],
      <ExecutionWavesSection
        data={{
          total_waves: 2,
          max_parallelism: 3,
          critical_path_length: 2,
          average_parallelism: 2,
          waves: [
            { wave_id: 0, size: 3, steps: ['s1', 's2', 's3'] },
            { wave_id: 1, size: 1, steps: ['s4'] },
          ],
        }}
      />
    );
    expect(screen.getByText('Execution Waves')).toBeInTheDocument();
    expect(screen.getByText('Max parallelism:')).toBeInTheDocument();
    expect(screen.getByText('Wave 1')).toBeInTheDocument();
  });
});
