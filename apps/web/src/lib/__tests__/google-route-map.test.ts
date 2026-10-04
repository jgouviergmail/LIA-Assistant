import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { MapsLibrary, MapsMap, MapsBounds } from '../google-route-map';
import type { MapPoint } from '../route-map-data';

const instances: FakeMap[] = [],
  lines: FakePolyline[] = [];
class FakeMap implements MapsMap {
  fitBounds = vi.fn<(bounds: MapsBounds, padding: number) => void>();
  setOptions = vi.fn<(options: Record<string, unknown>) => void>();
  constructor() {
    instances.push(this);
  }
}
class FakeBounds implements MapsBounds {
  points: MapPoint[] = [];
  extend(point: MapPoint) {
    this.points.push(point);
  }
}
class FakePolyline {
  setMap = vi.fn();
  setOptions = vi.fn();
  callback: (() => void) | undefined;
  remove = vi.fn();
  constructor(public options: Record<string, unknown>) {
    lines.push(this);
  }
  addListener(_event: 'click', callback: () => void) {
    this.callback = callback;
    return { remove: this.remove };
  }
}
const maps: MapsLibrary = {
  MapTypeControlStyle: { DROPDOWN_MENU: 1 },
  Map: FakeMap,
  Polyline: FakePolyline,
  LatLngBounds: FakeBounds,
  event: { clearInstanceListeners: vi.fn() },
};
function sdkCallback() {
  const script = document.head.querySelector<HTMLScriptElement>(
    'script[src*="maps.googleapis.com"]'
  );
  const callback = script && new URL(script.src).searchParams.get('callback')?.split('.')[1];
  if (callback) window.liaRouteMapsCallbacks?.[callback]?.();
}
beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => null);
});
const data = {
  primary_id: 'route-1',
  omitted_count: 0,
  routes: [
    {
      id: 'route-0',
      path: [
        { lat: 0, lng: 0 },
        { lat: 1, lng: 1 },
      ],
      duration_seconds: 0,
      distance_meters: 0,
    },
    {
      id: 'route-1',
      path: [
        { lat: 0, lng: 0 },
        { lat: 2, lng: 2 },
      ],
      duration_seconds: 180,
      distance_meters: 1200,
    },
  ],
};
afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  vi.resetModules();
  instances.length = 0;
  lines.length = 0;
  delete window.google;
  delete window.liaRouteMapsCallbacks;
  delete window.gm_authFailure;
  document.head
    .querySelectorAll('script[src*="maps.googleapis.com"]')
    .forEach(script => script.remove());
});
describe('one SDK, exact local overlays', () => {
  it('shares pending initialization and rejects changing the public key mid-page', async () => {
    const { loadRouteMaps } = await import('../google-route-map');
    const first = loadRouteMaps('public-key');
    const second = loadRouteMaps('public-key');
    expect(first).toBe(second);
    expect(document.head.querySelectorAll('script[src*="maps.googleapis.com"]')).toHaveLength(1);
    await expect(loadRouteMaps('different-key')).rejects.toThrow('configuration changed');
    window.google = { maps };
    sdkCallback();
    await expect(first).resolves.toBe(maps);
    expect(loadRouteMaps('public-key')).toBe(first);
  });
  it('times out without leaving a callback or a script', async () => {
    vi.useFakeTimers();
    const { loadRouteMaps } = await import('../google-route-map');
    const loading = loadRouteMaps('key');
    const witness = expect(loading).rejects.toThrow('unavailable');
    await vi.advanceTimersByTimeAsync(15001);
    await witness;
    expect(Object.keys(window.liaRouteMapsCallbacks ?? {})).toHaveLength(0);
    expect(document.head.querySelector('script[src*="maps.googleapis.com"]')).toBeNull();
  });
  it('draws all exact paths, fits the real primary and clears listeners/overlays on disposal', async () => {
    const { mountRouteMap } = await import('../google-route-map');
    const clicked = vi.fn();
    const element = document.createElement('div');
    document.body.append(element);
    const controller = mountRouteMap(maps, element, data, clicked, vi.fn());
    expect(lines.map(line => line.options.path)).toEqual(data.routes.map(route => route.path));
    const bounds: unknown = instances[0].fitBounds.mock.calls[0][0];
    expect(bounds).toMatchObject({ points: data.routes[1].path });
    lines[0].callback?.();
    expect(clicked).toHaveBeenCalledWith('route-0');
    controller.select('route-0');
    expect(lines[0].setOptions).toHaveBeenLastCalledWith(
      expect.objectContaining({ strokeWeight: 6, zIndex: 2 })
    );
    expect(instances).toHaveLength(1);
    controller.destroy();
    expect(maps.event.clearInstanceListeners).toHaveBeenCalledWith(instances[0]);
    lines.forEach(line => {
      expect(line.remove).toHaveBeenCalledOnce();
      expect(line.setMap).toHaveBeenCalledWith(null);
    });
    element.remove();
  });
  it('does not let a late timed-out SDK callback settle a later attempt', async () => {
    vi.useFakeTimers();
    const { loadRouteMaps } = await import('../google-route-map');
    const first = loadRouteMaps('key');
    const firstCallback = new URL(
      document.head.querySelector<HTMLScriptElement>('script[src*="maps.googleapis.com"]')!.src
    ).searchParams.get('callback');
    const failed = expect(first).rejects.toThrow('unavailable');
    await vi.advanceTimersByTimeAsync(15001);
    await failed;
    let resolved = false;
    const next = loadRouteMaps('key');
    void next.then(() => {
      resolved = true;
    });
    const nextCallback = new URL(
      document.head.querySelector<HTMLScriptElement>('script[src*="maps.googleapis.com"]')!.src
    ).searchParams.get('callback');
    expect(nextCallback).not.toBe(firstCallback);
    window.google = { maps };
    await Promise.resolve();
    expect(resolved).toBe(false);
    sdkCallback();
    await expect(next).resolves.toBe(maps);
  });
  it('cleans the constructed map when a later overlay throws', async () => {
    const { mountRouteMap } = await import('../google-route-map');
    class BrokenLine extends FakePolyline {
      constructor(options: Record<string, unknown>) {
        if (lines.length) throw new Error('overlay');
        super(options);
      }
    }
    const constructed = vi.fn();
    expect(() =>
      mountRouteMap(
        { ...maps, Polyline: BrokenLine },
        document.createElement('div'),
        data,
        vi.fn(),
        vi.fn(),
        constructed
      )
    ).toThrow('overlay');
    expect(constructed).toHaveBeenCalledOnce();
    expect(lines[0].setMap).toHaveBeenCalledWith(null);
    expect(maps.event.clearInstanceListeners).toHaveBeenCalledWith(instances[0]);
  });
});
