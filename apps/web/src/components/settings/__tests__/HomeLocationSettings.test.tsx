/**
 * HomeLocationSettings — the loading state, saving a typed address (PUT), and
 * clearing an existing home location (DELETE).
 *
 * Demonstrates the multi-endpoint data pattern: `useApiQuery` routed by endpoint
 * and `useApiMutation` routed by HTTP method.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { dataQuery, queryResult, loadingQuery, mutationResult } from '@/__tests__/api-mocks';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));
const { useApiMutation } = vi.hoisted(() => ({ useApiMutation: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation }));
const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { info: vi.fn(), error: vi.fn(), warn: vi.fn(), debug: vi.fn() },
}));

import { HomeLocationSettings } from '../HomeLocationSettings';

const setHome = vi.fn();
const clearHome = vi.fn();

function routeQueries(homeLocation: unknown, opts: { loading?: boolean } = {}) {
  useApiQuery.mockImplementation((endpoint: string) => {
    if (endpoint === '/connectors') {
      if (opts.loading) return loadingQuery();
      return dataQuery({
        connectors: [{ id: 'c1', connector_type: 'google_places', status: 'active' }],
      });
    }
    if (endpoint === '/users/me/home-location') {
      if (opts.loading) return loadingQuery();
      return queryResult({ data: homeLocation, setData: vi.fn() });
    }
    return queryResult();
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({ user: { id: 'u1' } });
  useApiMutation.mockImplementation((opts: { method: string }) =>
    mutationResult({ mutate: opts.method === 'DELETE' ? clearHome : setHome })
  );
});

describe('HomeLocationSettings', () => {
  it('shows a loading spinner while the queries resolve', () => {
    routeQueries(null, { loading: true });
    renderWithProviders(<HomeLocationSettings lng="en" collapsible={false} />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('keeps the save button disabled until an address is typed, then saves it', async () => {
    routeQueries(null);
    const { user } = renderWithProviders(<HomeLocationSettings lng="en" collapsible={false} />);
    const save = screen.getByRole('button', { name: 'settings.location.home.save' });
    expect(save).toBeDisabled();

    await user.type(
      screen.getByPlaceholderText('settings.location.home.placeholder'),
      '10 Downing St'
    );
    expect(save).toBeEnabled();

    await user.click(save);
    await waitFor(() =>
      expect(setHome).toHaveBeenCalledWith('/users/me/home-location', {
        address: '10 Downing St',
        lat: 0,
        lon: 0,
      })
    );
  });

  it('clears an existing home location', async () => {
    routeQueries({ address: '221B Baker St', lat: 51.5, lon: -0.1 });
    const { user } = renderWithProviders(<HomeLocationSettings lng="en" collapsible={false} />);
    expect(screen.getByText('221B Baker St')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /settings.location.home.clear/ }));
    await waitFor(() =>
      expect(clearHome).toHaveBeenCalledWith('/users/me/home-location', undefined)
    );
  });
});
