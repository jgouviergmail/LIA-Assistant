/**
 * InterestsSettings — the interest manager: loading, the rendered interest, and
 * the row actions that change what the assistant may bring up on its own —
 * deletion, the **block** feedback (worded differently from ordinary feedback
 * because it is a standing refusal), and the reactivation of a dormant or
 * blocked interest. Every action reports its own failure.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { useInterests } = vi.hoisted(() => ({ useInterests: vi.fn() }));
// The module also exports data the component renders (category icons); keep the
// real exports and swap only the hook.
vi.mock('@/hooks/useInterests', async importOriginal => {
  const actual = await importOriginal<typeof import('@/hooks/useInterests')>();
  return { ...actual, useInterests };
});
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { InterestsSettings } from '../InterestsSettings';
import type { Interest, useInterests as useInterestsFn } from '@/hooks/useInterests';

type InterestsHook = ReturnType<typeof useInterestsFn>;

function interest(over: Partial<Interest> = {}): Interest {
  return {
    id: 'i1',
    topic: 'Quantum computing',
    category: 'science',
    weight: 0.8,
    status: 'active',
    positive_signals: 3,
    negative_signals: 0,
    last_mentioned_at: null,
    last_notified_at: null,
    created_at: '2026-01-01T00:00:00Z',
    ...over,
  };
}

function hook(over: Partial<InterestsHook> = {}) {
  return {
    interests: [interest()],
    total: 1,
    blockedCount: 0,
    dormantCount: 0,
    categories: [],
    // The notification controls read these without an optional chain — an empty
    // settings object crashes the render.
    settings: {
      interests_notify_start_hour: 8,
      interests_notify_end_hour: 22,
      interests_notify_min_per_day: 1,
      interests_notify_max_per_day: 3,
    },
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

function render() {
  return renderWithProviders(<InterestsSettings lng="en" />);
}

const DELETE = 'interests.delete';
const BLOCK = 'interests.block';
const REACTIVATE = 'interests.reactivate';

/**
 * Interests are grouped into collapsed accordion sections (one per category,
 * plus dedicated dormant/blocked ones), so a row is only reachable after the
 * user opens its section.
 */
async function openSection(user: ReturnType<typeof render>['user'], name: RegExp) {
  await user.click(await screen.findByRole('button', { name }));
}

beforeEach(() => vi.clearAllMocks());

describe('InterestsSettings — list', () => {
  it('shows a loading indicator while interests load', () => {
    useInterests.mockReturnValue(hook({ loading: true, interests: [] }));
    render();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('keeps a category collapsed until it is opened, then lists its interests', async () => {
    useInterests.mockReturnValue(hook());
    const { user } = render();
    expect(screen.queryByText('Quantum computing')).not.toBeInTheDocument();
    await openSection(user, /science/i);
    expect(await screen.findByText('Quantum computing')).toBeInTheDocument();
  });
});

describe('InterestsSettings — row actions', () => {
  it('deletes an interest by id', async () => {
    const deleteInterest = vi.fn().mockResolvedValue(undefined);
    useInterests.mockReturnValue(hook({ deleteInterest }));
    const { user } = render();
    await openSection(user, /science/i);
    await user.click(await screen.findByRole('button', { name: DELETE }));
    // The confirmation action carries the same label as the row trigger.
    const confirms = await screen.findAllByRole('button', { name: DELETE });
    await user.click(confirms[confirms.length - 1]);
    await waitFor(() => expect(deleteInterest).toHaveBeenCalledWith('i1'));
    expect(toast.success).toHaveBeenCalledWith('interests.delete_success');
  });

  it('reports a failed deletion', async () => {
    useInterests.mockReturnValue(
      hook({ deleteInterest: vi.fn().mockRejectedValue(new Error('boom')) })
    );
    const { user } = render();
    await openSection(user, /science/i);
    await user.click(await screen.findByRole('button', { name: DELETE }));
    // The confirmation action carries the same label as the row trigger.
    const confirms = await screen.findAllByRole('button', { name: DELETE });
    await user.click(confirms[confirms.length - 1]);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('interests.delete_error'));
  });

  it('words a block differently from ordinary feedback', async () => {
    const submitFeedback = vi.fn().mockResolvedValue(undefined);
    useInterests.mockReturnValue(hook({ submitFeedback }));
    const { user } = render();
    await openSection(user, /science/i);
    await user.click(await screen.findByRole('button', { name: BLOCK }));
    await waitFor(() => expect(submitFeedback).toHaveBeenCalledWith('i1', 'block'));
    // A standing refusal gets its own confirmation, not the generic one.
    expect(toast.success).toHaveBeenCalledWith('interests.blocked_success');
    expect(toast.success).not.toHaveBeenCalledWith('interests.feedback_success');
  });

  it('reports a failed feedback submission', async () => {
    useInterests.mockReturnValue(
      hook({ submitFeedback: vi.fn().mockRejectedValue(new Error('boom')) })
    );
    const { user } = render();
    await openSection(user, /science/i);
    await user.click(await screen.findByRole('button', { name: BLOCK }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('interests.feedback_error'));
  });

  it('reactivates a dormant interest', async () => {
    const reactivateInterest = vi.fn().mockResolvedValue(undefined);
    useInterests.mockReturnValue(
      hook({ interests: [interest({ status: 'dormant' })], dormantCount: 1, reactivateInterest })
    );
    const { user } = render();
    await openSection(user, /dormant/);
    await user.click(await screen.findByRole('button', { name: REACTIVATE }));
    await waitFor(() => expect(reactivateInterest).toHaveBeenCalledWith('i1'));
    expect(toast.success).toHaveBeenCalledWith('interests.reactivate_success');
  });

  it('reports a failed reactivation', async () => {
    useInterests.mockReturnValue(
      hook({
        interests: [interest({ status: 'dormant' })],
        dormantCount: 1,
        reactivateInterest: vi.fn().mockRejectedValue(new Error('boom')),
      })
    );
    const { user } = render();
    await openSection(user, /dormant/);
    await user.click(await screen.findByRole('button', { name: REACTIVATE }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('interests.reactivate_error'));
  });
});

/**
 * Export stays a VISIBLE button at every size (owner request 2026-08-05):
 * folded into the phone "⋯" menu it read as absent. With export pinned and
 * nothing else foldable, the "⋯" trigger must not render at all.
 */
describe('InterestsSettings — pinned export', () => {
  it('keeps Export inline with no size gating and no "⋯" menu', async () => {
    render();
    const exportBtn = await screen.findByRole('button', { name: 'interests.export' });
    expect(exportBtn.closest('.hidden')).toBeNull();
    expect(screen.queryByRole('button', { name: 'common.more_actions' })).toBeNull();
  });
});
