/**
 * PersonalitySettings — the loading state, the personality list with its current
 * selection, and switching personality (success refreshes psyche + toasts;
 * failure toasts an error).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { usePersonality } = vi.hoisted(() => ({ usePersonality: vi.fn() }));
vi.mock('@/hooks/usePersonality', () => ({ usePersonality }));

const { updateFromFullState } = vi.hoisted(() => ({ updateFromFullState: vi.fn() }));
vi.mock('@/stores/psycheStore', () => ({
  usePsycheStore: { getState: () => ({ updateFromFullState }) },
}));

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get } }));

const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { PersonalitySettings } from '../PersonalitySettings';
import type { usePersonality as usePersonalityFn } from '@/hooks/usePersonality';

type PersonalityHook = ReturnType<typeof usePersonalityFn>;

const PERSONALITIES = [
  { id: 'p1', title: 'Companion', description: 'Warm', emoji: '😊', is_default: true },
  { id: 'p2', title: 'Analyst', description: 'Precise', emoji: '🔬', is_default: false },
];

function hook(over: Partial<PersonalityHook> = {}) {
  return {
    personalities: PERSONALITIES,
    currentPersonality: PERSONALITIES[0],
    loading: false,
    updating: false,
    updatePersonality: vi.fn().mockResolvedValue(undefined),
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue({});
});

describe('PersonalitySettings', () => {
  it('shows a loading indicator while personalities load', () => {
    usePersonality.mockReturnValue(hook({ loading: true, personalities: [] }));
    renderWithProviders(<PersonalitySettings lng="en" />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('lists every personality as a selectable option', () => {
    usePersonality.mockReturnValue(hook());
    renderWithProviders(<PersonalitySettings lng="en" />);
    expect(screen.getByRole('button', { name: 'Companion' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Analyst' })).toBeInTheDocument();
  });

  it('switching personality persists it, refreshes psyche and toasts success', async () => {
    const updatePersonality = vi.fn().mockResolvedValue(undefined);
    usePersonality.mockReturnValue(hook({ updatePersonality }));
    const { user } = renderWithProviders(<PersonalitySettings lng="en" />);
    await user.click(screen.getByRole('button', { name: 'Analyst' }));
    expect(updatePersonality).toHaveBeenCalledWith('p2');
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(updateFromFullState).toHaveBeenCalled());
  });

  it('toasts an error when the personality update fails', async () => {
    const updatePersonality = vi.fn().mockRejectedValue(new Error('boom'));
    usePersonality.mockReturnValue(hook({ updatePersonality }));
    const { user } = renderWithProviders(<PersonalitySettings lng="en" />);
    await user.click(screen.getByRole('button', { name: 'Analyst' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });
});
