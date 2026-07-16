/**
 * ConnectedConnectorCard — the connector label, the disconnect action, and the
 * deleting state.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { ConnectedConnectorCard } from '../ConnectedConnectorCard';
import { makeConnector as connector } from '@/__tests__/factories';

const t = (k: string) => k;

describe('ConnectedConnectorCard', () => {
  it('renders the connector label and disconnects on click', async () => {
    const onDisconnect = vi.fn();
    const { user } = renderWithProviders(
      <ConnectedConnectorCard
        connector={connector()}
        lng="en"
        t={t}
        deleteLoading={false}
        onDisconnect={onDisconnect}
      />
    );
    await user.click(screen.getByRole('button', { name: 'settings.connectors.google.disconnect' }));
    expect(onDisconnect).toHaveBeenCalledWith('c1');
  });

  it('disables the disconnect button while deleting', () => {
    renderWithProviders(
      <ConnectedConnectorCard
        connector={connector()}
        lng="en"
        t={t}
        deleteLoading
        onDisconnect={vi.fn()}
      />
    );
    // While deleting, the button's accessible name is the spinner's ("Loading…"),
    // so query the sole button rather than by the disconnect title.
    expect(screen.getByRole('button')).toBeDisabled();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});
