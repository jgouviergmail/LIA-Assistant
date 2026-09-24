/**
 * UsagePreferencesSettings — the exchange rhythm (ADR-311).
 *
 * A native radio group showing the EFFECTIVE rhythm the API publishes (the
 * person's choice, else the instance default), a choice persisted through the
 * generic profile update then refreshed and toasted, the no-op re-selection,
 * the error toast, and the group disabled while a choice is being saved.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import { makeUser } from '@/__tests__/factories';
import type { User } from '@/lib/auth';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { patch } = vi.hoisted(() => ({ patch: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { patch } }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { UsagePreferencesSettings } from '../UsagePreferencesSettings';

const PREFIX = 'settings.usage_preferences.exchange_rhythm';
const OPTION = (rhythm: string) => `${PREFIX}.options.${rhythm}.label`;

function authed(over: Partial<User> = {}) {
  return {
    user: makeUser({ id: 'u1', exchange_rhythm: 'occasional', ...over }),
    refreshUser: vi.fn(),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  patch.mockResolvedValue({});
});

describe('UsagePreferencesSettings', () => {
  it('offers the two rhythms as one native radio group, the effective one checked', () => {
    useAuth.mockReturnValue(authed({ exchange_rhythm: 'frequent' }));
    renderWithProviders(<UsagePreferencesSettings lng="en" />);

    const group = screen.getByRole('group', { name: `${PREFIX}.legend` });
    expect(within(group).getAllByRole('radio')).toHaveLength(2);
    expect(screen.getByRole('radio', { name: OPTION('frequent') })).toBeChecked();
    expect(screen.getByRole('radio', { name: OPTION('occasional') })).not.toBeChecked();
  });

  it('describes each option with its own sentence', () => {
    useAuth.mockReturnValue(authed());
    renderWithProviders(<UsagePreferencesSettings lng="en" />);

    for (const rhythm of ['frequent', 'occasional']) {
      expect(screen.getByRole('radio', { name: OPTION(rhythm) })).toHaveAccessibleDescription(
        `${PREFIX}.options.${rhythm}.description`
      );
    }
  });

  it('choosing the other rhythm persists it on the profile, refreshes and toasts', async () => {
    const ctx = authed({ exchange_rhythm: 'occasional' });
    useAuth.mockReturnValue(ctx);
    const { user } = renderWithProviders(<UsagePreferencesSettings lng="en" />);

    await user.click(screen.getByRole('radio', { name: OPTION('frequent') }));

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/users/u1', { exchange_rhythm: 'frequent' })
    );
    expect(ctx.refreshUser).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith(`${PREFIX}.options.frequent.selected`);
  });

  it('re-choosing the current rhythm sends nothing', async () => {
    useAuth.mockReturnValue(authed({ exchange_rhythm: 'occasional' }));
    const { user } = renderWithProviders(<UsagePreferencesSettings lng="en" />);

    await user.click(screen.getByRole('radio', { name: OPTION('occasional') }));

    expect(patch).not.toHaveBeenCalled();
  });

  it('a failed update shows the error toast', async () => {
    patch.mockRejectedValue(new Error('boom'));
    useAuth.mockReturnValue(authed({ exchange_rhythm: 'occasional' }));
    const { user } = renderWithProviders(<UsagePreferencesSettings lng="en" />);

    await user.click(screen.getByRole('radio', { name: OPTION('frequent') }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('the group is disabled while a choice is being saved', async () => {
    let release: () => void = () => {};
    patch.mockReturnValue(new Promise<void>(resolve => (release = resolve)));
    useAuth.mockReturnValue(authed({ exchange_rhythm: 'occasional' }));
    const { user } = renderWithProviders(<UsagePreferencesSettings lng="en" />);

    await user.click(screen.getByRole('radio', { name: OPTION('frequent') }));

    await waitFor(() =>
      expect(screen.getByRole('group', { name: `${PREFIX}.legend` })).toBeDisabled()
    );
    release();
    await waitFor(() =>
      expect(screen.getByRole('group', { name: `${PREFIX}.legend` })).not.toBeDisabled()
    );
  });
});
