import { z } from '@/lib/zod';

function mapsLink(value: string) {
  try {
    const url = new URL(value);
    return (
      url.origin === 'https://www.google.com' &&
      !url.username &&
      !url.password &&
      (url.pathname === '/maps/place/' || url.pathname === '/maps/search/')
    );
  } catch {
    return false;
  }
}
const point = z
  .object({
    lat: z.number().finite().min(-90).max(90),
    lng: z.number().finite().min(-180).max(180),
  })
  .strict();
const place = z
  .object({
    ref: z.string().min(1).max(256),
    label: z.string().min(1).max(200),
    url: z.string().max(4096).refine(mapsLink),
    position: point.nullable(),
  })
  .strict();
const positionMap = z
  .object({
    version: z.literal(1),
    places: z.array(place).min(1).max(64),
    omitted_count: z.number().int().min(0).max(10000),
    unlocated_count: z.number().int().min(0).max(10000),
  })
  .strict()
  .refine(
    data =>
      new Set(data.places.map(item => item.ref)).size === data.places.length &&
      data.unlocated_count >= data.places.filter(item => !item.position).length &&
      data.unlocated_count <= data.places.length + data.omitted_count
  );

export type PlacePositionData = z.infer<typeof positionMap>;
export function parsePlacePosition(wire: unknown): PlacePositionData | null {
  if (typeof wire !== 'string' || wire.length > 262144) return null;
  try {
    const result = positionMap.safeParse(JSON.parse(wire));
    return result.success ? result.data : null;
  } catch {
    return null;
  }
}
