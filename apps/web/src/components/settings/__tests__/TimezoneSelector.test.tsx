/**
 * TimezoneSelector — once mounted and the timezone list has loaded, it renders
 * the searchable picker.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get } }));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate: vi.fn(), loading: false }),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { TimezoneSelector } from '../TimezoneSelector';

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({ user: { id: 'u1', timezone: 'Europe/Paris' }, refreshUser: vi.fn() });
  get.mockResolvedValue({ Europe: ['Europe/Paris', 'Europe/London'] });
});

describe('TimezoneSelector', () => {
  it('renders the timezone search box once mounted', async () => {
    renderWithProviders(<TimezoneSelector lng="en" collapsible={false} />);
    await waitFor(() =>
      expect(
        screen.getByPlaceholderText('settings.timezone.search_placeholder')
      ).toBeInTheDocument()
    );
  });

  it('fetches the timezone list on mount', async () => {
    renderWithProviders(<TimezoneSelector lng="en" collapsible={false} />);
    await waitFor(() => expect(get).toHaveBeenCalledWith('/users/timezones'));
  });
});
