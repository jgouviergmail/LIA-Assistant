/**
 * MemorySettings — the loading state of the memories manager.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { useMemories } = vi.hoisted(() => ({ useMemories: vi.fn() }));
vi.mock('@/hooks/useMemories', () => ({ useMemories }));
const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', () => ({ default: { patch: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { MemorySettings } from '../MemorySettings';
import type { useMemories as useMemoriesFn } from '@/hooks/useMemories';

type MemoriesHook = ReturnType<typeof useMemoriesFn>;

function hook(over: Partial<MemoriesHook> = {}) {
  return {
    memories: [],
    total: 0,
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

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({ user: { id: 'u1', memory_enabled: true }, refreshUser: vi.fn() });
});

describe('MemorySettings', () => {
  it('shows a loading spinner while memories load', () => {
    useMemories.mockReturnValue(hook({ loading: true }));
    renderWithProviders(<MemorySettings lng="en" collapsible={false} />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});
