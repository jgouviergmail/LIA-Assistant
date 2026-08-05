/**
 * MemorySettings — the memories manager: loading, the category sections that
 * stay collapsed until opened, pinning (whose confirmation wording follows the
 * previous state), and above all the **asymmetric deletion rule** — an ordinary
 * memory is deleted on the spot, a *pinned* one must be confirmed first. The
 * bulk deletion likewise distinguishes "wipe everything" from "keep the pinned
 * ones", with its own wording.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { makeUser } from '@/__tests__/factories';

const { useMemories } = vi.hoisted(() => ({ useMemories: vi.fn() }));
// The module also exports helpers the component renders with (getEmotionalEmoji);
// keep the real exports and swap only the hook.
vi.mock('@/hooks/useMemories', async importOriginal => {
  const actual = await importOriginal<typeof import('@/hooks/useMemories')>();
  return { ...actual, useMemories };
});
const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { patch } = vi.hoisted(() => ({ patch: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { patch } }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { MemorySettings } from '../MemorySettings';
import type { Memory, useMemories as useMemoriesFn } from '@/hooks/useMemories';

type MemoriesHook = ReturnType<typeof useMemoriesFn>;

function memory(over: Partial<Memory> = {}): Memory {
  return {
    id: 'm1',
    content: 'Prefers concise answers',
    category: 'preference',
    emotional_weight: 0.4,
    trigger_topic: 'style',
    usage_nuance: 'when answering',
    importance: 3,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    pinned: false,
    ...over,
  };
}

function hook(over: Partial<MemoriesHook> = {}) {
  return {
    memories: [memory()],
    total: 1,
    loading: false,
    creating: false,
    deleting: false,
    updating: false,
    deletingAll: false,
    createMemory: vi.fn(),
    deleteMemory: vi.fn(),
    updateMemory: vi.fn(),
    deleteAllMemories: vi.fn(),
    togglePin: vi.fn(),
    ...over,
  };
}

function render() {
  return renderWithProviders(<MemorySettings lng="en" collapsible={false} />);
}

/** Memories live in collapsed per-category sections. */
async function openCategory(user: ReturnType<typeof render>['user']) {
  await user.click(await screen.findByRole('button', { name: /preference/i }));
}

const DELETE = 'memories.delete';
const PIN = 'memories.pin';
const UNPIN = 'memories.unpin';

beforeEach(() => {
  vi.clearAllMocks();
  patch.mockResolvedValue({});
  useAuth.mockReturnValue({
    user: makeUser({ memory_enabled: true }),
    refreshUser: vi.fn(),
  });
  useMemories.mockReturnValue(hook());
});

describe('MemorySettings — list', () => {
  it('shows a loading spinner while memories load', () => {
    useMemories.mockReturnValue(hook({ loading: true, memories: [] }));
    render();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('keeps a category collapsed until it is opened', async () => {
    const { user } = render();
    expect(screen.queryByText('Prefers concise answers')).not.toBeInTheDocument();
    await openCategory(user);
    expect(await screen.findByText('Prefers concise answers')).toBeInTheDocument();
  });
});

describe('MemorySettings — pinning', () => {
  it('pins an unpinned memory and confirms accordingly', async () => {
    const togglePin = vi.fn().mockResolvedValue(undefined);
    useMemories.mockReturnValue(hook({ memories: [memory({ pinned: false })], togglePin }));
    const { user } = render();
    await openCategory(user);
    await user.click(await screen.findByRole('button', { name: PIN }));
    await waitFor(() => expect(togglePin).toHaveBeenCalledWith('m1', true));
    expect(toast.success).toHaveBeenCalledWith('memories.pin_success');
  });

  it('unpins a pinned memory with the opposite wording', async () => {
    const togglePin = vi.fn().mockResolvedValue(undefined);
    useMemories.mockReturnValue(hook({ memories: [memory({ pinned: true })], togglePin }));
    const { user } = render();
    await openCategory(user);
    await user.click(await screen.findByRole('button', { name: UNPIN }));
    await waitFor(() => expect(togglePin).toHaveBeenCalledWith('m1', false));
    expect(toast.success).toHaveBeenCalledWith('memories.unpin_success');
  });

  it('reports a failed pin toggle', async () => {
    useMemories.mockReturnValue(
      hook({ memories: [memory()], togglePin: vi.fn().mockRejectedValue(new Error('boom')) })
    );
    const { user } = render();
    await openCategory(user);
    await user.click(await screen.findByRole('button', { name: PIN }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('memories.pin_error'));
  });
});

describe('MemorySettings — asymmetric deletion', () => {
  it('deletes an ordinary memory on the spot', async () => {
    const deleteMemory = vi.fn().mockResolvedValue(undefined);
    useMemories.mockReturnValue(hook({ memories: [memory({ pinned: false })], deleteMemory }));
    const { user } = render();
    await openCategory(user);
    await user.click(await screen.findByRole('button', { name: DELETE }));
    await waitFor(() => expect(deleteMemory).toHaveBeenCalledWith('m1'));
    expect(toast.success).toHaveBeenCalledWith('memories.delete_success');
  });

  it('never deletes a pinned memory without a confirmation', async () => {
    const deleteMemory = vi.fn().mockResolvedValue(undefined);
    useMemories.mockReturnValue(hook({ memories: [memory({ pinned: true })], deleteMemory }));
    const { user } = render();
    await openCategory(user);
    await user.click(await screen.findByRole('button', { name: DELETE }));
    // The click only arms the confirmation — nothing is destroyed yet.
    expect(deleteMemory).not.toHaveBeenCalled();
  });

  it('reports a failed deletion', async () => {
    useMemories.mockReturnValue(
      hook({
        memories: [memory({ pinned: false })],
        deleteMemory: vi.fn().mockRejectedValue(new Error('boom')),
      })
    );
    const { user } = render();
    await openCategory(user);
    await user.click(await screen.findByRole('button', { name: DELETE }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('memories.delete_error'));
  });
});

describe('MemorySettings — memory switch', () => {
  it('persists the memory preference and refreshes the user', async () => {
    const ctx = { user: makeUser({ memory_enabled: true }), refreshUser: vi.fn() };
    useAuth.mockReturnValue(ctx);
    const { user } = render();
    await user.click(screen.getByRole('switch'));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/auth/me/memory-preference', { memory_enabled: false })
    );
    expect(ctx.refreshUser).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith('memories.disabled_success');
  });

  it('reports a failed preference change', async () => {
    patch.mockRejectedValue(new Error('boom'));
    const { user } = render();
    await user.click(screen.getByRole('switch'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('common.error'));
  });
});

/**
 * Export stays a VISIBLE button at every size (owner request 2026-08-05):
 * folded into the phone "⋯" menu it read as absent. With export pinned and
 * nothing else foldable, the "⋯" trigger must not render at all.
 */
describe('MemorySettings — pinned export', () => {
  it('keeps Export inline with no size gating and no "⋯" menu', async () => {
    render();
    const exportBtn = await screen.findByRole('button', { name: 'memories.export' });
    expect(exportBtn.closest('.hidden')).toBeNull();
    expect(screen.queryByRole('button', { name: 'common.more_actions' })).toBeNull();
  });
});
