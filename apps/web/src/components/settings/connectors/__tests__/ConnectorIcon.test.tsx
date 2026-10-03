/**
 * ConnectorIcon — emoji vs icon vs unknown-fallback rendering.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { LIVE_PROVIDERS } from '@/lib/live/providers';

import { ConnectorIcon } from '../ConnectorIcon';
import { CONNECTOR_ICONS } from '../constants';

describe('ConnectorIcon', () => {
  it('renders an emoji labelled by the connector type for a known emoji connector', () => {
    renderWithProviders(<ConnectorIcon connectorType="google_calendar" />);
    expect(screen.getByRole('img', { name: 'google_calendar' })).toHaveTextContent('📅');
  });

  it('renders an icon (not an emoji) for an icon-only connector', () => {
    const { container } = renderWithProviders(<ConnectorIcon connectorType="google_places" />);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(container.querySelector('svg')).not.toBeNull();
  });

  it('falls back to a default icon for an unknown connector', () => {
    const { container } = renderWithProviders(<ConnectorIcon connectorType="unknown_xyz" />);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(container.querySelector('svg')).not.toBeNull();
  });

  it.each(LIVE_PROVIDERS.map(p => p.connectorType))(
    'gives the live connector %s its own microphone rather than the generic fallback',
    connectorType => {
      expect(CONNECTOR_ICONS[connectorType]).toBeDefined();
      renderWithProviders(<ConnectorIcon connectorType={connectorType} />);
      expect(screen.getByRole('img', { name: connectorType })).toHaveTextContent('🎙️');
    }
  );
});
