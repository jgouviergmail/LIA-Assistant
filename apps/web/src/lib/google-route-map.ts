import type { MapPoint, RouteMapData } from './route-map-data';

/** Minimal official SDK boundary; no Directions/Places/geocoding library. */
export interface MapsListener {
  remove(): void;
}
export interface MapsMap {
  fitBounds(bounds: MapsBounds, padding: number): void;
  setOptions(options: Record<string, unknown>): void;
}
export interface MapsBounds {
  extend(point: MapPoint): void;
}
export interface MapsPolyline {
  setMap(map: MapsMap | null): void;
  setOptions(options: Record<string, unknown>): void;
  addListener(event: 'click', callback: () => void): MapsListener;
}
export interface MapsLibrary {
  readonly MapTypeControlStyle: { readonly DROPDOWN_MENU: number };
  Map: new (element: HTMLElement, options: Record<string, unknown>) => MapsMap;
  Polyline: new (options: Record<string, unknown>) => MapsPolyline;
  LatLngBounds: new () => MapsBounds;
  event: { clearInstanceListeners(instance: MapsMap): void };
}
declare global {
  interface Window {
    google?: { maps?: MapsLibrary };
    liaRouteMapsCallbacks?: Record<string, () => void>;
    gm_authFailure?: () => void;
  }
}
let loading: { key: string; promise: Promise<MapsLibrary> } | null = null;
const failures = new Set<() => void>();
let attempt = 0;

export function loadRouteMaps(key: string): Promise<MapsLibrary> {
  if (loading)
    return loading.key === key
      ? loading.promise
      : Promise.reject(new Error('Map configuration changed'));
  const promise = new Promise<MapsLibrary>((resolve, reject) => {
    const script = document.createElement('script');
    const callback = `load${++attempt}`;
    window.liaRouteMapsCallbacks ??= {};
    const previousFailure = window.gm_authFailure;
    let settled = false;
    const timer = window.setTimeout(fail, 15_000);
    function clean() {
      window.clearTimeout(timer);
      script.remove();
      delete window.liaRouteMapsCallbacks?.[callback];
      if (window.gm_authFailure === authFailure) window.gm_authFailure = previousFailure;
      loading = null;
    }
    function fail() {
      if (settled) return;
      settled = true;
      clean();
      reject(new Error('Map SDK unavailable'));
    }
    function authFailure() {
      previousFailure?.();
      for (const failure of failures) failure();
      if (settled) clean();
      else fail();
    }
    window.gm_authFailure = authFailure;
    window.liaRouteMapsCallbacks[callback] = () => {
      if (settled) return;
      const maps = window.google?.maps;
      if (!maps?.Map || !maps.Polyline || !maps.LatLngBounds) {
        fail();
        return;
      }
      settled = true;
      window.clearTimeout(timer);
      delete window.liaRouteMapsCallbacks?.[callback];
      resolve(maps);
    };
    const url = new URL('https://maps.googleapis.com/maps/api/js');
    url.search = new URLSearchParams({
      key,
      callback: `liaRouteMapsCallbacks.${callback}`,
      loading: 'async',
      v: 'quarterly',
    }).toString();
    script.src = url.toString();
    script.async = true;
    script.onerror = fail;
    document.head.append(script);
  });
  loading = { key, promise };
  return promise;
}

export function mountRouteMap(
  maps: MapsLibrary,
  element: HTMLElement,
  data: RouteMapData,
  onSelect: (id: string) => void,
  onFailure: () => void,
  onConstruct: () => void = () => {}
) {
  const map = new maps.Map(element, {
    center: data.routes[0].path[0],
    zoom: 12,
    gestureHandling: 'cooperative',
    mapTypeControl: true,
    mapTypeControlOptions: {
      style: maps.MapTypeControlStyle.DROPDOWN_MENU,
      mapTypeIds: ['roadmap', 'satellite', 'hybrid', 'terrain'],
    },
    streetViewControl: false,
    fullscreenControl: false,
    clickableIcons: false,
  });
  onConstruct();
  const lines: { route: RouteMapData['routes'][number]; line: MapsPolyline }[] = [];
  const listeners: MapsListener[] = [];
  function clear() {
    listeners.forEach(listener => listener.remove());
    lines.forEach(({ line }) => line.setMap(null));
    maps.event.clearInstanceListeners(map);
    element.replaceChildren();
  }
  try {
    for (const route of data.routes) {
      const line = new maps.Polyline({
        map,
        path: route.path,
        geodesic: false,
        strokeOpacity: 0.8,
        strokeWeight: 4,
      });
      lines.push({ route, line });
      listeners.push(line.addListener('click', () => onSelect(route.id)));
    }
  } catch (error) {
    clear();
    throw error;
  }
  let selected = data.primary_id;
  function fit() {
    const bounds = new maps.LatLngBounds();
    const route = data.routes.find(item => item.id === selected);
    route?.path.forEach(point => bounds.extend(point));
    map.fitBounds(bounds, 36);
  }
  function style() {
    const dark = document.documentElement.classList.contains('dark');
    const color = mapAccent(element, dark);
    map.setOptions({
      styles: dark
        ? [
            { elementType: 'geometry', stylers: [{ color: '#202b38' }] },
            { elementType: 'labels.text.fill', stylers: [{ color: '#e2e8f0' }] },
            { elementType: 'labels.text.stroke', stylers: [{ color: '#202b38' }] },
          ]
        : null,
    });
    lines.forEach(({ route, line }) =>
      line.setOptions({
        strokeColor: route.id === selected ? color : dark ? '#a1b4c8' : '#54657a',
        strokeOpacity: route.id === selected ? 1 : 0.6,
        strokeWeight: route.id === selected ? 6 : 4,
        zIndex: route.id === selected ? 2 : 1,
      })
    );
  }
  const observer = new MutationObserver(style);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class', 'data-oled', 'data-theme'],
  });
  failures.add(onFailure);
  try {
    style();
    fit();
  } catch (error) {
    observer.disconnect();
    failures.delete(onFailure);
    clear();
    throw error;
  }
  return {
    select(id: string) {
      if (data.routes.some(route => route.id === id)) {
        selected = id;
        style();
        fit();
      }
    },
    fit,
    destroy() {
      observer.disconnect();
      failures.delete(onFailure);
      clear();
    },
  };
}

function mapAccent(element: HTMLElement, dark: boolean): string {
  // Maps accepts CSS3 colors; convert the application's OKLCH token to sRGB.
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 1;
  const context = canvas.getContext('2d');
  const token = getComputedStyle(element).getPropertyValue('--color-primary').trim();
  if (!context || !token) return dark ? '#93c5fd' : '#2563eb';
  context.fillStyle = token;
  context.fillRect(0, 0, 1, 1);
  const [r, g, b] = context.getImageData(0, 0, 1, 1).data;
  return `rgb(${r}, ${g}, ${b})`;
}
