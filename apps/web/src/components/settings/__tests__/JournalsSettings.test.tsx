/**
 * JournalsSettings — the loading state (early return before the section body).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Accordion } from '@/components/ui/accordion';

const { useJournals } = vi.hoisted(() => ({ useJournals: vi.fn() }));
vi.mock('@/hooks/useJournals', () => ({ useJournals }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { JournalsSettings } from '../JournalsSettings';
import type { useJournals as useJournalsFn } from '@/hooks/useJournals';

type JournalsHook = ReturnType<typeof useJournalsFn>;

function hook(over: Partial<JournalsHook> = {}) {
  return {
    entries: [],
    settings: {},
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

beforeEach(() => vi.clearAllMocks());

describe('JournalsSettings', () => {
  it('shows a loading spinner while the journal loads', () => {
    useJournals.mockReturnValue(hook({ isLoading: true }));
    renderWithProviders(
      <Accordion type="multiple" defaultValue={['journals']}>
        <JournalsSettings lng="en" />
      </Accordion>
    );
    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});
