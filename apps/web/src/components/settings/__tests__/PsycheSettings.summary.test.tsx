import { StrictMode } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';
import { act, renderWithProviders, screen } from '@/__tests__/test-utils';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'one' } }) }));
vi.mock('@/lib/api-client', async original => ({
  ...(await original<typeof import('@/lib/api-client')>()),
  default: { get },
}));
vi.mock('@/hooks/usePsyche', () => ({
  usePsyche: () => ({
    settings: {
      psyche_enabled: true,
      psyche_display_avatar: true,
      psyche_sensitivity: 50,
      psyche_stability: 50,
    },
    state: {},
    error: null,
    settingsError: null,
    isLoading: false,
    isUpdatingSettings: false,
    isResetting: false,
    updateSettings: vi.fn(),
    resetPsyche: vi.fn(),
    refetchState: vi.fn(),
    refetchSettings: vi.fn(),
  }),
}));
vi.mock('@/components/psyche/PsycheStateSummary', () => ({
  PsycheStateSummary: ({ summary }: { summary?: React.ReactNode }) => <>{summary}</>,
}));
import { PsycheSettings } from '../PsycheSettings';

beforeEach(() => {
  get.mockReset();
  get.mockImplementation(async (endpoint: string) =>
    endpoint === '/psyche/summary' ? { summary: 'Voluntarily generated point' } : []
  );
});
const summaryReads = () => get.mock.calls.filter(([endpoint]) => endpoint === '/psyche/summary');
it('loads once on arrival, stays closed across rerender and reads the server-cached point on reopening', async () => {
  const { user, rerender } = renderWithProviders(
    <StrictMode>
      <PsycheSettings lng="en" />
    </StrictMode>
  );
  expect(await screen.findByText('Voluntarily generated point')).toBeVisible();
  expect(summaryReads()).toHaveLength(1);
  expect(get).toHaveBeenCalledWith(
    '/psyche/summary',
    expect.objectContaining({ signal: expect.any(AbortSignal) })
  );
  await user.click(screen.getByText('psyche.presentation.point'));
  expect(screen.queryByText('Voluntarily generated point')).not.toBeInTheDocument();
  rerender(
    <StrictMode>
      <PsycheSettings lng="en" />
    </StrictMode>
  );
  await act(async () => {});
  expect(screen.queryByText('Voluntarily generated point')).not.toBeInTheDocument();
  expect(screen.getByText('psyche.presentation.point').closest('details')).not.toHaveAttribute(
    'open'
  );
  expect(summaryReads()).toHaveLength(1);
  await user.click(screen.getByText('psyche.presentation.point'));
  expect(await screen.findByText('Voluntarily generated point')).toBeVisible();
  expect(summaryReads()).toHaveLength(2);
});
