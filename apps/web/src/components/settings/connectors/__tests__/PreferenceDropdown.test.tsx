/**
 * PreferenceDropdown — the loading, error (with retry) and ready states of the
 * connector preference picker.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { useConnectorItems } = vi.hoisted(() => ({ useConnectorItems: vi.fn() }));
vi.mock('../hooks/useConnectorItems', () => ({ useConnectorItems }));

import { PreferenceDropdown } from '../PreferenceDropdown';
import { makeConnector } from '@/__tests__/factories';
import type { useConnectorItems as useConnectorItemsFn } from '../hooks/useConnectorItems';

const t = (k: string) => k;
const connector = makeConnector();

type ItemsHook = ReturnType<typeof useConnectorItemsFn>;
function hook(over: Partial<ItemsHook> = {}): ItemsHook {
  return { items: [], loading: false, error: false, refetch: vi.fn(), ...over };
}

beforeEach(() => vi.clearAllMocks());

describe('PreferenceDropdown', () => {
  it('shows a loading indicator while items load', () => {
    useConnectorItems.mockReturnValue(hook({ loading: true }));
    renderWithProviders(
      <PreferenceDropdown
        connector={connector}
        savedValue=""
        saving={false}
        t={t}
        onSelect={vi.fn()}
      />
    );
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('shows an error with a retry that refetches', async () => {
    const refetch = vi.fn();
    useConnectorItems.mockReturnValue(hook({ error: true, refetch }));
    const { user } = renderWithProviders(
      <PreferenceDropdown
        connector={connector}
        savedValue=""
        saving={false}
        t={t}
        onSelect={vi.fn()}
      />
    );
    expect(screen.getByText('settings.connectors.preferences.fetch_error')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /refresh/i }));
    expect(refetch).toHaveBeenCalled();
  });

  it('renders the select combobox once items are ready', () => {
    useConnectorItems.mockReturnValue(hook({ items: [{ name: 'Work', isDefault: true }] }));
    renderWithProviders(
      <PreferenceDropdown
        connector={connector}
        savedValue="Work"
        saving={false}
        t={t}
        onSelect={vi.fn()}
      />
    );
    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });
});
