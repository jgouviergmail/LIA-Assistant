/**
 * ConnectorHealthBanner — the persistent "still broken" surface.
 *
 * The modal already covers "look now". What is proved here is the property the
 * modal cannot have: while a connector is in ERROR the banner is present,
 * named, and one activation away from the fix — at every viewport, and without
 * a way to silence it that outlives the problem.
 *
 * Regression target (2026-07-30): five connectors in ERROR for a full day
 * while their owner believed everything worked, because the only surface that
 * ever said otherwise was a modal shown once, hours earlier.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { ConnectorHealthBanner } from '../ConnectorHealthBanner';
import type { ConnectorHealthItem } from '@/hooks/useConnectorHealth';

const t = (key: string, options?: Record<string, unknown>) =>
  options ? `${key}:${JSON.stringify(options)}` : key;

function item(over: Partial<ConnectorHealthItem> = {}): ConnectorHealthItem {
  return {
    id: 'c1',
    connector_type: 'google_calendar',
    display_name: 'Google Calendar',
    health_status: 'error',
    severity: 'critical',
    expires_in_minutes: null,
    authorize_url: '/connectors/google_calendar/authorize',
    ...over,
  };
}

function renderBanner(over: Partial<React.ComponentProps<typeof ConnectorHealthBanner>> = {}) {
  const props: React.ComponentProps<typeof ConnectorHealthBanner> = {
    connectors: [item()],
    lng: 'fr',
    t,
    reconnecting: false,
    onReconnect: vi.fn(),
    ...over,
  };
  return { props, ...renderWithProviders(<ConnectorHealthBanner {...props} />) };
}

describe('ConnectorHealthBanner', () => {
  it('renders nothing when every connector is healthy', () => {
    const { container } = renderBanner({ connectors: [] });

    expect(container).toBeEmptyDOMElement();
  });

  it('names the broken connector when exactly one is down', () => {
    renderBanner();

    expect(
      screen.getByText(/settings\.connectors\.health\.banner_one.*Google Calendar/)
    ).toBeInTheDocument();
  });

  it('counts them instead of naming one when several are down', () => {
    renderBanner({
      connectors: [item(), item({ id: 'c2', display_name: 'Gmail' })],
    });

    expect(
      screen.getByText(/settings\.connectors\.health\.banner_many.*"total":2/)
    ).toBeInTheDocument();
    expect(screen.queryByText(/Google Calendar/)).not.toBeInTheDocument();
  });

  it('never interpolates through i18next `count`', () => {
    // `count` is a plural SELECTOR: passing it makes i18next resolve
    // `banner_many_one`/`banner_many_other`, keys that do not exist in any of
    // the six locales. The bug is invisible in a mocked-`t` test unless the
    // option name itself is asserted.
    renderBanner({ connectors: [item(), item({ id: 'c2' })] });

    expect(screen.queryByText(/"count"/)).toBeNull();
  });

  it('exposes a named status region rather than an interrupting alert', () => {
    renderBanner();

    // `status` is polite: the condition lasts hours and must not preempt a
    // screen-reader user mid-sentence.
    const region = screen.getByRole('status', {
      name: 'settings.connectors.health.banner_label',
    });
    expect(region).toBeInTheDocument();
  });

  it('reconnects the single broken connector on activation', async () => {
    const onReconnect = vi.fn();
    const { user } = renderBanner({ onReconnect });

    await user.click(screen.getByRole('button', { name: /reconnect/i }));

    expect(onReconnect).toHaveBeenCalledWith('c1', '/connectors/google_calendar/authorize');
  });

  it('is operable with the keyboard alone', async () => {
    const onReconnect = vi.fn();
    const { user } = renderBanner({ onReconnect });

    await user.tab();
    expect(screen.getByRole('button', { name: /reconnect/i })).toHaveFocus();
    await user.keyboard('{Enter}');

    expect(onReconnect).toHaveBeenCalledTimes(1);
  });

  it('blocks a second submission while the redirect is in flight', async () => {
    const onReconnect = vi.fn();
    const { user } = renderBanner({ reconnecting: true, onReconnect });

    const button = screen.getByRole('button', {
      name: 'settings.connectors.health.reconnecting',
    });
    expect(button).toBeDisabled();
    await user.click(button);

    expect(onReconnect).not.toHaveBeenCalled();
  });

  it('sends to the connectors settings when several need attention', () => {
    renderBanner({
      connectors: [item(), item({ id: 'c2', display_name: 'Gmail' })],
    });

    const link = screen.getByRole('link', {
      name: 'settings.connectors.health.banner_manage',
    });
    // Deep link (ADR-172): the locale is carried and the section is targeted.
    expect(link).toHaveAttribute('href', expect.stringContaining('/fr/'));
    expect(link).toHaveAttribute('href', expect.stringContaining('connectors'));
  });

  it('publishes its height so the viewport-locked chat shell can subtract it', () => {
    // The chat shell is `h-[calc(100dvh - constant - var(--connector-banner-h))]`.
    // Without this variable the composer is pushed below the fold the moment a
    // connector breaks — the constant predates the banner and cannot know it.
    const observed: Element[] = [];
    const disconnect = vi.fn();
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(private cb: () => void) {}
        observe(el: Element) {
          observed.push(el);
          this.cb();
        }
        disconnect = disconnect;
        unobserve = vi.fn();
      }
    );

    const { unmount } = renderBanner();

    expect(observed).toHaveLength(1);
    expect(
      document.documentElement.style.getPropertyValue('--connector-banner-h')
    ).toMatch(/px$/);

    unmount();

    // Reconnected: the height it claimed goes with it, or the chat shell stays
    // permanently short.
    expect(disconnect).toHaveBeenCalled();
    expect(document.documentElement.style.getPropertyValue('--connector-banner-h')).toBe('');
    vi.unstubAllGlobals();
  });

  it('offers no way to dismiss it while the connector is still broken', () => {
    renderBanner();

    // Exactly one control: the fix. A "later" button would let the user
    // silence a condition that does not go away on its own — which is the
    // defect this banner exists to close.
    expect(screen.getAllByRole('button')).toHaveLength(1);
    expect(screen.queryByRole('button', { name: /dismiss|later|plus tard/i })).toBeNull();
  });
});
