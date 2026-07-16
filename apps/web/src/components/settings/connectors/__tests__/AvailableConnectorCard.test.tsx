/**
 * AvailableConnectorCard — connect action and the mutual-exclusivity blocked state.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { AvailableConnectorCard } from '../AvailableConnectorCard';

describe('AvailableConnectorCard', () => {
  it('renders the label and description and connects on click', async () => {
    const onConnect = vi.fn();
    const { user } = renderWithProviders(
      <AvailableConnectorCard
        connectorType="google_calendar"
        label="Google Calendar"
        description="Sync your events"
        onConnect={onConnect}
      />
    );
    expect(screen.getByText('Google Calendar')).toBeInTheDocument();
    expect(screen.getByText('Sync your events')).toBeInTheDocument();
    await user.click(screen.getByRole('button'));
    expect(onConnect).toHaveBeenCalledTimes(1);
  });

  it('disables the connect button and shows the reason when blocked', async () => {
    const onConnect = vi.fn();
    const { user } = renderWithProviders(
      <AvailableConnectorCard
        connectorType="apple_calendar"
        label="Apple Calendar"
        description="desc"
        onConnect={onConnect}
        isBlocked
        blockedMessage="Blocked because Google Calendar is active"
      />
    );
    expect(screen.getByText('Blocked because Google Calendar is active')).toBeInTheDocument();
    expect(screen.getByRole('button')).toBeDisabled();
    await user.click(screen.getByRole('button'));
    expect(onConnect).not.toHaveBeenCalled();
  });
});
