/**
 * ErrorConnectorCard — the error status display and the reconnect action.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { ErrorConnectorCard } from '../ErrorConnectorCard';
import { makeConnector } from '@/__tests__/factories';
import type { Connector } from '../types';

const t = (k: string) => k;

function connector(over: Partial<Connector> = {}): Connector {
  return makeConnector({ connector_type: 'gmail', status: 'error', ...over });
}

describe('ErrorConnectorCard', () => {
  it('shows the error status and reconnects on click', async () => {
    const onReconnect = vi.fn();
    const { user } = renderWithProviders(
      <ErrorConnectorCard
        connector={connector()}
        t={t}
        reconnecting={false}
        onReconnect={onReconnect}
      />
    );
    expect(screen.getByText('settings.connectors.health.error_status')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /reconnect/i }));
    expect(onReconnect).toHaveBeenCalledWith('gmail');
  });

  it('disables the reconnect button while reconnecting', () => {
    renderWithProviders(
      <ErrorConnectorCard connector={connector()} t={t} reconnecting onReconnect={vi.fn()} />
    );
    expect(screen.getByRole('button', { name: /reconnect/i })).toBeDisabled();
  });
});
