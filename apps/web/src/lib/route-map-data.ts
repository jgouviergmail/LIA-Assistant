/** Closed display-only data, bounded again when reading old/untrusted archives. */
export interface MapPoint {
  lat: number;
  lng: number;
}
export interface MapRoute {
  id: string;
  path: MapPoint[];
  distance_meters: number | null;
  duration_seconds: number | null;
}
export interface RouteMapData {
  primary_id: string;
  routes: MapRoute[];
  omitted_count: number;
}
function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function measurement(value: unknown): number | null {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : null;
}
function decode(value: unknown): MapPoint[] | null {
  if (
    typeof value !== 'string' ||
    value.length > 100_000 ||
    !/^(?:[\x5f-\x7e]{0,6}[\x3f-\x5e]){2,}$/.test(value)
  )
    return null;
  const encoded = value;
  const points: MapPoint[] = [];
  let index = 0,
    lat = 0,
    lng = 0;
  function delta(): number {
    let group = 0,
      digits = 0,
      valueDigit: number;
    do {
      valueDigit = encoded.charCodeAt(index++) - 63;
      group += (valueDigit & 31) * 2 ** (digits++ * 5);
    } while (valueDigit >= 32);
    return group % 2 ? -Math.floor(group / 2) - 1 : group / 2;
  }
  while (index < value.length) {
    lat += delta();
    lng += delta();
    if (
      Math.abs(lat) > 9_000_000 ||
      Math.abs(lng) > 18_000_000 ||
      index > value.length ||
      points.length >= 25_000
    )
      return null;
    points.push({ lat: lat / 100_000, lng: lng / 100_000 });
  }
  return points.length >= 2 ? points : null;
}
export function parseRouteMap(wire: unknown): RouteMapData | null {
  if (typeof wire !== 'string' || wire.length > 810_000) return null;
  let source: unknown;
  try {
    source = JSON.parse(wire);
  } catch {
    return null;
  }
  if (!object(source) || source.version !== 1 || !validFamily(source.routes)) return null;
  const routes = parseRoutes(source.routes);
  if (!routes) return null;
  const omitted = measurement(source.omitted_count);
  if (
    typeof source.primary_id !== 'string' ||
    !routes.some(route => route.id === source.primary_id) ||
    omitted === null ||
    omitted > 8
  )
    return null;
  return { primary_id: source.primary_id, routes, omitted_count: omitted };
}
function validFamily(value: unknown): value is unknown[] {
  return Array.isArray(value) && value.length >= 1 && value.length <= 8;
}
function parseRoute(route: unknown): MapRoute | null {
  if (!object(route) || typeof route.id !== 'string' || !/^route-[0-7]$/.test(route.id))
    return null;
  const path = decode(route.polyline);
  return path
    ? {
        id: route.id,
        path,
        distance_meters: measurement(route.distance_meters),
        duration_seconds: measurement(route.duration_seconds),
      }
    : null;
}
function parseRoutes(source: unknown[]): MapRoute[] | null {
  const routes: MapRoute[] = [],
    ids = new Set<string>();
  let points = 0;
  for (const entry of source) {
    const route = parseRoute(entry);
    if (!route || ids.has(route.id) || (points += route.path.length) > 25_000) return null;
    ids.add(route.id);
    routes.push(route);
  }
  return routes;
}
