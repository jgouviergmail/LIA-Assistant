/**
 * HapticsSettings — a sensory control of its own.
 *
 * `prefers-reduced-motion` is about ANIMATION; it says nothing about touch,
 * and someone may want a still interface with tactile confirmation (or the
 * reverse). Deriving one from the other would decide for them.
 *
 * The property that matters most: where the device cannot vibrate, the section
 * must not render at all. A switch that changes nothing is worse than no
 * switch — it invites the reader to fix something that was never broken.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { HAPTICS_ENABLED_KEY } from '@/lib/haptics';
import { HapticsSettings } from '../HapticsSettings';

function withVibrate() {
  Object.defineProperty(navigator, 'vibrate', {
    configurable: true,
    writable: true,
    value: () => true,
  });
}

beforeEach(() => window.localStorage.clear());
afterEach(() => {
  Reflect.deleteProperty(navigator, 'vibrate');
  window.localStorage.clear();
});

describe('HapticsSettings', () => {
  it('renders nothing where the device cannot vibrate', () => {
    // iOS Safari, and every desktop.
    const { container } = renderWithProviders(<HapticsSettings lng="en" collapsible={false} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('offers a named switch, on by default, where it can', () => {
    withVibrate();
    renderWithProviders(<HapticsSettings lng="en" collapsible={false} />);

    const toggle = screen.getByRole('switch', { name: 'settings.haptics.label' });
    expect(toggle).toBeChecked();
  });

  it('records a refusal on this device', async () => {
    withVibrate();
    const { user } = renderWithProviders(<HapticsSettings lng="en" collapsible={false} />);

    await user.click(screen.getByRole('switch', { name: 'settings.haptics.label' }));

    expect(window.localStorage.getItem(HAPTICS_ENABLED_KEY)).toBe('off');
    expect(screen.getByRole('switch', { name: 'settings.haptics.label' })).not.toBeChecked();
  });

  it('reflects a preference stored on a previous visit', () => {
    withVibrate();
    window.localStorage.setItem(HAPTICS_ENABLED_KEY, 'off');

    renderWithProviders(<HapticsSettings lng="en" collapsible={false} />);

    expect(screen.getByRole('switch', { name: 'settings.haptics.label' })).not.toBeChecked();
  });
});

describe('HapticsSettings — on the server', () => {
  // `useSyncExternalStore` reads its SERVER snapshot when there is no client:
  // `navigator` and `localStorage` do not exist there. Those two snapshots are
  // what keeps the markup identical on both sides — read the capability
  // optimistically on the server and the first client paint would remove a
  // section React had just rendered, which is precisely a hydration mismatch.
  it('renders nothing, whatever the device turns out to be', () => {
    const html = renderToStaticMarkup(<HapticsSettings lng="en" collapsible={false} />);

    expect(html).toBe('');
  });

  it('renders nothing even where the runtime does expose vibrate', () => {
    // Guards the snapshot itself rather than the absence of the API: a server
    // snapshot delegating to `isHapticsSupported` would pass the test above by
    // accident and still break hydration on a phone.
    withVibrate();

    expect(renderToStaticMarkup(<HapticsSettings lng="en" collapsible={false} />)).toBe('');
  });
});
