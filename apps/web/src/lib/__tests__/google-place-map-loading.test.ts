import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadPlaceMaps } from '../google-place-map';
import { loadMapsSdk } from '../google-maps-sdk';

vi.mock('../google-maps-sdk', () => ({ loadMapsSdk: vi.fn(), mapFailures: new Set() }));
const map = {
  Map: vi.fn(),
  Polyline: vi.fn(),
  LatLngBounds: vi.fn(),
  MapTypeControlStyle: { DROPDOWN_MENU: 1 },
  event: { clearInstanceListeners: vi.fn() },
};
afterEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
});
describe('bounded marker library loading', () => {
  it('does not construct a map when the marker API is absent', async () => {
    vi.mocked(loadMapsSdk).mockResolvedValue(map);
    await expect(loadPlaceMaps('public')).rejects.toThrow('Marker library unavailable');
    expect(map.Map).not.toHaveBeenCalled();
  });
  it('bounds an offline marker-library request without constructing or billing', async () => {
    vi.useFakeTimers();
    vi.mocked(loadMapsSdk).mockResolvedValue({
      ...map,
      importLibrary: () => new Promise(() => {}),
    });
    const loading = loadPlaceMaps('public');
    const refused = expect(loading).rejects.toThrow('Marker library unavailable');
    await vi.advanceTimersByTimeAsync(10001);
    await refused;
    expect(map.Map).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});
