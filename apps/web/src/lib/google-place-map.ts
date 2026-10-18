import {
  loadMapsSdk,
  mapFailures,
  type MapsLibrary,
  type MarkerLibrary,
  type MapsBoundsLiteral,
} from './google-maps-sdk';
import type { PlacePositionData } from './place-position-data';
import type { MapPoint } from './route-map-data';

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
    if (typeof marker.AdvancedMarkerElement !== 'function')
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
  const markers: { ref: string; marker: InstanceType<MarkerLibrary['AdvancedMarkerElement']> }[] =
    [];
  const markerEvents = new AbortController();
  function clear() {
    markerEvents.abort();
    markers.forEach(value => {
      value.marker.map = null;
    });
    mapFailures.delete(onFailure);
    maps.event.clearInstanceListeners(map);
    element.replaceChildren();
  }
  function fit() {
    const points = located.flatMap(value => (value.position ? [value.position] : []));
    const bounds = minimalPlaceBounds(points);
    if (bounds.north === bounds.south && bounds.west === bounds.east)
      map.setOptions({ center: first, zoom: 14 });
    else map.fitBounds(new maps.LatLngBounds(bounds), 36);
  }
  try {
    onConstruct();
    located.forEach(place => {
      const pin = new marker.AdvancedMarkerElement({
        map,
        position: place.position,
        title: `${data.places.indexOf(place) + 1}. ${place.label}`,
        gmpClickable: true,
        zIndex: 1,
      });
      markers.push({ ref: place.ref, marker: pin });
      pin.addEventListener('gmp-click', () => onSelect(place.ref), { signal: markerEvents.signal });
    });
    fit();
    mapFailures.add(onFailure);
  } catch (error) {
    clear();
    throw error;
  }
  return {
    fit,
    destroy: clear,
    select(ref: string) {
      const place = located.find(value => value.ref === ref);
      if (!place?.position) return;
      markers.forEach(value => {
        value.marker.zIndex = value.ref === ref ? 10 : 1;
      });
      map.setOptions({ center: place.position, zoom: 15 });
    },
  };
}
