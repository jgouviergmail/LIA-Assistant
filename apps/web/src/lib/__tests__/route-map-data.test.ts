import { describe, expect, it } from 'vitest';
import { parseRouteMap } from '../route-map-data';

const wire = {
  version: 1,
  primary_id: 'route-1',
  omitted_count: 0,
  routes: [
    { id: 'route-0', polyline: '??_ibE_ibE', distance_meters: 0, duration_seconds: 0 },
    { id: 'route-1', polyline: '??_seK_seK', distance_meters: 1200, duration_seconds: 180 },
  ],
};
describe('archived exact route geometries', () => {
  it('keeps the actual primary index, coordinates and zero facts', () => {
    const parsed = parseRouteMap(JSON.stringify(wire));
    expect(parsed?.primary_id).toBe('route-1');
    expect(parsed?.routes[0]).toMatchObject({
      distance_meters: 0,
      duration_seconds: 0,
      path: [
        { lat: 0, lng: 0 },
        { lat: 1, lng: 1 },
      ],
    });
  });
  it.each([
    '',
    'null',
    '{',
    JSON.stringify({ ...wire, primary_id: 'other' }),
    JSON.stringify({ ...wire, routes: Array(9).fill(wire.routes[0]) }),
    JSON.stringify({ ...wire, routes: [wire.routes[0], wire.routes[0]] }),
  ])('refuses malformed families without network activity: %s', value => {
    expect(parseRouteMap(value)).toBeNull();
  });
  it.each(['_', '???', '~'.repeat(100001), '~~~~~~~????', '<script>', '_c`|@????'])(
    'refuses malformed/excessive/off-earth geometry: %s',
    polyline => {
      expect(
        parseRouteMap(
          JSON.stringify({ ...wire, routes: [wire.routes[0], { ...wire.routes[1], polyline }] })
        )
      ).toBeNull();
    }
  );
});
