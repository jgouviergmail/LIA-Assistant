/**
 * DebugPanel v2 orchestrator.
 *
 * The panel reads in EXECUTION ORDER (7 numbered phases), folds idle
 * sections behind a per-phase disclosure, surfaces anomalies on the entry
 * header, and gives each history entry a scannable summary strip.
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { DebugPanel } from '../DebugPanel';
import { baseDebugMetrics } from './fixtures';
import type { DebugMetrics } from '@/types/chat';
import type { DebugMetricsEntry } from '@/types/chat-state';

const CHAT_METRICS: DebugMetrics = baseDebugMetrics({
  execution_mode: 'pipeline',
  llm_calls: [
    {
      node_name: 'router',
      model_name: 'm',
      tokens_in: 100,
      tokens_out: 10,
      tokens_cache: 0,
      cost_eur: 0.001,
      duration_ms: 500,
      started_offset_ms: 0,
    },
  ],
  llm_summary: {
    total_calls: 1,
    total_tokens_in: 100,
    total_tokens_out: 10,
    total_tokens_cache: 0,
    total_cost_eur: 0.001,
  },
  request_lifecycle: {
    nodes: [
      {
        name: 'router',
        status: 'completed',
        tokens_in: 100,
        tokens_out: 10,
        tokens_cache: 0,
        cost_eur: 0.001,
        calls_count: 1,
        duration_ms: 500,
      },
    ],
    total_nodes: 1,
    total_duration_ms: 500,
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
});

function entry(metrics: DebugMetrics, id = 'e1'): DebugMetricsEntry {
  return {
    id,
    timestamp: new Date(2026, 7, 5, 14, 30, 5),
    query: metrics.query_info.original_query,
    metrics,
  };
}

describe('DebugPanel v2 — execution-ordered phases', () => {
  it('renders the seven phase headers in execution order', () => {
    render(<DebugPanel metrics={CHAT_METRICS} history={[entry(CHAT_METRICS)]} />);

    const headers = screen.getAllByTestId('phase-header').map(h => h.textContent);
    expect(headers).toEqual([
      expect.stringContaining('Request'),
      expect.stringContaining('Analysis'),
      expect.stringContaining('Planning'),
      expect.stringContaining('Execution'),
      expect.stringContaining('Response context'),
      expect.stringContaining('Background extraction'),
      expect.stringContaining('Totals & pipeline'),
    ]);
  });

  it('folds idle sections behind a per-phase disclosure', async () => {
    const user = userEvent.setup();
    render(<DebugPanel metrics={CHAT_METRICS} history={[entry(CHAT_METRICS)]} />);

    // Planner has no data on a chat turn: not rendered directly.
    expect(screen.queryByText('Planner')).toBeNull();

    // The Planning phase exposes its idle disclosure; opening it reveals them.
    const toggles = screen.getAllByRole('button', { name: /idle section/ });
    expect(toggles.length).toBeGreaterThan(0);
    const planningToggle = toggles.find(t => t.getAttribute('aria-expanded') === 'false');
    expect(planningToggle).toBeTruthy();
    await user.click(toggles[0]);
    // After opening the Analysis-phase disclosure, its idle sections exist.
    expect(screen.getByText('FOR_EACH Analysis')).toBeInTheDocument();
  });

  it('shows the entry summary strip with clock, route and anomaly count', () => {
    render(<DebugPanel metrics={CHAT_METRICS} history={[entry(CHAT_METRICS)]} />);

    expect(screen.getByText('14:30:05')).toBeInTheDocument();
    expect(screen.getAllByText('chat').length).toBeGreaterThan(0);
    // semantic_validation.is_valid=false → 1 anomaly surfaced on the header.
    expect(screen.getByTitle(/anomal/i)).toBeInTheDocument();
  });

  it('exposes aria-expanded on the history entry toggle', async () => {
    const user = userEvent.setup();
    render(<DebugPanel metrics={CHAT_METRICS} history={[entry(CHAT_METRICS)]} />);

    const toggle = screen.getByRole('button', { name: /salut lia/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });

  it('renders the pipeline strip from the lifecycle nodes', () => {
    render(<DebugPanel metrics={CHAT_METRICS} history={[entry(CHAT_METRICS)]} />);
    const strip = screen.getByTestId('pipeline-strip');
    expect(within(strip).getByText('router')).toBeInTheDocument();
    expect(within(strip).getByText('500ms')).toBeInTheDocument();
  });

  it('keeps the empty state when no metrics exist', () => {
    render(<DebugPanel metrics={null} history={[]} />);
    expect(screen.getByText(/No debug metrics available/)).toBeInTheDocument();
  });
});
