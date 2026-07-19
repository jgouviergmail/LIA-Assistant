/**
 * ExecutionTraceDisclosure — collapsed backstage record (Lot 2 P2-V1).
 *
 * Oracles are role/name and visible state (repo a11y contract): a native
 * disclosure button with a stable accessible name, collapsed by default,
 * expanding to the grouped steps + reasoning. Renders nothing without a trace.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ExecutionTraceDisclosure } from '@/components/chat/ExecutionTraceDisclosure';
import type { ExecutionTrace } from '@/types/execution-trace';

// Identity translator; handles count + seconds interpolation used by the label.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (opts && typeof opts.count === 'number') return `${key}:${opts.count}`;
      if (opts && opts.seconds !== undefined) return `${key}:${opts.seconds}`;
      return key;
    },
  }),
}));

function trace(overrides: Partial<ExecutionTrace> = {}): ExecutionTrace {
  return {
    steps: [
      { emoji: '🧭', label: 'Analyse', category: 'system' },
      { emoji: '📧', label: 'Envoi email', category: 'tool' },
    ],
    reasoning: '',
    durationMs: 4200,
    ...overrides,
  };
}

describe('ExecutionTraceDisclosure', () => {
  it('renders nothing without a trace', () => {
    const { container } = render(<ExecutionTraceDisclosure trace={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing for an empty trace (no steps)', () => {
    const { container } = render(<ExecutionTraceDisclosure trace={trace({ steps: [] })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows a collapsed summary with step count and duration', () => {
    render(<ExecutionTraceDisclosure trace={trace()} />);

    const toggle = screen.getByRole('button', { name: 'chat.trace.aria_toggle' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    // Mock translator echoes key:count — the real i18next resolves the
    // summary_one/_other plurals (keys present in all 6 locales).
    expect(screen.getByText(/chat\.trace\.summary:2/)).toBeInTheDocument();
    expect(screen.getByText(/chat\.trace\.duration:4\.2/)).toBeInTheDocument();
    // Steps are hidden while collapsed.
    expect(screen.queryByText('Envoi email')).not.toBeInTheDocument();
  });

  it('expands to reveal the steps on click', async () => {
    render(<ExecutionTraceDisclosure trace={trace()} />);

    const toggle = screen.getByRole('button', { name: 'chat.trace.aria_toggle' });
    await userEvent.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Analyse')).toBeInTheDocument();
    expect(screen.getByText('Envoi email')).toBeInTheDocument();
  });

  it('shows the reasoning block when present (expanded)', async () => {
    render(<ExecutionTraceDisclosure trace={trace({ reasoning: 'I weighed the options.' })} />);

    await userEvent.click(screen.getByRole('button', { name: 'chat.trace.aria_toggle' }));

    expect(screen.getByText('chat.trace.reasoning_title')).toBeInTheDocument();
    expect(screen.getByText('I weighed the options.')).toBeInTheDocument();
  });

  it('omits the duration when the trace has none', () => {
    render(<ExecutionTraceDisclosure trace={trace({ durationMs: undefined })} />);
    expect(screen.queryByText(/chat\.trace\.duration/)).not.toBeInTheDocument();
  });
});
