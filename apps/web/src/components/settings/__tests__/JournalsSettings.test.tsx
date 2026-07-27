/**
 * JournalsSettings — the loading early-return, and the manual consolidation,
 * whose four outcomes are worded differently and must not be conflated: nothing
 * to change, changes applied, the LLM quota refusal (HTTP 429) and a generic
 * failure. The busy state must also lock the trigger so a second consolidation
 * cannot be queued on top of the first.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { Accordion } from '@/components/ui/accordion';

const { useJournals } = vi.hoisted(() => ({ useJournals: vi.fn() }));
vi.mock('@/hooks/useJournals', () => ({ useJournals }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { JournalsSettings } from '../JournalsSettings';
import type { JournalEntry, useJournals as useJournalsFn } from '@/hooks/useJournals';

type JournalsHook = ReturnType<typeof useJournalsFn>;

const CONSOLIDATE = 'journals.consolidateNow';

function entry(over: Partial<JournalEntry> = {}): JournalEntry {
  return {
    id: 'e1',
    theme: 'self_reflection',
    title: 'First light',
    content: 'A quiet observation.',
    mood: 'reflective',
    status: 'active',
    source: 'manual',
    personality_code: null,
    char_count: 20,
    search_hints: null,
    injection_count: 0,
    last_injected_at: null,
    confidence: 'medium',
    evidence_count: 0,
    contradiction_count: 0,
    level: 'L0',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  };
}

/** The hook exposes a list *response*, not a bare array (`entries.entries`). */
function entriesResponse(list: JournalEntry[] = []) {
  const totalChars = list.reduce((sum, e) => sum + e.char_count, 0);
  return {
    entries: list,
    by_theme: [],
    total: list.length,
    total_chars: totalChars,
    max_total_chars: 100_000,
    usage_pct: (totalChars / 100_000) * 100,
  };
}

function hook(over: Partial<JournalsHook> = {}) {
  return {
    entries: entriesResponse(),
    // The whole panel (entries, actions, consolidation) is gated on this flag —
    // with journals disabled only the master toggle renders.
    settings: { journals_enabled: true },
    isLoading: false,
    portrait: null,
    createEntry: vi.fn(),
    updateEntry: vi.fn(),
    deleteEntry: vi.fn(),
    deleteAllEntries: vi.fn(),
    updateSettings: vi.fn(),
    consolidateNow: vi.fn(),
    submitPortraitFeedback: vi.fn(),
    isCreating: false,
    isUpdating: false,
    isUpdatingSettings: false,
    isConsolidating: false,
    isSubmittingFeedback: false,
    ...over,
  };
}

function render() {
  return renderWithProviders(
    <Accordion type="multiple" defaultValue={['journals']}>
      <JournalsSettings lng="en" />
    </Accordion>
  );
}

beforeEach(() => vi.clearAllMocks());

describe('JournalsSettings', () => {
  it('shows a loading spinner while the journal loads', () => {
    useJournals.mockReturnValue(hook({ isLoading: true }));
    render();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});

describe('JournalsSettings — manual consolidation', () => {
  it('says nothing changed when the run applied no action', async () => {
    const consolidateNow = vi.fn().mockResolvedValue({ actions_applied: 0, duration_ms: 1500 });
    useJournals.mockReturnValue(hook({ consolidateNow }));
    const { user } = render();
    await user.click(await screen.findByRole('button', { name: CONSOLIDATE }));
    await waitFor(() => expect(consolidateNow).toHaveBeenCalledTimes(1));
    expect(toast.success).toHaveBeenCalledWith('journals.consolidatedNoop');
  });

  it('reports how many changes were applied', async () => {
    const consolidateNow = vi.fn().mockResolvedValue({ actions_applied: 3, duration_ms: 4200 });
    useJournals.mockReturnValue(hook({ consolidateNow }));
    const { user } = render();
    await user.click(await screen.findByRole('button', { name: CONSOLIDATE }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('journals.consolidatedSuccess'));
  });

  it('distinguishes an LLM quota refusal (429) from a generic failure', async () => {
    const consolidateNow = vi.fn().mockRejectedValue({ status: 429 });
    useJournals.mockReturnValue(hook({ consolidateNow }));
    const { user } = render();
    await user.click(await screen.findByRole('button', { name: CONSOLIDATE }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('journals.consolidatedQuota'));
  });

  it('falls back to the generic failure wording for any other error', async () => {
    const consolidateNow = vi.fn().mockRejectedValue(new Error('boom'));
    useJournals.mockReturnValue(hook({ consolidateNow }));
    const { user } = render();
    await user.click(await screen.findByRole('button', { name: CONSOLIDATE }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('journals.consolidatedError'));
  });

  it('locks the trigger while a consolidation is running', async () => {
    useJournals.mockReturnValue(hook({ isConsolidating: true }));
    render();
    expect(await screen.findByRole('button', { name: 'journals.consolidating' })).toBeDisabled();
  });
});

describe('JournalsSettings — settings toggles', () => {
  it('persists a settings change and confirms it', async () => {
    const updateSettings = vi.fn().mockResolvedValue(undefined);
    useJournals.mockReturnValue(hook({ updateSettings }));
    const { user } = render();
    await user.click(await screen.findByRole('switch', { name: 'journals.consolidation' }));
    await waitFor(() =>
      expect(updateSettings).toHaveBeenCalledWith({ journal_consolidation_enabled: false })
    );
    expect(toast.success).toHaveBeenCalledWith('journals.settingsUpdated');
  });

  it('reports a failed settings change', async () => {
    const updateSettings = vi.fn().mockRejectedValue(new Error('boom'));
    useJournals.mockReturnValue(hook({ updateSettings }));
    const { user } = render();
    await user.click(await screen.findByRole('switch', { name: 'journals.consolidation' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('journals.settingsError'));
  });
});

describe('JournalsSettings — export & bulk deletion', () => {
  it('exports the journal through the JSON endpoint in a new tab', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    const { user } = render();
    await user.click(await screen.findByRole('button', { name: 'journals.export' }));
    expect(open).toHaveBeenCalledWith('/api/v1/journals/export?format=json', '_blank');
  });

  it('offers no bulk deletion while the journal is empty', async () => {
    useJournals.mockReturnValue(hook({ entries: entriesResponse([]) }));
    render();
    expect(await screen.findByRole('button', { name: 'journals.deleteAll' })).toBeDisabled();
  });

  it('wipes every entry only after the confirmation is validated', async () => {
    const deleteAllEntries = vi.fn().mockResolvedValue(undefined);
    useJournals.mockReturnValue(hook({ entries: entriesResponse([entry()]), deleteAllEntries }));
    const { user } = render();
    await user.click(await screen.findByRole('button', { name: 'journals.deleteAll' }));
    await screen.findByText('journals.deleteAllTitle');
    expect(deleteAllEntries).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'common.delete' }));
    await waitFor(() => expect(deleteAllEntries).toHaveBeenCalledTimes(1));
    expect(toast.success).toHaveBeenCalledWith('journals.allDeleted');
  });

  it('reports a failed bulk deletion', async () => {
    const deleteAllEntries = vi.fn().mockRejectedValue(new Error('boom'));
    useJournals.mockReturnValue(hook({ entries: entriesResponse([entry()]), deleteAllEntries }));
    const { user } = render();
    await user.click(await screen.findByRole('button', { name: 'journals.deleteAll' }));
    await user.click(await screen.findByRole('button', { name: 'common.delete' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('journals.deleteAllError'));
  });
});

describe('JournalsSettings — entry creation', () => {
  it('refuses to create an entry with an empty title or body', async () => {
    const createEntry = vi.fn();
    useJournals.mockReturnValue(hook({ createEntry }));
    const { user } = render();
    // The trigger and the dialog's submit share the same label; the submit is
    // the one rendered last (in the dialog portal).
    await user.click(await screen.findByRole('button', { name: 'journals.create' }));
    await screen.findByText('journals.createTitle');
    const submits = screen.getAllByRole('button', { name: 'journals.create' });
    await user.click(submits[submits.length - 1]);
    expect(createEntry).not.toHaveBeenCalled();
  });
});

describe('JournalsSettings — theme grouping and counts', () => {
  /**
   * Until ADR-159 two of the four themes were permanently empty, so nothing
   * exercised the populated-group path. They now fill up, and the group badge
   * is the first thing a reader trusts.
   */
  it('renders one group per theme, including the two that used to be empty', async () => {
    useJournals.mockReturnValue(
      hook({
        entries: entriesResponse([
          entry({ id: 'a', theme: 'self_reflection' }),
          entry({ id: 'b', theme: 'ideas_analyses' }),
          entry({ id: 'c', theme: 'learnings' }),
          entry({ id: 'd', theme: 'user_observations' }),
        ]),
      })
    );
    render();
    for (const theme of ['self_reflection', 'user_observations', 'ideas_analyses', 'learnings']) {
      expect(await screen.findByText(`journals.themes.${theme}`)).toBeInTheDocument();
    }
  });

  it('counts on the badge exactly what the group renders', async () => {
    useJournals.mockReturnValue(
      hook({
        entries: entriesResponse([
          entry({ id: 'a', theme: 'learnings', title: 'L one' }),
          entry({ id: 'b', theme: 'learnings', title: 'L two' }),
          entry({ id: 'c', theme: 'ideas_analyses', title: 'I one' }),
        ]),
      })
    );
    const { user } = render();
    await user.click(await screen.findByText('journals.themes.learnings'));
    expect(await screen.findByText('L one')).toBeInTheDocument();
    expect(screen.getByText('L two')).toBeInTheDocument();

    const trigger = screen.getByText('journals.themes.learnings').closest('button');
    expect(trigger).not.toBeNull();
    // The badge sits next to the label inside the same trigger.
    expect(trigger?.textContent).toContain('2');
  });

  it('keeps the badge in step with the unused-only filter', async () => {
    /**
     * The badge used to come from the server-side `by_theme` total while the
     * rows came from the loaded page filtered client-side, so switching the
     * filter left a badge contradicting the list right under it.
     */
    useJournals.mockReturnValue(
      hook({
        entries: entriesResponse([
          entry({ id: 'a', theme: 'learnings', title: 'Used', injection_count: 4 }),
          entry({ id: 'b', theme: 'learnings', title: 'Never used', injection_count: 0 }),
        ]),
      })
    );
    const { user } = render();
    await user.click(await screen.findByText('journals.themes.learnings'));
    const label = () => screen.getByText('journals.themes.learnings').closest('button');
    expect(label()?.textContent).toContain('2');

    await user.click(await screen.findByLabelText('journals.filterUnused'));
    await waitFor(() => expect(label()?.textContent).toContain('1'));
    expect(screen.queryByText('Used')).not.toBeInTheDocument();
    expect(screen.getByText('Never used')).toBeInTheDocument();
  });
});

describe('JournalsSettings — truncated list', () => {
  it('says so when the response is a partial page', async () => {
    const response = entriesResponse([entry({ id: 'a', theme: 'learnings' })]);
    useJournals.mockReturnValue(hook({ entries: { ...response, total: 120 } }));
    render();
    // Asserted by its accessible role and its text, not only by a test id: the
    // notice exists to be *read*, and a live region is how it reaches a screen
    // reader once the list resolves.
    const notice = await screen.findByRole('status');
    expect(notice).toHaveTextContent('journals.listTruncated');
  });

  it('stays silent when every entry is on the page', async () => {
    useJournals.mockReturnValue(
      hook({ entries: entriesResponse([entry({ id: 'a', theme: 'learnings' })]) })
    );
    render();
    await screen.findByText('journals.themes.learnings');
    expect(screen.queryByTestId('journals-truncated-notice')).not.toBeInTheDocument();
  });
});
