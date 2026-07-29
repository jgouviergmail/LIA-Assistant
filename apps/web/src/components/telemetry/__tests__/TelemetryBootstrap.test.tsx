/**
 * TelemetryBootstrap / TrackView (ADR-178 Phase 4).
 *
 * What must hold:
 * - TrackView emits its funnel event exactly once on mount (flag on);
 * - the PWA install signals are wired globally (arbitration c);
 * - everything stays inert when the flag is off.
 */

import { render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { TelemetryBootstrap, TrackView } from '@/components/telemetry/TelemetryBootstrap';

describe('TelemetryBootstrap', () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    fetchMock.mockClear();
  });

  it('TrackView emits one funnel event on mount when enabled', () => {
    vi.stubEnv('NEXT_PUBLIC_PRODUCT_TELEMETRY', 'true');
    vi.stubGlobal('fetch', fetchMock);
    render(<TrackView event="landing_view" />);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      events: [{ kind: 'event', event_type: 'landing_view' }],
    });
  });

  it('TrackView stays inert when the flag is off', () => {
    vi.stubGlobal('fetch', fetchMock);
    render(<TrackView event="landing_view" />);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('emits pwa_install_prompt / pwa_installed on the window signals', () => {
    vi.stubEnv('NEXT_PUBLIC_PRODUCT_TELEMETRY', 'true');
    vi.stubGlobal('fetch', fetchMock);
    render(<TelemetryBootstrap />);
    window.dispatchEvent(new Event('beforeinstallprompt'));
    window.dispatchEvent(new Event('appinstalled'));
    const bodies = fetchMock.mock.calls.map(call => JSON.parse(call[1].body));
    expect(bodies).toContainEqual({
      events: [{ kind: 'event', event_type: 'pwa_install_prompt' }],
    });
    expect(bodies).toContainEqual({
      events: [{ kind: 'event', event_type: 'pwa_installed' }],
    });
  });

  it('unmount removes the PWA listeners (no leak, no late emission)', () => {
    vi.stubEnv('NEXT_PUBLIC_PRODUCT_TELEMETRY', 'true');
    vi.stubGlobal('fetch', fetchMock);
    const { unmount } = render(<TelemetryBootstrap />);
    unmount();
    window.dispatchEvent(new Event('beforeinstallprompt'));
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
