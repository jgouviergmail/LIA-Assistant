import { describe, expect, it, vi } from 'vitest';
import { minimalPlaceBounds, mountPlaceMap } from '../google-place-map';
import type { MapsLibrary, MapsMap, MarkerLibrary } from '../google-maps-sdk';
import type { MapRoute } from '../route-map-data';
import type { PlacePositionData } from '../place-position-data';

function pinConstructor() {
  return vi.fn(function (options: { glyphText?: string }) {
    const pin = document.createElement('span');
    pin.textContent = options.glyphText ?? '';
    return Object.assign(pin, {
      glyphText: options.glyphText,
      background: '',
      borderColor: '',
      glyphColor: '',
    });
  });
}

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
    const instances: (HTMLElement & { map: MapsMap | null; zIndex?: number })[] = [];
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
      PinElement: pinConstructor(),
      AdvancedMarkerElement: vi.fn(function () {
        const pin = Object.assign(document.createElement('div'), { map, zIndex: 1 });
        instances.push(pin);
        return pin;
      }),
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
    const instances: (HTMLElement & { map: MapsMap | null })[] = [];
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
      PinElement: pinConstructor(),
      AdvancedMarkerElement: vi.fn(function () {
        if (instances.length) throw new Error('marker unavailable');
        const pin = Object.assign(document.createElement('div'), { map });
        instances.push(pin);
        return pin;
      }),
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

function detailsMap(source: PlacePositionData = data) {
  const map = { fitBounds: vi.fn(), setOptions: vi.fn() };
  const closeEvents = new EventTarget();
  const removedCloseListener = vi.fn();
  const popup = {
    setContent: vi.fn(),
    setOptions: vi.fn(),
    open: vi.fn(),
    close: vi.fn(() => {
      closeEvents.dispatchEvent(new Event('close'));
    }),
    addListener: vi.fn((event: 'close', callback: () => void) => {
      closeEvents.addEventListener(event, callback);
      return {
        remove() {
          closeEvents.removeEventListener(event, callback);
          removedCloseListener();
        },
      };
    }),
  };
  const line = { setMap: vi.fn(), setOptions: vi.fn(), addListener: vi.fn() };
  const instances: (HTMLElement & { map: MapsMap | null; zIndex?: number })[] = [];
  const maps = {
    Map: vi.fn(function () {
      return map;
    }),
    InfoWindow: vi.fn(function () {
      return popup;
    }),
    Polyline: vi.fn(function () {
      return line;
    }),
    MapTypeControlStyle: { DROPDOWN_MENU: 1 },
    LatLngBounds: vi.fn(function (value) {
      return { ...value, extend: vi.fn() };
    }),
    event: { clearInstanceListeners: vi.fn() },
  };
  const marker: MarkerLibrary = {
    PinElement: pinConstructor(),
    AdvancedMarkerElement: vi.fn(function (options: Record<string, unknown>) {
      const pin = Object.assign(document.createElement('div'), { map, zIndex: 1 });
      if (typeof options.title === 'string') pin.title = options.title;
      instances.push(pin);
      return pin;
    }),
  };
  const select = vi.fn();
  const element = document.createElement('div');
  element.style.setProperty('--color-primary', '#123456');
  element.style.setProperty('--color-primary-foreground', '#ffffff');
  element.style.setProperty('--color-background', '#fafafa');
  const controller = mountPlaceMap(
    maps,
    marker,
    element,
    source,
    'configured',
    select,
    vi.fn(),
    vi.fn()
  );
  return {
    map,
    popup,
    line,
    maps,
    instances,
    select,
    controller,
    marker,
    element,
    removedCloseListener,
    closeNative(source: 'button' | 'escape' = 'button') {
      if (source === 'button') closeEvents.dispatchEvent(new Event('closeclick'));
      closeEvents.dispatchEvent(new Event('close'));
    },
  };
}
const route: MapRoute = {
  id: 'route-0',
  path: [
    { lat: 10, lng: 178 },
    { lat: 0, lng: 179.9 },
  ],
  distance_meters: 1234,
  duration_seconds: 456,
};
describe('details and route on the existing place map', () => {
  it('renders original place numbers as distinct native pin DOM, preserving gaps and accessible titles', () => {
    const unlocated = data.places[3];
    const source = {
      ...data,
      unlocated_count: 2,
      places: [
        unlocated,
        data.places[0],
        data.places[1],
        { ...unlocated, ref: 'e' },
        data.places[2],
      ],
    };
    const { controller, marker, maps, instances, select } = detailsMap(source);
    expect(instances.map(instance => instance.textContent)).toEqual(['2', '3', '5']);
    expect(instances.map(instance => instance.title)).toEqual([
      '2. East',
      '3. West',
      '5. Coincident',
    ]);
    expect(marker.PinElement).toHaveBeenCalledTimes(3);
    for (const [index, number] of ['2', '3', '5'].entries()) {
      expect(marker.PinElement).toHaveBeenNthCalledWith(index + 1, {
        glyphText: number,
        background: '#123456',
        glyphColor: '#ffffff',
        borderColor: '#fafafa',
      });
      const visual = instances[index].firstElementChild;
      expect(visual).toHaveTextContent(number);
      expect(visual).toHaveAttribute('data-place-number', number);
      expect(visual).toHaveAttribute('aria-hidden', 'true');
      expect(marker.AdvancedMarkerElement).toHaveBeenNthCalledWith(
        index + 1,
        expect.objectContaining({ gmpClickable: true })
      );
    }
    expect(instances[0].firstElementChild).not.toBe(instances[1].firstElementChild);
    instances[1].dispatchEvent(new Event('gmp-click'));
    expect(select).toHaveBeenCalledExactlyOnceWith('b');
    controller.select('b');
    expect(instances[1].zIndex).toBe(10);
    expect(maps.Map).toHaveBeenCalledOnce();
    controller.destroy();
    expect(
      instances.every(instance => instance.map === null && instance.childElementCount === 0)
    ).toBe(true);
  });
  it('updates existing native pin colors from theme tokens and stops observing after destroy', async () => {
    const { controller, marker, element } = detailsMap();
    const first = vi.mocked(marker.PinElement).mock.results[0].value;
    expect(first.glyphText).toBe('1');
    element.style.setProperty('--color-primary', '#abcdef');
    element.style.setProperty('--color-primary-foreground', '#112233');
    element.style.setProperty('--color-background', '#010203');
    document.documentElement.classList.add('dark');
    await Promise.resolve();
    expect(first.background).toBe('#abcdef');
    expect(first.glyphColor).toBe('#112233');
    expect(first.borderColor).toBe('#010203');
    expect(first.textContent).toBe('1');
    expect(marker.PinElement).toHaveBeenCalledTimes(3);
    controller.destroy();
    element.style.setProperty('--color-primary', '#111111');
    document.documentElement.classList.remove('dark');
    await Promise.resolve();
    expect(first.background).toBe('#abcdef');
  });
  it('reuses one popup, passes real DOM and keeps marker/list selection on one map', () => {
    const { controller, maps, popup, instances, map, select } = detailsMap();
    const first = document.createElement('section');
    first.textContent = '<img src=x onerror="alert(1)">';
    const second = document.createElement('section');
    controller.showDetails('a', first);
    controller.showDetails('b', second);
    expect(maps.InfoWindow).toHaveBeenCalledOnce();
    expect(maps.InfoWindow).toHaveBeenCalledWith({ maxWidth: 440 });
    expect(maps.InfoWindow.mock.invocationCallOrder[0]).toBeLessThan(
      popup.open.mock.invocationCallOrder[0]
    );
    expect(popup.setContent).toHaveBeenNthCalledWith(1, first);
    expect(popup.setContent).toHaveBeenNthCalledWith(2, second);
    expect(popup.setOptions).toHaveBeenNthCalledWith(1, {
      ariaLabel: data.places[0].label,
      headerContent: undefined,
    });
    expect(popup.setOptions).toHaveBeenNthCalledWith(2, {
      ariaLabel: data.places[1].label,
      headerContent: undefined,
    });
    expect(popup.open).toHaveBeenLastCalledWith({ map, anchor: instances[1], shouldFocus: false });
    expect(first.querySelector('img')).toBeNull();
    instances[1].dispatchEvent(new Event('gmp-click'));
    expect(select).toHaveBeenLastCalledWith('b');
    controller.select('b');
    expect(map.setOptions).toHaveBeenLastCalledWith({ center: { lat: 1, lng: -179.9 }, zoom: 15 });
    controller.showDetails('d', first);
    expect(popup.open).toHaveBeenCalledTimes(2);
    controller.clearDetails();
    expect(popup.close).toHaveBeenCalledOnce();
    expect(popup.setContent).toHaveBeenLastCalledWith();
    expect(popup.setOptions).toHaveBeenLastCalledWith({ headerContent: undefined });
    expect(maps.Map).toHaveBeenCalledOnce();
    controller.destroy();
  });
  it.each(['button', 'escape'] as const)(
    'passes header DOM and binds %s closure to the current selection with one listener',
    source => {
      const { controller, popup, maps, closeNative, removedCloseListener } = detailsMap();
      const first = document.createElement('section');
      const second = document.createElement('section');
      const firstHeader = document.createElement('h2');
      const secondHeader = document.createElement('h2');
      secondHeader.textContent = '<img src=x onerror="alert(1)">';
      const closedFirst = vi.fn();
      const closedSecond = vi.fn();
      controller.showDetails('a', first, firstHeader, closedFirst);
      controller.showDetails('b', second, secondHeader, closedSecond);
      expect(popup.setOptions).toHaveBeenNthCalledWith(1, {
        ariaLabel: 'East',
        headerContent: firstHeader,
      });
      expect(popup.setOptions).toHaveBeenNthCalledWith(2, {
        ariaLabel: 'West',
        headerContent: secondHeader,
      });
      expect(popup.setContent).toHaveBeenLastCalledWith(second);
      expect(secondHeader.querySelector('img')).toBeNull();
      closeNative(source);
      expect(closedFirst).not.toHaveBeenCalled();
      expect(closedSecond).toHaveBeenCalledOnce();
      expect(popup.addListener).toHaveBeenCalledExactlyOnceWith('close', expect.any(Function));
      controller.destroy();
      closeNative(source);
      expect(closedSecond).toHaveBeenCalledOnce();
      expect(removedCloseListener).toHaveBeenCalledOnce();
      expect(maps.InfoWindow).toHaveBeenCalledOnce();
    }
  );
  it('releases header, body and close callback without disabling native close on reuse', () => {
    const { controller, popup, closeNative, removedCloseListener } = detailsMap();
    const onClose = vi.fn();
    controller.showDetails(
      'a',
      document.createElement('section'),
      document.createElement('h2'),
      onClose
    );
    controller.clearDetails();
    expect(popup.close).toHaveBeenCalledOnce();
    expect(popup.setContent).toHaveBeenLastCalledWith();
    expect(popup.setOptions).toHaveBeenLastCalledWith({ headerContent: undefined });
    closeNative();
    expect(onClose).not.toHaveBeenCalled();
    controller.showDetails('b', document.createElement('section'));
    expect(popup.setOptions).toHaveBeenLastCalledWith({
      ariaLabel: 'West',
      headerContent: undefined,
    });
    expect(popup.addListener).toHaveBeenCalledOnce();
    closeNative();
    expect(onClose).not.toHaveBeenCalled();
    controller.destroy();
    controller.destroy();
    expect(removedCloseListener).toHaveBeenCalledOnce();
  });
  it('updates one route overlay, fits its origin with places, and clears all resources on destroy', () => {
    const { controller, maps, line, popup, map } = detailsMap();
    controller.showDetails('a', document.createElement('div'));
    controller.setRoute(route);
    expect(maps.Polyline).toHaveBeenCalledOnce();
    expect(maps.Polyline).toHaveBeenCalledWith(expect.objectContaining({ map, path: route.path }));
    expect(maps.LatLngBounds).toHaveBeenLastCalledWith({
      north: 10,
      south: 0,
      west: 178,
      east: -179.9,
    });
    controller.setRoute(null);
    expect(line.setMap).toHaveBeenLastCalledWith(null);
    controller.setRoute({ ...route, path: [{ lat: 20, lng: 178 }, route.path[1]] });
    expect(maps.Polyline).toHaveBeenCalledOnce();
    expect(line.setMap).toHaveBeenLastCalledWith(map);
    expect(line.setOptions).toHaveBeenCalledWith(
      expect.objectContaining({ path: [{ lat: 20, lng: 178 }, route.path[1]] })
    );
    expect(maps.Map).toHaveBeenCalledOnce();
    controller.destroy();
    expect(popup.close).toHaveBeenCalledTimes(1);
    expect(popup.setContent).toHaveBeenLastCalledWith();
    expect(line.setMap).toHaveBeenLastCalledWith(null);
    const optionCalls = map.setOptions.mock.calls.length;
    controller.setRoute(route);
    controller.showDetails('a', document.createElement('div'));
    controller.select('a');
    expect(map.setOptions).toHaveBeenCalledTimes(optionCalls);
    expect(maps.InfoWindow).toHaveBeenCalledOnce();
    controller.destroy();
    expect(popup.close).toHaveBeenCalledTimes(1);
  });
  it('updates the route color with the document theme and releases the theme observer', async () => {
    const { controller, line } = detailsMap();
    controller.setRoute(route);
    expect(line.setOptions).toHaveBeenCalledWith(
      expect.objectContaining({ strokeColor: '#2563eb' })
    );
    document.documentElement.classList.add('dark');
    await Promise.resolve();
    expect(line.setOptions).toHaveBeenLastCalledWith(
      expect.objectContaining({ strokeColor: '#93c5fd' })
    );
    controller.destroy();
    const calls = line.setOptions.mock.calls.length;
    document.documentElement.classList.remove('dark');
    await Promise.resolve();
    expect(line.setOptions).toHaveBeenCalledTimes(calls);
  });
});
