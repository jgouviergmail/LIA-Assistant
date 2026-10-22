import { z } from '@/lib/zod';
import { parseRouteMap } from '@/lib/route-map-data';

const response = z
  .object({
    origin_source: z.enum(['browser', 'last_known', 'home']),
    origin_as_of: z.string().datetime({ offset: true }).nullable().optional(),
    travel_mode: z.enum(['WALK', 'DRIVE']),
    polyline: z.string().max(50_000),
    distance_meters: z.number().int().min(0).max(Number.MAX_SAFE_INTEGER),
    duration_seconds: z.number().int().min(0).max(Number.MAX_SAFE_INTEGER),
  })
  .strict();

export function parsePlaceRoute(value: unknown) {
  const parsed = response.safeParse(value);
  if (!parsed.success) return null;
  const source = parsed.data;
  if (source.origin_source === 'last_known' && !source.origin_as_of) return null;
  const map = parseRouteMap(
    JSON.stringify({
      version: 1,
      primary_id: 'route-0',
      omitted_count: 0,
      routes: [{ id: 'route-0', ...source }],
    })
  );
  return map ? { ...source, route: map.routes[0] } : null;
}

export type PlaceRoute = NonNullable<ReturnType<typeof parsePlaceRoute>>;
