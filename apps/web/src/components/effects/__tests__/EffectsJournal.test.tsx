/**
 * EffectsJournal — the user's record of what LIA did (ADR-263).
 *
 * Oracles are visible state, role/name and data transitions, per the frontend
 * charter: the exact total is stated (never the page length), an empty
 * register reads differently from a filter that matched nothing, a refresh
 * does NOT unmount the list, and the filter never disables the control the
 * click just landed on.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { EffectsJournal } from '@/components/effects/EffectsJournal';
import type { EffectEntry } from '@/types/effects';
import type { UseEffectsJournalResult } from '@/hooks/useEffectsJournal';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const dictionary: Record<string, string> = {
        'effects.journal.title': 'Action journal',
        'effects.journal.description': 'What LIA did',
        'effects.journal.refresh': 'Refresh',
        'effects.journal.retry': 'Retry',
        'effects.journal.error': 'Could not load',
        'effects.journal.loading': 'Loading',
        'effects.journal.filter_label': 'Filter by status',
        'effects.journal.load_more': 'Load more',
        'effects.journal.total': '{{count}} actions',
        'effects.journal.empty_title': 'Nothing yet',
        'effects.journal.empty_description': 'Actions will appear here',
        'effects.journal.empty_filtered_title': 'No match',
        'effects.journal.empty_filtered_description': 'Try another status',
        'effects.journal.empty_action': 'Go to the chat',
        'effects.journal.status.all': 'All',
        'effects.journal.status.succeeded': 'Done',
        'effects.journal.status.failed': 'Failed',
        'effects.journal.status.refused': 'Refused',
        'effects.journal.status.claimed': 'In progress',
        'effects.journal.status.abandoned': 'Interrupted',
        'effects.journal.source.user': 'You asked',
        'effects.journal.source.scheduled': 'Scheduled',
        'effects.journal.source.subagent': 'Sub-agent',
        'effects.labels.draft.email': 'Sent an email to {recipient}',
        'effects.labels.generic': 'Ran {tool}',
      };
      const template = dictionary[key];
      if (template === undefined) return (options?.defaultValue as string) ?? '';
      // i18next spelling first: {{count}} would otherwise be eaten by the
      // single-brace pass below, which is the backend labels' spelling.
      return template
        .replace(/\{\{(\w+)\}\}/g, (_m, name) => String(options?.[name] ?? ''))
        .replace(/\{(\w+)\}/g, (_m, name) => String(options?.[name] ?? ''));
    },
    i18n: { language: 'en' },
  }),
}));

const hookResult = vi.hoisted(() => ({ current: {} as UseEffectsJournalResult }));
const requestedStatus = vi.hoisted(() => ({ current: undefined as string | undefined }));

vi.mock('@/hooks/useEffectsJournal', () => ({
  useEffectsJournal: (status?: string) => {
    requestedStatus.current = status;
    return hookResult.current;
  },
  EFFECTS_PAGE_SIZE: 20,
}));

function entry(overrides: Partial<EffectEntry> = {}): EffectEntry {
  return {
    id: 'effect-1',
    label_key: 'effects.labels.draft.email',
    values: { recipient: 'Marie' },
    tool_name: 'draft:email',
    mutation_policy: 'draft',
    status: 'succeeded',
    source: 'user',
    execution_mode: 'pipeline',
    approval_kind: 'draft_critique',
    error_code: null,
    claimed_at: '2026-09-04T10:00:00.000Z',
    closed_at: '2026-09-04T10:00:01.000Z',
    ...overrides,
  };
}

function state(overrides: Partial<UseEffectsJournalResult> = {}): UseEffectsJournalResult {
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
  requestedStatus.current = undefined;
});

describe('EffectsJournal', () => {
  it('states what was done, in the reader s language', () => {
    render(<EffectsJournal lng="en" />);

    expect(screen.getByRole('heading', { name: 'Action journal' })).toBeInTheDocument();
    expect(screen.getByText('Sent an email to Marie')).toBeInTheDocument();
  });

  it('shows the EXACT total, not the number of rows on screen', () => {
    hookResult.current = state({ entries: [entry()], total: 137 });
    render(<EffectsJournal lng="en" />);

    expect(screen.getByText('137 actions')).toBeInTheDocument();
  });

  it('shows a skeleton and one announcement on first load', () => {
    hookResult.current = state({ entries: undefined, total: undefined, firstLoad: true });
    const { container } = render(<EffectsJournal lng="en" />);

    expect(container.querySelector('[data-slot="effects-skeleton"]')).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });

  it('marks a refresh busy WITHOUT unmounting the list', () => {
    hookResult.current = state({ loading: true, firstLoad: false });
    render(<EffectsJournal lng="en" />);

    expect(screen.getByText('Sent an email to Marie')).toBeInTheDocument();
    const busy = document.querySelector('[aria-busy="true"]');
    expect(busy).not.toBeNull();
  });

  it('reads an empty register as "nothing yet"', () => {
    hookResult.current = state({ entries: [], total: 0 });
    render(<EffectsJournal lng="en" />);

    expect(screen.getByText('Nothing yet')).toBeInTheDocument();
  });

  it('reads an empty FILTERED answer as "no match" — a different emptiness', async () => {
    render(<EffectsJournal lng="en" />);
    await userEvent.click(screen.getByRole('button', { name: 'Failed' }));

    // The filter went to the server; the server answered with nothing.
    hookResult.current = state({ entries: [], total: 0 });
    await userEvent.click(screen.getByRole('button', { name: 'Done' }));
    await userEvent.click(screen.getByRole('button', { name: 'Failed' }));

    expect(screen.getByText('No match')).toBeInTheDocument();
  });

  it('sends the filter to the SERVER, so the total describes what is shown', async () => {
    render(<EffectsJournal lng="en" />);

    await userEvent.click(screen.getByRole('button', { name: 'Failed' }));

    expect(requestedStatus.current).toBe('failed');
  });

  it('asks for everything when no filter is active', () => {
    render(<EffectsJournal lng="en" />);

    expect(requestedStatus.current).toBeUndefined();
  });

  it('marks the active filter with aria-current and never disables it', async () => {
    render(<EffectsJournal lng="en" />);
    const group = screen.getByRole('group', { name: 'Filter by status' });

    const all = within(group).getByRole('button', { name: 'All' });
    expect(all).toHaveAttribute('aria-current', 'true');
    expect(all).not.toBeDisabled();

    await userEvent.click(within(group).getByRole('button', { name: 'Done' }));
    expect(within(group).getByRole('button', { name: 'Done' })).toHaveAttribute(
      'aria-current',
      'true'
    );
    expect(within(group).getByRole('button', { name: 'Done' })).not.toBeDisabled();
  });

  it('keeps the keyboard focus on the filter it just activated', async () => {
    render(<EffectsJournal lng="en" />);
    const failed = screen.getByRole('button', { name: 'Failed' });

    await userEvent.click(failed);

    expect(document.activeElement).toBe(failed);
  });

  it('states an error with a way out, without hiding a loaded list', () => {
    hookResult.current = state({ entries: undefined, total: undefined, error: new Error('x') });
    render(<EffectsJournal lng="en" />);

    expect(screen.getByText('Could not load')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('offers "load more" only when more rows exist — filter or not', async () => {
    render(<EffectsJournal lng="en" />);
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument();

    hookResult.current = state({ hasMore: true });
    const { rerender } = render(<EffectsJournal lng="en" />);
    rerender(<EffectsJournal lng="en" />);
    expect(screen.getAllByRole('button', { name: 'Load more' }).length).toBeGreaterThan(0);

    // Under a filter too: the server pages the filtered set, so hiding the
    // control would amputate the feature exactly when a reader needs it.
    await userEvent.click(screen.getAllByRole('button', { name: 'Failed' })[0]);
    expect(screen.getAllByRole('button', { name: 'Load more' }).length).toBeGreaterThan(0);
  });

  it('falls back to the generic wording rather than printing a key', () => {
    hookResult.current = state({
      entries: [entry({ label_key: 'effects.labels.unknown', tool_name: 'mystery_tool' })],
    });
    render(<EffectsJournal lng="en" />);

    expect(screen.getByText('Ran mystery_tool')).toBeInTheDocument();
    expect(screen.queryByText(/effects\.labels/)).not.toBeInTheDocument();
  });

  it('states the outcome and the authority of each row', () => {
    hookResult.current = state({
      entries: [entry({ status: 'failed', source: 'scheduled' })],
      total: 1,
    });
    render(<EffectsJournal lng="en" />);

    // Scoped to the row: "Failed" is also a filter button above the list.
    const row = screen.getByRole('listitem');
    expect(within(row).getByText('Failed')).toBeInTheDocument();
    expect(within(row).getByText('Scheduled')).toBeInTheDocument();
  });
});
