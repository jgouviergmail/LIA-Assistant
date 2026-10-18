import { describe, expect, it, vi } from 'vitest';
import { minimalPlaceBounds, mountPlaceMap } from '../google-place-map';
import type { MapsLibrary, MapsMap, MarkerLibrary } from '../google-maps-sdk';

const data = {
  version: 1 as const,
  omitted_count: 0,
  unlocated_count: 1,
  places: [
    {
      ref: 'a',
      label: 'East',
      url: 'https://www.google.com/maps/place/?q=a',
      position: { lat: 0, lng: 179.9 },
    },
    {
      ref: 'b',
      label: 'West',
      url: 'https://www.google.com/maps/place/?q=b',
      position: { lat: 1, lng: -179.9 },
    },
    {
      ref: 'c',
      label: 'Coincident',
      url: 'https://www.google.com/maps/place/?q=c',
      position: { lat: 0, lng: 179.9 },
    },
    { ref: 'd', label: 'Unlocated', url: 'https://www.google.com/maps/place/?q=d', position: null },
  ],
};
describe('native place markers', () => {
  it('fits the narrow antimeridian interval without changing source positions', () => {
    expect(minimalPlaceBounds(data.places.flatMap(p => (p.position ? [p.position] : [])))).toEqual({
      north: 1,
      south: 0,
      west: 179.9,
      east: -179.9,
    });
  });
  it('constructs once, retains coincident markers, reports construction and releases everything', () => {
    const instances: (EventTarget & { map: MapsMap | null; zIndex?: number })[] = [];
    const created = vi.fn(),
      selected = vi.fn();
    const map = { fitBounds: vi.fn(), setOptions: vi.fn() };
    const MapClass = vi.fn(function () {
      return map;
    });
    const maps: MapsLibrary = {
      Map: MapClass,
      Polyline: vi.fn(),
      MapTypeControlStyle: { DROPDOWN_MENU: 1 },
      LatLngBounds: vi.fn(function (value) {
        return { ...value, extend: vi.fn() };
      }),
      event: { clearInstanceListeners: vi.fn() },
    };
    const marker: MarkerLibrary = {
      AdvancedMarkerElement: class extends EventTarget {
        map = map;
        zIndex?: number;
        constructor(public options: Record<string, unknown>) {
          super();
          instances.push(this);
        }
      },
    };
    const element = document.createElement('div');
    const controller = mountPlaceMap(
      maps,
      marker,
      element,
      data,
      'configured',
      selected,
      vi.fn(),
      created
    );
    expect(MapClass).toHaveBeenCalledTimes(1);
    expect(MapClass).toHaveBeenCalledWith(
      element,
      expect.objectContaining({ mapId: 'configured', colorScheme: 'LIGHT' })
    );
    expect(created).toHaveBeenCalledOnce();
    expect(instances).toHaveLength(3);
    instances[1].dispatchEvent(new Event('gmp-click'));
    expect(selected).toHaveBeenLastCalledWith('b');
    controller.select('c');
    expect(instances[2].zIndex).toBeGreaterThan(instances[0].zIndex ?? 0);
    expect(MapClass).toHaveBeenCalledTimes(1);
    controller.destroy();
    expect(instances.every(instance => instance.map === null)).toBe(true);
    selected.mockClear();
    instances[1].dispatchEvent(new Event('gmp-click'));
    expect(selected).not.toHaveBeenCalled();
    expect(maps.event.clearInstanceListeners).toHaveBeenCalledWith(map);
  });
  it('bills the constructed map and clears partial markers if a later marker fails', () => {
    const map = { fitBounds: vi.fn(), setOptions: vi.fn() };
    const clear = vi.fn(),
      selected = vi.fn(),
      constructed = vi.fn();
    const instances: (EventTarget & { map: MapsMap | null })[] = [];
    const maps: MapsLibrary = {
      Map: vi.fn(function () {
        return map;
      }),
      Polyline: vi.fn(),
      MapTypeControlStyle: { DROPDOWN_MENU: 1 },
      LatLngBounds: vi.fn(),
      event: { clearInstanceListeners: clear },
    };
    const marker: MarkerLibrary = {
      AdvancedMarkerElement: class extends EventTarget {
        map: MapsMap | null = map;
        constructor() {
          super();
          if (instances.length) throw new Error('marker unavailable');
          instances.push(this);
        }
      },
    };
    const element = document.createElement('div');
    element.textContent = 'partial canvas';
    document.documentElement.classList.add('dark');
    try {
      expect(() =>
        mountPlaceMap(maps, marker, element, data, 'configured', selected, vi.fn(), constructed)
      ).toThrow('marker unavailable');
      expect(maps.Map).toHaveBeenCalledWith(
        element,
        expect.objectContaining({ colorScheme: 'DARK' })
      );
      expect(constructed).toHaveBeenCalledOnce();
      expect(instances[0].map).toBeNull();
      instances[0].dispatchEvent(new Event('gmp-click'));
      expect(selected).not.toHaveBeenCalled();
      expect(clear).toHaveBeenCalledWith(map);
      expect(element).toBeEmptyDOMElement();
    } finally {
      document.documentElement.classList.remove('dark');
    }
  });
});
