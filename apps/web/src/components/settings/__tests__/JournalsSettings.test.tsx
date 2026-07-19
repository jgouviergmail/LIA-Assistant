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
