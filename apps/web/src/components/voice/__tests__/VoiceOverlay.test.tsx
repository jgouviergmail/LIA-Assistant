/**
 * VoiceOverlay — visibility gating: hidden when disabled or idle, shown for an
 * active voice state.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders } from '@/__tests__/test-utils';
import { VoiceOverlay, type VoiceOverlayProps } from '../VoiceOverlay';

function props(over: Partial<VoiceOverlayProps> = {}): VoiceOverlayProps {
  return {
    isEnabled: true,
    state: 'listening',
    onTap: vi.fn(),
    onStop: vi.fn(),
    onDisable: vi.fn(),
    ...over,
  };
}

describe('VoiceOverlay', () => {
  it('renders nothing when voice mode is disabled', () => {
    const { container } = renderWithProviders(<VoiceOverlay {...props({ isEnabled: false })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing in the idle state', () => {
    const { container } = renderWithProviders(<VoiceOverlay {...props({ state: 'idle' })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the overlay for an active voice state', () => {
    const { container } = renderWithProviders(<VoiceOverlay {...props({ state: 'listening' })} />);
    expect(container).not.toBeEmptyDOMElement();
  });
});
