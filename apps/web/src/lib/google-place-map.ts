import {
  loadMapsSdk,
  mapFailures,
  type MapsLibrary,
  type MarkerLibrary,
  type MapsBoundsLiteral,
  type MapsInfoWindow,
  type MapsListener,
  type MapsMarker,
  type MapsPolyline,
  type MapsPinElement,
} from './google-maps-sdk';
import type { PlacePositionData } from './place-position-data';
import type { MapPoint, MapRoute } from './route-map-data';
import { mapAccent } from './google-route-map';

export async function loadPlaceMaps(key: string) {
  const maps = await loadMapsSdk(key);
  if (!maps.importLibrary) throw new Error('Marker library unavailable');
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const marker = await Promise.race([
      maps.importLibrary('marker'),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error('Marker library unavailable')), 10000);
      }),
    ]);
    if (
      typeof marker.AdvancedMarkerElement !== 'function' ||
      typeof marker.PinElement !== 'function'
    )
      throw new Error('Marker library unavailable');
    return { maps, marker };
  } finally {
    clearTimeout(timer);
  }
}

/** The complement of the largest longitude gap is the minimal visible interval. */
export function minimalPlaceBounds(points: MapPoint[]): MapsBoundsLiteral {
  if (!points.length) throw new Error('No positions');
  const longitudes = [...new Set(points.map(point => point.lng))].sort((a, b) => a - b);
  let gap = -1,
    cut = 0;
  longitudes.forEach((lng, index) => {
    const next = index + 1 < longitudes.length ? longitudes[index + 1] : longitudes[0] + 360;
    if (next - lng > gap) {
      gap = next - lng;
      cut = index;
    }
  });
  return {
    north: Math.max(...points.map(point => point.lat)),
    south: Math.min(...points.map(point => point.lat)),
    west: longitudes[(cut + 1) % longitudes.length],
    east: longitudes[cut],
  };
}

export function mountPlaceMap(
  maps: MapsLibrary,
  marker: MarkerLibrary,
  element: HTMLElement,
  data: PlacePositionData,
  mapId: string,
  onSelect: (ref: string) => void,
  onFailure: () => void,
  onConstruct: () => void
) {
  const located = data.places.filter(place => place.position !== null);
  const first = located[0]?.position;
  if (!first || !mapId) throw new Error('No positions or map ID');
  const map = new maps.Map(element, {
    center: first,
    zoom: 14,
    mapId,
    colorScheme: document.documentElement.classList.contains('dark') ? 'DARK' : 'LIGHT',
    gestureHandling: 'cooperative',
    clickableIcons: false,
    streetViewControl: false,
    fullscreenControl: false,
    mapTypeControl: true,
    mapTypeControlOptions: {
      style: maps.MapTypeControlStyle.DROPDOWN_MENU,
      mapTypeIds: ['roadmap', 'satellite', 'hybrid', 'terrain'],
    },
  });
  const markers: {
    ref: string;
    marker: InstanceType<MarkerLibrary['AdvancedMarkerElement']>;
    visual: MapsPinElement;
  }[] = [];
  const markerEvents = new AbortController();
  let details: MapsInfoWindow | null = null;
  let detailsCloseListener: MapsListener | null = null;
  let onDetailsClose: (() => void) | undefined;
  // What the open window is anchored on, and what it shows — null once closed.
  let shown: { anchor: MapsMarker; parts: (HTMLElement | undefined)[] } | null = null;
  let route: MapRoute | null = null;
  let routeLine: MapsPolyline | null = null;
  let destroyed = false;
  const observer = new MutationObserver(styleMap);
  function clearDetails() {
    onDetailsClose = undefined;
    shown = null;
    details?.close();
    details?.setContent();
    details?.setOptions({ headerContent: undefined });
  }
  function clear() {
    if (destroyed) return;
    destroyed = true;
    observer.disconnect();
    detailsCloseListener?.remove();
    detailsCloseListener = null;
    clearDetails();
    details = null;
    routeLine?.setMap(null);
    routeLine = null;
    route = null;
    markerEvents.abort();
    markers.forEach(value => {
      value.marker.map = null;
      value.marker.replaceChildren();
    });
    mapFailures.delete(onFailure);
    maps.event.clearInstanceListeners(map);
    element.replaceChildren();
  }
  function fit() {
    if (destroyed) return;
    const points = located.flatMap(value => (value.position ? [value.position] : []));
    points.push(...(route?.path ?? []));
    const bounds = minimalPlaceBounds(points);
    if (bounds.north === bounds.south && bounds.west === bounds.east)
      map.setOptions({ center: first, zoom: 14 });
    else map.fitBounds(new maps.LatLngBounds(bounds), 36);
    revealDetails();
  }
  /**
   * Open the shown window again once the map has moved under it.
   *
   * The map pans a window into view when it OPENS, and a fit moves the map
   * without moving the window: the route of a first selection comes back from
   * the network after its details placed themselves, and its fit left them
   * badly placed — a second selection, whose route comes from the cache, fitted
   * before they placed themselves (owner report 2026-10-22). The close this
   * costs is the map's, never the person's: their callback is held aside, as
   * `clearDetails` does. A window the person is working in is left alone —
   * re-opening detaches its content and would drop their focus.
   */
  function revealDetails() {
    const current = shown;
    if (!details || !current) return;
    const focused = document.activeElement;
    if (current.parts.some(part => part?.contains(focused))) return;
    const callback = onDetailsClose;
    onDetailsClose = undefined;
    details.close();
    details.open({ map, anchor: current.anchor, shouldFocus: false });
    shown = current;
    onDetailsClose = callback;
  }
  function pinColors() {
    const theme = getComputedStyle(element);
    const dark = document.documentElement.classList.contains('dark');
    return {
      background:
        theme.getPropertyValue('--color-primary').trim() || (dark ? '#93c5fd' : '#2563eb'),
      glyphColor:
        theme.getPropertyValue('--color-primary-foreground').trim() ||
        (dark ? '#0f172a' : '#ffffff'),
      borderColor:
        theme.getPropertyValue('--color-background').trim() || (dark ? '#0f172a' : '#ffffff'),
    };
  }
  function styleMap() {
    if (destroyed) return;
    const colors = pinColors();
    markers.forEach(({ visual }) => {
      visual.background = colors.background;
      visual.glyphColor = colors.glyphColor;
      visual.borderColor = colors.borderColor;
    });
    if (!routeLine) return;
    const dark = document.documentElement.classList.contains('dark');
    routeLine.setOptions({
      strokeColor: mapAccent(element, dark),
      strokeOpacity: 1,
      strokeWeight: 6,
      zIndex: 2,
    });
  }
  try {
    onConstruct();
    const colors = pinColors();
    located.forEach(place => {
      const number = String(data.places.indexOf(place) + 1);
      const visual = new marker.PinElement({ glyphText: number, ...colors });
      visual.classList.add('lia-place-position__map-pin');
      visual.dataset.placeNumber = number;
      visual.setAttribute('aria-hidden', 'true');
      const pin = new marker.AdvancedMarkerElement({
        map,
        position: place.position,
        title: `${number}. ${place.label}`,
        gmpClickable: true,
        zIndex: 1,
      });
      markers.push({ ref: place.ref, marker: pin, visual });
      pin.append(visual);
      pin.addEventListener('gmp-click', () => onSelect(place.ref), { signal: markerEvents.signal });
    });
    fit();
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class', 'data-oled', 'data-theme'],
    });
    mapFailures.add(onFailure);
  } catch (error) {
    clear();
    throw error;
  }
  return {
    fit,
    destroy: clear,
    clearDetails,
    showDetails(ref: string, content: HTMLElement, header?: HTMLElement, onClose?: () => void) {
      if (destroyed || !maps.InfoWindow) return;
      const anchor = markers.find(value => value.ref === ref)?.marker;
      if (!anchor) return;
      // Google applies maxWidth before open; its native body owns vertical scrolling.
      if (!details) {
        details = new maps.InfoWindow({ maxWidth: 440 });
        detailsCloseListener = details.addListener('close', () => {
          shown = null;
          const callback = onDetailsClose;
          onDetailsClose = undefined;
          callback?.();
        });
      }
      onDetailsClose = onClose;
      const label = data.places.find(value => value.ref === ref)?.label ?? '';
      details.setOptions({ ariaLabel: label, headerContent: header });
      details.setContent(content);
      details.open({ map, anchor, shouldFocus: false });
      shown = { anchor, parts: [content, header] };
    },
    setRoute(next: MapRoute | null) {
      if (destroyed) return;
      route = next;
      if (!next) {
        routeLine?.setMap(null);
        return;
      }
      if (routeLine) {
        routeLine.setOptions({ path: next.path });
        routeLine.setMap(map);
      } else {
        routeLine = new maps.Polyline({ map, path: next.path, geodesic: false });
      }
      styleMap();
      fit();
    },
    select(ref: string) {
      if (destroyed) return;
      const place = located.find(value => value.ref === ref);
      if (!place?.position) return;
      markers.forEach(value => {
        value.marker.zIndex = value.ref === ref ? 10 : 1;
      });
      map.setOptions({ center: place.position, zoom: 15 });
    },
  };
}
