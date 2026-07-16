/**
 * InterestsSettings — the loading state of the interests manager.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { useInterests } = vi.hoisted(() => ({ useInterests: vi.fn() }));
vi.mock('@/hooks/useInterests', () => ({ useInterests }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { InterestsSettings } from '../InterestsSettings';
import type { useInterests as useInterestsFn } from '@/hooks/useInterests';

type InterestsHook = ReturnType<typeof useInterestsFn>;

function hook(over: Partial<InterestsHook> = {}) {
  return {
    interests: [],
    total: 0,
    blockedCount: 0,
    dormantCount: 0,
    categories: [],
    settings: {},
    loading: false,
    settingsLoading: false,
    creating: false,
    deleting: false,
    deletingAll: false,
    submittingFeedback: false,
    updatingSettings: false,
    updating: false,
    reactivating: false,
    createInterest: vi.fn(),
    deleteInterest: vi.fn(),
    deleteAllInterests: vi.fn(),
    submitFeedback: vi.fn(),
    updateSettings: vi.fn(),
    updateInterest: vi.fn(),
    reactivateInterest: vi.fn(),
    refetch: vi.fn(),
    ...over,
  };
}

beforeEach(() => vi.clearAllMocks());

describe('InterestsSettings', () => {
  it('shows a loading spinner while interests load', () => {
    useInterests.mockReturnValue(hook({ loading: true }));
    renderWithProviders(<InterestsSettings lng="en" collapsible={false} />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});
