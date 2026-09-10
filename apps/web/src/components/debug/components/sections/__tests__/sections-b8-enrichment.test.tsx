/**
 * What the enriched panel actually shows (B8, lot 7).
 *
 * Four claims, each of which the panel got wrong or could not make before:
 *
 * 1. **the ReAct bound drawn is the bound ENFORCED** — the section published
 *    the hard ceiling while the loop stops at ADR-238's narrowed budget, so a
 *    turn that spent exactly its four iterations read as « 4/25 »: a model that
 *    gave up;
 * 2. **a failed model call looks failed** — it rendered exactly like a
 *    successful one, tokens billed and all;
 * 3. **the room the turn had is the MODEL's window**, not four instance-wide
 *    thresholds independent of it;
 * 4. **the two deferred registers are on screen** — a turn that opened nine
 *    sources used to look like a turn that did nothing.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Accordion } from '@/components/ui/accordion';
import { LLMCallsSection } from '../LLMCallsSection';
import { ReactExecutionSection } from '../ReactExecutionSection';
import { RegistersSection } from '../RegistersSection';
import { TokenBudgetSection } from '../TokenBudgetSection';
import type { LLMCall, ReactExecutionMetrics, RegistersMetrics } from '@/types/chat';

function open(values: string[], ui: React.ReactNode) {
  return render(
    <Accordion type="multiple" defaultValue={values}>
      {ui}
    </Accordion>
  );
}

const REACT_BASE: ReactExecutionMetrics = {
  iterations: 4,
  max_iterations: 25,
  elapsed_seconds: 8,
  tool_names: [],
  executed_tool_calls: 2,
};

function call(over: Partial<LLMCall> = {}): LLMCall {
  return {
    node_name: 'router',
    model_name: 'gpt-5-mini',
    tokens_in: 100,
    tokens_out: 20,
    tokens_cache: 0,
    cost_eur: 0.009,
    ...over,
  };
}

const SUMMARY = {
  total_calls: 1,
  total_tokens_in: 100,
  total_tokens_out: 20,
  total_tokens_cache: 0,
  total_cost_eur: 0.009,
};

describe('the ReAct loop draws the bound that stopped it', () => {
  it('shows the EFFECTIVE budget, not the ceiling', () => {
    open(
      ['react_execution'],
      <ReactExecutionSection
        data={{ ...REACT_BASE, iteration_budget: 4, iteration_ceiling: 25 }}
      />
    );

    // « 4/25 » on a turn narrowed to four iterations reads as a model that
    // gave up; « 4/4 » reads as a turn that spent what it was given.
    // Both the badge and the metric row carry it — the point is that 4/25 is gone.
    expect(screen.getAllByText('4/4').length).toBeGreaterThan(0);
    expect(screen.queryAllByText('4/25')).toHaveLength(0);
  });

  it('names the ceiling beside the budget when the two differ', () => {
    open(
      ['react_execution'],
      <ReactExecutionSection
        data={{ ...REACT_BASE, iteration_budget: 4, iteration_ceiling: 25 }}
      />
    );

    expect(screen.getByText(/^Ceiling:/)).toBeInTheDocument();
    expect(screen.getByText('25')).toBeInTheDocument();
  });

  it('never draws a ceiling row when nothing narrowed the turn', () => {
    open(
      ['react_execution'],
      <ReactExecutionSection
        data={{ ...REACT_BASE, iteration_budget: 25, iteration_ceiling: 25 }}
      />
    );

    expect(screen.queryByText(/^Ceiling:/)).not.toBeInTheDocument();
  });

  it('says why the loop stopped', () => {
    open(
      ['react_execution'],
      <ReactExecutionSection data={{ ...REACT_BASE, exit_reason: 'max_iterations' }} />
    );

    expect(screen.getByText(/^Stopped because:/)).toBeInTheDocument();
    expect(screen.getByText('max_iterations')).toBeInTheDocument();
  });

  it('names what the loop asked for and never got', () => {
    open(
      ['react_execution'],
      <ReactExecutionSection
        data={{ ...REACT_BASE, abandoned_calls: ['get_emails_tool', 'get_events_tool'] }}
      />
    );

    expect(screen.getByText('Asked for, never ran')).toBeInTheDocument();
    expect(screen.getByText('get_emails_tool')).toBeInTheDocument();
  });

  it('renders a payload persisted before this lot, minus the new rows', () => {
    // An older turn carries none of the new keys: it must still render on the
    // ceiling it did publish, rather than break.
    open(['react_execution'], <ReactExecutionSection data={REACT_BASE} />);

    expect(screen.getAllByText('4/25').length).toBeGreaterThan(0);
    expect(screen.queryByText(/^Stopped because:/)).not.toBeInTheDocument();
  });
});

describe('a model call says what was sent and what came back', () => {
  it('marks a failed call as failed', () => {
    open(
      ['llm'],
      <LLMCallsSection
        calls={[call({ status: 'error', failure_kind: 'rate_limit' })]}
        summary={SUMMARY}
      />
    );

    expect(screen.getByText('rate_limit')).toBeInTheDocument();
  });

  it('leaves a successful call unmarked', () => {
    open(['llm'], <LLMCallsSection calls={[call({ status: 'success' })]} summary={SUMMARY} />);

    expect(screen.queryByText('failed')).not.toBeInTheDocument();
  });

  it('names the configured slot, which is not the graph node', () => {
    open(
      ['llm'],
      <LLMCallsSection calls={[call({ llm_type: 'router_classification' })]} summary={SUMMARY} />
    );

    expect(screen.getByText('router_classification')).toBeInTheDocument();
  });

  it('lists the parameters that were actually observed', () => {
    open(
      ['llm'],
      <LLMCallsSection
        calls={[call({ provider: 'ollama', temperature: 0.2, reasoning_level: 'high' })]}
        summary={SUMMARY}
      />
    );

    const sent = screen.getByTitle('ollama · temp 0.2 · reasoning high');
    expect(sent).toBeInTheDocument();
  });

  it('prints NO parameter line when nothing was observed', () => {
    // A default temperature on a call that never carried one names a value the
    // provider never saw.
    open(['llm'], <LLMCallsSection calls={[call()]} summary={SUMMARY} />);

    expect(screen.queryByText(/^Sent:/)).not.toBeInTheDocument();
  });
});

describe('the token budget shows the model’s own window', () => {
  const BUDGET = {
    current_tokens: 5000,
    thresholds: { safe: 10000, warning: 20000, critical: 30000, max: 40000 },
    zone: 'safe' as const,
    strategy: 'full_catalogue',
    fallback_active: false,
  };

  it('names the window, its model and who declared it', () => {
    open(
      ['token_budget'],
      <TokenBudgetSection
        data={{
          ...BUDGET,
          context_window: 128000,
          context_window_source: 'catalogue',
          context_window_model: 'gpt-5-mini',
          context_used_percent: 4,
        }}
      />
    );

    expect(screen.getByText(/^Context window:/)).toBeInTheDocument();
    expect(screen.getByText('gpt-5-mini')).toBeInTheDocument();
    expect(screen.getByText('Model catalogue')).toBeInTheDocument();
  });

  it('warns when the window came from the fallback table', () => {
    // That table is a DEFAULT, not a measurement — it is wrong on 10 of its 56
    // entries — so it must not read like a declaration.
    open(
      ['token_budget'],
      <TokenBudgetSection
        data={{ ...BUDGET, context_window: 8192, context_window_source: 'table' }}
      />
    );

    expect(screen.getByText('Fallback table')).toBeInTheDocument();
  });

  it('publishes the instant compaction fires, even when it never fired', () => {
    open(
      ['token_budget'],
      <TokenBudgetSection
        data={{ ...BUDGET, context_window: 128000, compaction_threshold: 51200 }}
      />
    );

    expect(screen.getByText(/^Compacts at:/)).toBeInTheDocument();
  });

  it('draws no window block on a payload persisted before this lot', () => {
    open(['token_budget'], <TokenBudgetSection data={BUDGET} />);

    expect(screen.queryByText('Model window')).not.toBeInTheDocument();
  });
});

describe('the two deferred registers', () => {
  const REGISTERS: RegistersMetrics = {
    decision: {
      run_id: 'r',
      source: 'user',
      execution_mode: 'react',
      route: 'actionable',
      plan_step_count: 3,
      outcome: 'interrupted',
      stop_reason: null,
      settled: false,
    },
    treatments: {
      entries: [
        { tool_name: 'get_emails_tool', mutation_policy: 'read', outcome: 'ok', duration_ms: 87 },
        { tool_name: 'get_events_tool', mutation_policy: 'read', outcome: 'failed', duration_ms: 12 },
      ],
      count: 2,
      failed_count: 1,
    },
  };

  it('lists what the turn consulted', () => {
    open(['registers'], <RegistersSection data={REGISTERS} />);

    expect(screen.getByText('get_emails_tool')).toBeInTheDocument();
    expect(screen.getByText('get_events_tool')).toBeInTheDocument();
  });

  it('says the outcome is what is known SO FAR, not a verdict', () => {
    open(['registers'], <RegistersSection data={REGISTERS} />);

    expect(screen.getByText(/^Outcome so far:/)).toBeInTheDocument();
    expect(screen.getByText(/register row is written when the turn closes/)).toBeInTheDocument();
  });

  it('distinguishes a turn that consulted nothing from one with no register', () => {
    open(
      ['registers'],
      <RegistersSection
        data={{ decision: REGISTERS.decision, treatments: { entries: [], count: 0, failed_count: 0 } }}
      />
    );

    expect(screen.getByText(/opened none of the person/)).toBeInTheDocument();
  });

  it('draws nothing at all outside a turn', () => {
    const { container } = open(['registers'], <RegistersSection data={undefined} />);

    expect(container.textContent).not.toContain('Registers');
  });

  it('lists the silent corrections the turn made to itself', () => {
    open(
      ['registers'],
      <RegistersSection
        data={{
          ...REGISTERS,
          verdicts: {
            entries: [
              { kind: 'reasoning_coerced', detail: 'high->medium' },
              { kind: 'history_repaired', detail: 'tool_calls:removal' },
            ],
            count: 2,
            dropped: 0,
          },
        }}
      />
    );

    expect(screen.getByText('Reasoning level coerced')).toBeInTheDocument();
    expect(screen.getByText('high->medium')).toBeInTheDocument();
  });

  it('says when the per-turn cap dropped some', () => {
    // « 50 » with nothing beside it reads as an exact count (ADR-185).
    open(
      ['registers'],
      <RegistersSection
        data={{
          ...REGISTERS,
          verdicts: {
            entries: [{ kind: 'history_repaired', detail: null }],
            count: 50,
            dropped: 7,
          },
        }}
      />
    );

    expect(screen.getByText(/\+7 more, past the per-turn cap/)).toBeInTheDocument();
  });

  it('draws no correction block on a turn that corrected nothing', () => {
    open(['registers'], <RegistersSection data={REGISTERS} />);

    expect(screen.queryByText('Silently corrected')).not.toBeInTheDocument();
  });
});
