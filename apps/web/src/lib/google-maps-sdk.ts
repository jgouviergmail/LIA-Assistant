import type { MapPoint } from './route-map-data';

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
export interface MapsBoundsLiteral {
  north: number;
  south: number;
  west: number;
  east: number;
}
export interface MapsMarker extends Pick<
  HTMLElement,
  'addEventListener' | 'removeEventListener' | 'append' | 'replaceChildren'
> {
  map: MapsMap | null;
  zIndex?: number;
}
export interface MapsPinElementOptions {
  glyphText?: string;
  background?: string;
  borderColor?: string;
  glyphColor?: string;
}
export interface MapsPinElement extends HTMLElement {
  glyphText?: string;
  background?: string;
  borderColor?: string;
  glyphColor?: string;
}
export interface MarkerLibrary {
  AdvancedMarkerElement: new (options: Record<string, unknown>) => MapsMarker;
  PinElement: new (options: MapsPinElementOptions) => MapsPinElement;
}
export interface MapsPolyline {
  setMap(map: MapsMap | null): void;
  setOptions(options: Record<string, unknown>): void;
  addListener(event: 'click', callback: () => void): MapsListener;
}
export interface MapsInfoWindowOptions {
  ariaLabel?: string;
  maxWidth?: number;
  headerContent?: HTMLElement;
}
export interface MapsInfoWindow {
  setContent(content?: HTMLElement): void;
  setOptions(options: MapsInfoWindowOptions): void;
  open(options: { map: MapsMap; anchor: MapsMarker; shouldFocus: boolean }): void;
  close(): void;
  addListener(event: 'close', callback: () => void): MapsListener;
}
export interface MapsLibrary {
  readonly MapTypeControlStyle: { readonly DROPDOWN_MENU: number };
  Map: new (element: HTMLElement, options: Record<string, unknown>) => MapsMap;
  Polyline: new (options: Record<string, unknown>) => MapsPolyline;
  InfoWindow?: new (options?: MapsInfoWindowOptions) => MapsInfoWindow;
  LatLngBounds: new (bounds?: MapsBoundsLiteral) => MapsBounds;
  importLibrary?: (library: 'marker') => Promise<MarkerLibrary>;
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
export const mapFailures = new Set<() => void>();
let attempt = 0;

export function loadMapsSdk(key: string): Promise<MapsLibrary> {
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
      for (const failure of mapFailures) failure();
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
