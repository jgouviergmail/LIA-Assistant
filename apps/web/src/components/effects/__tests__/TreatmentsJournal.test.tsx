/**
 * TreatmentsJournal — the user's record of what LIA looked at (ADR-263, lot 4).
 *
 * Oracles are visible state, role/name and data transitions, per the frontend
 * charter: the exact total is stated (never the page length), the headline is
 * the DOMAIN rather than a technical name, an empty register reads differently
 * from a filter that matched nothing, a refresh does NOT unmount the list, and
 * the filter never disables the control the click just landed on.
 *
 * One oracle belongs to this register alone: nothing of what was asked may
 * reach the screen, because nothing of it was recorded.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { TreatmentsJournal } from '@/components/effects/TreatmentsJournal';
import type { TreatmentEntry } from '@/types/treatments';
import type { UseTreatmentsJournalResult } from '@/hooks/useTreatmentsJournal';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const dictionary: Record<string, string> = {
        'treatments.journal.title': 'What LIA looked at',
        'treatments.journal.description': 'Capabilities consulted',
        'treatments.journal.refresh': 'Refresh',
        'treatments.journal.retry': 'Retry',
        'treatments.journal.error': 'Could not load',
        'treatments.journal.filter_label': 'Filter by capability',
        'treatments.journal.all_capabilities': 'All',
        'treatments.journal.load_more': 'Load more',
        'treatments.journal.total': '{{count}} consultations',
        'treatments.journal.duration': '{{ms}} ms',
        'treatments.journal.repeats': '×{{count}}',
        'treatments.journal.outcome.failed': 'No answer',
        'treatments.journal.empty_title': 'Nothing yet',
        'treatments.journal.empty_description': 'Consultations will appear here',
        'treatments.journal.empty_filtered_title': 'No match',
        'treatments.journal.empty_filtered_description': 'Try another capability',
        'treatments.journal.empty_action': 'Go to the chat',
        'treatments.domains.email': 'Emails',
        'treatments.domains.event': 'Calendar',
        'treatments.domains.unknown': 'Unidentified capability',
        'effects.journal.source.user': 'You asked',
        'effects.journal.source.scheduled': 'Scheduled',
        'effects.journal.source.subagent': 'Sub-agent',
        'effects.export.group_label': 'Export this register',
        'effects.export.markdown': 'Export (readable)',
        'effects.export.csv': 'Export (CSV)',
      };
      const template = dictionary[key];
      if (template === undefined) return (options?.defaultValue as string) ?? '';
      return template.replace(/\{\{(\w+)\}\}/g, (_m, name) => String(options?.[name] ?? ''));
    },
    i18n: { language: 'en' },
  }),
}));

const hookResult = vi.hoisted(() => ({ current: {} as UseTreatmentsJournalResult }));
const requestedTool = vi.hoisted(() => ({ current: undefined as string | undefined }));

vi.mock('@/hooks/useTreatmentsJournal', () => ({
  useTreatmentsJournal: (toolName?: string) => {
    requestedTool.current = toolName;
    return hookResult.current;
  },
  TREATMENTS_PAGE_SIZE: 20,
}));

function entry(overrides: Partial<TreatmentEntry> = {}): TreatmentEntry {
  return {
    id: 'treatment-1',
    domain: 'email',
    tool_name: 'get_emails_tool',
    mutation_policy: 'read',
    outcome: 'ok',
    source: 'user',
    execution_mode: 'pipeline',
    duration_ms: 142,
    thread_id: 'conv-1',
    run_id: 'run-1',
    occurred_at: '2026-09-04T10:00:00.000Z',
    ...overrides,
  };
}

function state(
  overrides: Partial<UseTreatmentsJournalResult> = {}
): UseTreatmentsJournalResult {
  return {
    entries: [entry()],
    total: 1,
    hasMore: false,
    firstLoad: false,
    loading: false,
    error: null,
    loadMore: vi.fn(),
    refetch: vi.fn(),
    ...overrides,
  };
}

beforeEach(() => {
  hookResult.current = state();
  requestedTool.current = undefined;
});

describe('TreatmentsJournal', () => {
  it('names the DOMAIN, not the tool, as the headline', () => {
    render(<TreatmentsJournal lng="en" />);

    expect(screen.getByRole('heading', { name: 'What LIA looked at' })).toBeInTheDocument();
    expect(screen.getByText('Emails')).toBeInTheDocument();
    // The technical half is present, beside it — nothing is hidden. Scoped to
    // the LIST: since both registers show their filter under one rule, the
    // capability also names a chip above, and an unscoped query would match
    // the control instead of the row it is supposed to describe.
    const list = screen.getByRole('list');
    expect(within(list).getByText('get_emails_tool')).toBeInTheDocument();
  });

  it('falls back to a readable wording for an unknown domain', () => {
    hookResult.current = state({ entries: [entry({ domain: 'made_up' })] });
    render(<TreatmentsJournal lng="en" />);

    expect(screen.getByText('Unidentified capability')).toBeInTheDocument();
  });

  it('shows the EXACT total, not the number of rows on screen', () => {
    hookResult.current = state({ entries: [entry()], total: 873 });
    render(<TreatmentsJournal lng="en" />);

    expect(screen.getByText('873 consultations')).toBeInTheDocument();
  });

  it('says which consultation did not answer', () => {
    hookResult.current = state({ entries: [entry({ outcome: 'failed' })] });
    render(<TreatmentsJournal lng="en" />);

    expect(screen.getByText('No answer')).toBeInTheDocument();
  });

  it('reads an empty register as "nothing yet"', () => {
    hookResult.current = state({ entries: [], total: 0 });
    render(<TreatmentsJournal lng="en" />);

    expect(screen.getByText('Nothing yet')).toBeInTheDocument();
    expect(screen.queryByText('No match')).not.toBeInTheDocument();
  });

  it('reads a filter that matched nothing as a DIFFERENT emptiness', async () => {
    // Two capabilities on screen, so a filter exists to select; then the
    // filtered payload comes back empty. The two emptinesses must not read
    // the same: one says "nothing happened", the other "change your filter".
    hookResult.current = state({
      entries: [entry(), entry({ id: 'treatment-2', tool_name: 'get_events_tool' })],
      total: 2,
    });
    const { rerender } = render(<TreatmentsJournal lng="en" />);

    await userEvent.click(screen.getByRole('button', { name: 'get_events_tool' }));
    // The filtered payload comes back empty. `refetch` is a mock, so the
    // re-render is driven explicitly rather than by a click that changes no
    // state — a click on a no-op control would have proved nothing.
    hookResult.current = state({ entries: [], total: 0 });
    rerender(<TreatmentsJournal lng="en" />);

    expect(requestedTool.current).toBe('get_events_tool');
    expect(screen.getByText('No match')).toBeInTheDocument();
    expect(screen.queryByText('Nothing yet')).not.toBeInTheDocument();
    // And the way back exists: the filter controls survive an empty result.
    expect(screen.getByRole('button', { name: 'All' })).toBeInTheDocument();
  });

  it('sends the filter to the SERVER so the total matches the list', async () => {
    hookResult.current = state({
      entries: [entry(), entry({ id: 'treatment-2', tool_name: 'get_events_tool' })],
    });
    render(<TreatmentsJournal lng="en" />);

    await userEvent.click(screen.getByRole('button', { name: 'get_events_tool' }));

    expect(requestedTool.current).toBe('get_events_tool');
  });

  it('never disables the filter control the click just landed on', async () => {
    hookResult.current = state({
      entries: [entry(), entry({ id: 'treatment-2', tool_name: 'get_events_tool' })],
    });
    render(<TreatmentsJournal lng="en" />);
    const control = screen.getByRole('button', { name: 'get_events_tool' });

    await userEvent.click(control);

    expect(control).not.toBeDisabled();
    expect(control).toHaveFocus();
    expect(control).toHaveAttribute('aria-current', 'true');
  });

  it('marks a refresh busy instead of unmounting the list', () => {
    hookResult.current = state({ loading: true, firstLoad: false });
    render(<TreatmentsJournal lng="en" />);

    expect(screen.getByText('Emails')).toBeInTheDocument();
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull();
  });

  it('shows skeleton geometry on the FIRST load only', () => {
    hookResult.current = state({ entries: undefined, total: undefined, firstLoad: true });
    render(<TreatmentsJournal lng="en" />);

    expect(document.querySelector('[data-slot="treatments-skeleton"]')).not.toBeNull();
  });

  it('offers both export formats as downloads', () => {
    render(<TreatmentsJournal lng="en" />);

    const readable = screen.getByRole('link', { name: 'Export (readable)' });
    expect(readable).toHaveAttribute('download');
    expect(readable.getAttribute('href')).toContain('register=consultations');
    expect(screen.getByRole('link', { name: 'Export (CSV)' }).getAttribute('href')).toContain(
      'format=csv'
    );
  });

  it('separates the rows by DAY, one heading per day', () => {
    hookResult.current = state({
      entries: [
        entry({ id: 'a', occurred_at: '2026-09-04T10:00:00.000Z' }),
        entry({ id: 'b', occurred_at: '2026-09-04T18:00:00.000Z' }),
        entry({ id: 'c', occurred_at: '2026-09-03T09:00:00.000Z' }),
      ],
      total: 3,
    });
    render(<TreatmentsJournal lng="en" />);

    const headings = screen.getAllByRole('heading', { level: 3 });
    expect(headings).toHaveLength(2);
    expect(headings[0]).not.toHaveTextContent(headings[1].textContent ?? '');
  });

  it('groups CONSECUTIVE identical consultations instead of repeating them', () => {
    // The measured case: one ReAct turn asked the mailbox five times. Five
    // identical lines is a log; one line saying five is a register.
    hookResult.current = state({
      entries: [
        entry({ id: '1', duration_ms: 100 }),
        entry({ id: '2', duration_ms: 200 }),
        entry({ id: '3', duration_ms: 300 }),
      ],
      total: 3,
    });
    render(<TreatmentsJournal lng="en" />);

    expect(screen.getAllByRole('listitem')).toHaveLength(1);
    expect(screen.getByText(/×3/)).toBeInTheDocument();
    // The exact server-side total is untouched: nothing is hidden.
    expect(screen.getByText('3 consultations')).toBeInTheDocument();
  });

  it('never groups a failure with a success', () => {
    hookResult.current = state({
      entries: [
        entry({ id: '1' }),
        entry({ id: '2', outcome: 'failed' }),
        entry({ id: '3' }),
      ],
      total: 3,
    });
    render(<TreatmentsJournal lng="en" />);

    expect(screen.getAllByRole('listitem')).toHaveLength(3);
    expect(screen.getByText('No answer')).toBeInTheDocument();
  });

  it('never groups across a DAY boundary', () => {
    // Without this rule a single line would stand for calls made on two days
    // while carrying one day's timestamp — and the journal drew one heading
    // for a two-day span.
    hookResult.current = state({
      entries: [
        entry({ id: '1', occurred_at: '2026-09-04T10:00:00.000Z' }),
        entry({ id: '2', occurred_at: '2026-09-03T10:00:00.000Z' }),
      ],
      total: 2,
    });
    render(<TreatmentsJournal lng="en" />);

    expect(screen.getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getAllByRole('heading', { level: 3 })).toHaveLength(2);
    expect(screen.queryByText(/×2/)).not.toBeInTheDocument();
  });

  it('never groups two different capabilities', () => {
    hookResult.current = state({
      entries: [entry({ id: '1' }), entry({ id: '2', tool_name: 'get_events_tool' })],
      total: 2,
    });
    render(<TreatmentsJournal lng="en" />);

    expect(screen.getAllByRole('listitem')).toHaveLength(2);
  });

  it('sums the durations of a group rather than showing one of them', () => {
    hookResult.current = state({
      entries: [entry({ id: '1', duration_ms: 100 }), entry({ id: '2', duration_ms: 250 })],
      total: 2,
    });
    render(<TreatmentsJournal lng="en" />);

    expect(screen.getByText('350 ms')).toBeInTheDocument();
  });

  it('shows nothing of what was asked — because nothing was recorded', () => {
    render(<TreatmentsJournal lng="en" />);

    expect(document.body.textContent).not.toContain('query');
    expect(document.body.textContent).not.toContain('arguments');
  });
});
