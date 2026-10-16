/**
 * TimezoneSelector — once mounted and the timezone list has loaded, it renders
 * the searchable picker.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { act } from '@testing-library/react';
import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get } }));
const { mutate, mutationOptions, toast } = vi.hoisted(() => ({
  mutate: vi.fn(),
  mutationOptions: {
    current: null as null | { onSuccess: (user: { timezone: string }) => void | Promise<void> },
  },
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: (options: NonNullable<typeof mutationOptions.current>) => {
    mutationOptions.current = options;
    return { mutate, loading: false };
  },
}));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { info: vi.fn(), error: vi.fn(), warn: vi.fn(), debug: vi.fn() },
}));

import { TimezoneSelector } from '../TimezoneSelector';

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({ user: { id: 'u1', timezone: 'Europe/Paris' }, refreshUser: vi.fn() });
  get.mockResolvedValue({ Europe: ['Europe/Paris', 'Europe/London'] });
});

describe('TimezoneSelector', () => {
  it('keeps the confirmed timezone when refreshing the account fails after saving', async () => {
    const refreshUser = vi.fn().mockRejectedValue(new Error('Account refresh unavailable'));
    useAuth.mockReturnValue({ user: { id: 'u1', timezone: 'Europe/Paris' }, refreshUser });
    renderWithProviders(<TimezoneSelector lng="en" />);
    const london = await screen.findByRole('button', { name: /London.*Europe\/London/ });

    await act(async () => {
      await expect(
        Promise.resolve(mutationOptions.current?.onSuccess({ timezone: 'Europe/London' }))
      ).resolves.toBeUndefined();
    });

    expect(london).toHaveAttribute('aria-current', 'true');
    expect(refreshUser).toHaveBeenCalledOnce();
    expect(toast.error).not.toHaveBeenCalled();
    expect(mutate).not.toHaveBeenCalled();
  });

  it('renders the timezone search box once mounted', async () => {
    renderWithProviders(<TimezoneSelector lng="en" />);
    await waitFor(() =>
      expect(
        screen.getByPlaceholderText('settings.timezone.search_placeholder')
      ).toBeInTheDocument()
    );
  });

  it('fetches the timezone list on mount', async () => {
    renderWithProviders(<TimezoneSelector lng="en" />);
    await waitFor(() => expect(get).toHaveBeenCalledWith('/users/timezones'));
  });
});

it('retains the confirmed timezone if persistence returns no result', async () => {
  mutate.mockResolvedValueOnce(undefined);
  const { user } = renderWithProviders(<TimezoneSelector lng="en" />);
  const london = await screen.findByRole('button', { name: /London.*Europe\/London/ });
  await user.click(london);
  expect(screen.getByRole('button', { name: /Paris.*Europe\/Paris/ })).toHaveAttribute(
    'aria-current',
    'true'
  );
  expect(london).not.toHaveAttribute('aria-current');
});
